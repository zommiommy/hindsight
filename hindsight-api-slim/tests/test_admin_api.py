"""Tests for the admin surface: GET /admin/config + the admin_api feature flag.

These are deterministic (no LLM): the endpoint only reads server-level config. We
toggle env vars + clear the config cache to exercise the enable flag, the optional
admin token, and credential redaction.
"""

import httpx
import pytest
import pytest_asyncio

from hindsight_api.api import create_app
from hindsight_api.config import clear_config_cache


@pytest_asyncio.fixture
async def admin_client(memory):
    """Async test client for the FastAPI app (mock LLM)."""
    app = create_app(memory, initialize_memory=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _set_env(monkeypatch, **values: str | None) -> None:
    """Set/unset env vars and reset the cached config so the next read reflects them."""
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    clear_config_cache()


@pytest.fixture(autouse=True)
def _restore_config_cache():
    """Ensure the global config cache is reset after each test."""
    yield
    clear_config_cache()


@pytest.mark.asyncio
async def test_admin_config_disabled_by_default(admin_client, monkeypatch):
    """When the admin API is disabled (default), the endpoint is invisible (404)."""
    _set_env(monkeypatch, HINDSIGHT_API_ENABLE_ADMIN_API=None, HINDSIGHT_API_ADMIN_TOKEN=None)

    response = await admin_client.get("/admin/config")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_config_enabled_no_token(admin_client, monkeypatch):
    """When enabled without a token, the endpoint is open and returns config."""
    _set_env(monkeypatch, HINDSIGHT_API_ENABLE_ADMIN_API="true", HINDSIGHT_API_ADMIN_TOKEN=None)

    response = await admin_client.get("/admin/config")

    assert response.status_code == 200
    config = response.json()["config"]
    # A representative spread of non-credential fields should be present.
    assert "llm_provider" in config
    assert "enable_admin_api" in config
    assert config["enable_admin_api"] is True


@pytest.mark.asyncio
async def test_admin_config_redacts_credentials(admin_client, monkeypatch):
    """Credential fields are masked, never returned in cleartext."""
    _set_env(
        monkeypatch,
        HINDSIGHT_API_ENABLE_ADMIN_API="true",
        HINDSIGHT_API_ADMIN_TOKEN="s3cret-token",
        HINDSIGHT_API_LLM_API_KEY="super-secret-key",
    )

    response = await admin_client.get("/admin/config", headers={"Authorization": "Bearer s3cret-token"})

    assert response.status_code == 200
    config = response.json()["config"]
    # The configured LLM key is present but masked.
    assert config["llm_api_key"] == "***"
    assert "super-secret-key" not in response.text
    # Provider keys that fall back to the LLM key (and aren't in the credential
    # denylist) must also be masked — the view redacts by name, not just the set.
    assert config["embeddings_openrouter_api_key"] == "***"
    assert config["reranker_openrouter_api_key"] == "***"
    # The admin token must never leak through its own config view.
    assert config["admin_api_token"] == "***"
    assert "s3cret-token" not in response.text
    # Value-bearing fields that merely contain "token" in their name (plural) are
    # NOT redacted — they carry useful config, not secrets.
    assert config["recall_max_tokens"] != "***"


@pytest.mark.asyncio
async def test_admin_config_requires_token_when_set(admin_client, monkeypatch):
    """With a token configured, missing/wrong tokens are rejected; the right one passes."""
    _set_env(
        monkeypatch,
        HINDSIGHT_API_ENABLE_ADMIN_API="true",
        HINDSIGHT_API_ADMIN_TOKEN="right-token",
    )

    missing = await admin_client.get("/admin/config")
    assert missing.status_code == 401

    wrong = await admin_client.get("/admin/config", headers={"Authorization": "Bearer wrong-token"})
    assert wrong.status_code == 401

    bearer = await admin_client.get("/admin/config", headers={"Authorization": "Bearer right-token"})
    assert bearer.status_code == 200

    # A bare token (no "Bearer " prefix) is also accepted.
    bare = await admin_client.get("/admin/config", headers={"Authorization": "right-token"})
    assert bare.status_code == 200


@pytest.mark.asyncio
async def test_version_reports_admin_api_flag(admin_client, monkeypatch):
    """The /version feature flags track the admin enable flag."""
    _set_env(monkeypatch, HINDSIGHT_API_ENABLE_ADMIN_API="true")
    enabled = await admin_client.get("/version")
    assert enabled.json()["features"]["admin_api"] is True

    _set_env(monkeypatch, HINDSIGHT_API_ENABLE_ADMIN_API="false")
    disabled = await admin_client.get("/version")
    assert disabled.json()["features"]["admin_api"] is False
