"""Unit tests for GeminiCacheManager.

The SDK's caches.create call is replaced with a fake throughout — no
network, no real Gemini calls. We assert:

* Identical prefixes return identical fingerprints (cache hits).
* Different prefixes return different fingerprints.
* The first get_or_create for a fingerprint creates; the second within
  the TTL window reuses without calling the SDK again.
* "minimum token count" errors from Gemini surface as ``None`` (soft
  fallback), not exceptions.
* Other SDK errors also surface as ``None`` so callers don't crash on
  transient creation failures.
* The TTL refresh boundary recreates after the safety margin elapses.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from hindsight_api.engine.providers.gemini_cache import GeminiCacheManager


def _make_client(create_side_effect=None):
    """Build a fake Gemini client whose ``aio.caches.create`` returns
    a SimpleNamespace with ``.name`` (or raises the given exception)."""
    create_mock = AsyncMock()
    if isinstance(create_side_effect, Exception):
        create_mock.side_effect = create_side_effect
    elif callable(create_side_effect):
        create_mock.side_effect = create_side_effect
    else:
        create_mock.return_value = SimpleNamespace(
            name="cachedContents/test-cache-name-001"
        )

    client = MagicMock()
    client.aio = MagicMock()
    client.aio.caches = MagicMock()
    client.aio.caches.create = create_mock
    return client, create_mock


# ---- Fingerprint properties ----------------------------------------------


def test_fingerprint_is_stable():
    fp1 = GeminiCacheManager.fingerprint(
        model="gemini-3.1-flash-lite",
        system_instruction="Extract facts.",
        response_schema=None,
    )
    fp2 = GeminiCacheManager.fingerprint(
        model="gemini-3.1-flash-lite",
        system_instruction="Extract facts.",
        response_schema=None,
    )
    assert fp1 == fp2


def test_fingerprint_changes_with_model():
    fp1 = GeminiCacheManager.fingerprint("gemini-3.1-flash-lite", "X", None)
    fp2 = GeminiCacheManager.fingerprint("gemini-3.1-flash", "X", None)
    assert fp1 != fp2


def test_fingerprint_changes_with_system_instruction():
    fp1 = GeminiCacheManager.fingerprint("m", "Extract facts.", None)
    fp2 = GeminiCacheManager.fingerprint("m", "Extract entities.", None)
    assert fp1 != fp2


def test_fingerprint_handles_pydantic_schema():
    """Two equivalent Pydantic schemas should fingerprint identically;
    a different shape should not."""
    from pydantic import BaseModel

    class A(BaseModel):
        x: int
        y: str

    class A_dup(BaseModel):
        x: int
        y: str

    class B(BaseModel):
        x: int
        y: int  # different type

    fp_a = GeminiCacheManager.fingerprint("m", "p", A)
    fp_dup = GeminiCacheManager.fingerprint("m", "p", A_dup)
    fp_b = GeminiCacheManager.fingerprint("m", "p", B)

    # A and A_dup have the same JSON schema, even though they're distinct classes.
    assert fp_a == fp_dup
    assert fp_a != fp_b


# ---- get_or_create lifecycle ---------------------------------------------


@pytest.mark.asyncio
async def test_first_call_creates_subsequent_reuses():
    client, create_mock = _make_client()
    mgr = GeminiCacheManager(client)

    name1 = await mgr.get_or_create(
        model="gemini-3.1-flash-lite",
        system_instruction="Extract facts.",
        response_schema=None,
    )
    name2 = await mgr.get_or_create(
        model="gemini-3.1-flash-lite",
        system_instruction="Extract facts.",
        response_schema=None,
    )

    assert name1 == "cachedContents/test-cache-name-001"
    assert name2 == name1
    # Only ONE underlying create call — second was served from in-memory cache.
    assert create_mock.call_count == 1


@pytest.mark.asyncio
async def test_different_prefixes_create_separately():
    client, create_mock = _make_client(
        create_side_effect=lambda *a, **kw: SimpleNamespace(
            name=f"cachedContents/created-{create_mock.call_count}"
        )
    )
    mgr = GeminiCacheManager(client)

    name_a = await mgr.get_or_create(
        model="m", system_instruction="A", response_schema=None
    )
    name_b = await mgr.get_or_create(
        model="m", system_instruction="B", response_schema=None
    )
    assert name_a != name_b
    assert create_mock.call_count == 2


# ---- Failure / fallback handling -----------------------------------------


@pytest.mark.asyncio
async def test_minimum_token_count_error_returns_none():
    """When the prefix is too short, Gemini rejects with a 'minimum
    token count' style message. Manager must surface this as None so
    the caller transparently falls back to a non-cached call."""
    err = Exception("Cached content must have at least 1024 input tokens (minimum)")
    client, _ = _make_client(create_side_effect=err)
    mgr = GeminiCacheManager(client)

    result = await mgr.get_or_create(
        model="m", system_instruction="tiny", response_schema=None
    )
    assert result is None


@pytest.mark.asyncio
async def test_other_sdk_errors_also_return_none():
    """Transient errors (rate limits, 5xx, etc.) should fail soft so
    a single bad create doesn't crash every retain call."""
    err = RuntimeError("transient backend error 503")
    client, _ = _make_client(create_side_effect=err)
    mgr = GeminiCacheManager(client)

    result = await mgr.get_or_create(
        model="m", system_instruction="ok-sized prefix", response_schema=None
    )
    assert result is None


@pytest.mark.asyncio
async def test_failed_create_does_not_poison_cache():
    """If create fails on first attempt, a retry should call create
    again instead of returning a stale/None entry."""
    call_log = []

    async def maybe_fail(*args, **kwargs):
        call_log.append(1)
        if len(call_log) == 1:
            raise RuntimeError("first call fails")
        return SimpleNamespace(name="cachedContents/recovered")

    client = MagicMock()
    client.aio = MagicMock()
    client.aio.caches = MagicMock()
    client.aio.caches.create = maybe_fail

    mgr = GeminiCacheManager(client)

    first = await mgr.get_or_create(
        model="m", system_instruction="prefix", response_schema=None
    )
    second = await mgr.get_or_create(
        model="m", system_instruction="prefix", response_schema=None
    )

    assert first is None
    assert second == "cachedContents/recovered"
    assert len(call_log) == 2


# ---- TTL behaviour --------------------------------------------------------


@pytest.mark.asyncio
async def test_refreshes_after_ttl_margin(monkeypatch):
    """An entry created at t=0 with ttl=10 and margin=2 should be
    treated as stale at t>=8 and trigger a recreate."""
    client, create_mock = _make_client(
        create_side_effect=lambda *a, **kw: SimpleNamespace(
            name=f"cachedContents/v{create_mock.call_count}"
        )
    )
    mgr = GeminiCacheManager(client, ttl_seconds=10, refresh_margin_seconds=2)

    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hindsight_api.engine.providers.gemini_cache.time.monotonic",
        lambda: fake_now["t"],
    )

    first = await mgr.get_or_create(
        model="m", system_instruction="p", response_schema=None
    )
    assert first == "cachedContents/v1"

    # Advance to just before the refresh boundary — should reuse.
    fake_now["t"] = 1000.0 + 7.0
    again = await mgr.get_or_create(
        model="m", system_instruction="p", response_schema=None
    )
    assert again == "cachedContents/v1"
    assert create_mock.call_count == 1

    # Advance past the refresh boundary — should recreate.
    fake_now["t"] = 1000.0 + 9.0
    refreshed = await mgr.get_or_create(
        model="m", system_instruction="p", response_schema=None
    )
    assert refreshed == "cachedContents/v2"
    assert create_mock.call_count == 2
