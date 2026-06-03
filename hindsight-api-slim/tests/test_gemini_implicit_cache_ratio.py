"""Measure Gemini's *implicit* prompt-cache hit rate, without explicit caching.

Context: PR #1936 (feat/gemini-context-cache) adds explicit Gemini
``CachedContent`` caching for the two big-fixed-prefix call paths
(``retain_extract_facts`` and the reflect tool loop). The premise is that those
paths re-send a large constant prefix (system prompt + response schema / tools)
on every call, so charging that prefix at the cached-input rate is a clear win.

These tests establish the *baseline* the PR has to beat: with the explicit cache
turned OFF (it doesn't even exist on this branch), how much does Gemini's own
automatic / implicit caching already give us for free? We run real Gemini, route
every call through the LLM-request tracer added in #1922, and read back the
recorded ``cached_tokens`` vs ``input_tokens`` per scope.

The point is observation, not a pass/fail threshold — the cached-token ratio is
printed loudly so it can be quoted in the PR discussion. The only hard assertions
are structural (we actually recorded N traced calls that each re-sent the prefix,
and tokens were captured), so the test never flakes on Gemini's caching whims.

Gated on ``HINDSIGHT_RUN_GEMINI_EVALS=1`` plus a Gemini API key, since it costs
money and needs network. Implicit caching is a 2.5-family feature, so the default
model is ``gemini-2.5-flash`` (override with ``HINDSIGHT_GEMINI_EVAL_MODEL``).
"""

import asyncio
import os
import uuid

import pytest
from hindsight_api.engine.llm_trace import LLMRequestEntry

from hindsight_api import MemoryEngine, RequestContext
from hindsight_api.engine.consolidation.consolidator import run_consolidation_job
from hindsight_api.engine.llm_wrapper import LLMConfig

_GEMINI_API_KEY = (
    os.getenv("HINDSIGHT_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)
_RUN = os.getenv("HINDSIGHT_RUN_GEMINI_EVALS") == "1" and bool(_GEMINI_API_KEY)

pytestmark = pytest.mark.skipif(
    not _RUN,
    reason=(
        "Gemini implicit-cache measurement is gated. Set HINDSIGHT_RUN_GEMINI_EVALS=1 "
        "and provide GEMINI_API_KEY/GOOGLE_API_KEY to run."
    ),
)

# Number of retain "chunks": each is a separate retain call → a separate
# retain_extract_facts LLM call that re-sends the same ~3k-token system prefix.
# That repetition is the precondition for any caching (implicit or explicit) to
# kick in. Override with HINDSIGHT_GEMINI_CACHE_CHUNKS.
_CHUNKS = int(os.getenv("HINDSIGHT_GEMINI_CACHE_CHUNKS", "5"))

# Distinct paragraphs so each retain extracts real, non-duplicate facts. The
# *content* varies per call; the system prompt / schema prefix does not — which
# is exactly the shape caching targets.
_DOCS = [
    "Ada Lovelace worked with Charles Babbage on the Analytical Engine in the 1840s. "
    "She wrote what is often considered the first algorithm intended for a machine, "
    "a method for computing Bernoulli numbers. She lived in London and corresponded "
    "extensively with Babbage about the engine's capabilities.",
    "Grace Hopper joined the Harvard Mark I team in 1944 and later developed the first "
    "compiler, A-0, in 1952. She championed machine-independent programming languages, "
    "which led to COBOL. She served in the US Navy and retired as a rear admiral.",
    "Katherine Johnson computed orbital mechanics for NASA's first crewed spaceflights. "
    "John Glenn personally asked her to verify the electronic computer's calculations "
    "before his 1962 Friendship 7 orbit. She worked at Langley Research Center in Virginia.",
    "Alan Turing formalized computation with the Turing machine in 1936 and worked at "
    "Bletchley Park during World War II breaking the Enigma cipher. He proposed the "
    "imitation game, now called the Turing test, in a 1950 paper on machine intelligence.",
    "Margaret Hamilton led the software engineering team that wrote the onboard flight "
    "software for the Apollo missions at MIT. Her error-detection code prevented an abort "
    "during the Apollo 11 landing in 1969. She later coined the term 'software engineering'.",
    "Barbara Liskov designed the CLU programming language in the 1970s and introduced data "
    "abstraction. The Liskov substitution principle is named after her. She won the Turing "
    "Award in 2008 for contributions to programming language and system design.",
    "Tim Berners-Lee invented the World Wide Web in 1989 while at CERN, writing the first "
    "browser and the HTTP protocol. He founded the World Wide Web Consortium in 1994 to "
    "develop open web standards.",
    "Radia Perlman invented the spanning-tree protocol while at Digital Equipment Corporation, "
    "which made large bridged Ethernet networks possible. She is sometimes called the mother "
    "of the internet, a title she has said she dislikes.",
]


# Explicit Gemini prompt caching (PR #1936) — opt-in. Set HINDSIGHT_GEMINI_EXPLICIT_CACHE=1
# to turn it on for this run. On a branch without the feature the flag is simply
# ignored, so the same test measures the implicit baseline there.
_EXPLICIT_CACHE = os.getenv("HINDSIGHT_GEMINI_EXPLICIT_CACHE") == "1"


async def _gemini_engine(memory_no_llm_verify: MemoryEngine) -> MemoryEngine:
    """Point an engine at real Gemini and force-enable the LLM-request tracer.

    The fixture builds the engine with tracing disabled (config default). The
    recorder reads ``enabled`` once at construction, so we flip the flag directly
    rather than rebuilding the engine — equivalent to running with
    ``HINDSIGHT_API_LLM_TRACE_ENABLED=true``.

    When ``HINDSIGHT_GEMINI_EXPLICIT_CACHE=1`` we also enable PR #1936's explicit
    CachedContent caching the production way (env var + config-cache clear), so we
    can compare its cached/input ratio against the implicit baseline. Otherwise the
    only caching observed is Gemini's own implicit caching.
    """
    from hindsight_api.config import clear_config_cache

    model = os.getenv("HINDSIGHT_GEMINI_EVAL_MODEL", "gemini-2.5-flash")
    if _EXPLICIT_CACHE:
        os.environ["HINDSIGHT_API_LLM_GEMINI_PROMPT_CACHE_ENABLED"] = "true"
        clear_config_cache()  # so the bank-config resolver re-reads the flag from env
    cfg = LLMConfig(
        provider="gemini",
        api_key=_GEMINI_API_KEY or "",
        base_url="",
        model=model,
        gemini_prompt_cache_enabled=_EXPLICIT_CACHE,
    )
    memory_no_llm_verify._llm_config = cfg
    memory_no_llm_verify._retain_llm_config = cfg
    memory_no_llm_verify._reflect_llm_config = cfg
    memory_no_llm_verify._consolidation_llm_config = cfg
    memory_no_llm_verify._llm_recorder._enabled = True
    mode = "EXPLICIT cache ON" if _EXPLICIT_CACHE else "implicit only"
    print(f"\n[gemini-cache] provider=gemini model={model} chunks={_CHUNKS} mode={mode}")
    return memory_no_llm_verify


async def _drain_traces(mem: MemoryEngine) -> None:
    """Wait for the recorder's fire-and-forget trace writes to land.

    record_llm_call schedules each INSERT as a detached asyncio task tracked in
    ``_pending`` (bucketed by trace_id). Gather them so the rows are queryable.
    Loop a few times because consolidation's attach_memory_ids can spawn a
    follow-up write after the first drain.
    """
    await mem.wait_for_background_tasks()
    rec = mem._llm_recorder
    for _ in range(10):
        pending = [t for bucket in rec._pending.values() for t in bucket if not t.done()]
        if not pending:
            break
        await asyncio.gather(*pending, return_exceptions=True)


def _report(scope: str, rows: list[LLMRequestEntry]) -> float:
    """Print the cached/input token ratio for a scope and return it.

    Gemini's ``prompt_token_count`` (our ``input_tokens``) already includes the
    cached prefix, so ``cached_tokens / input_tokens`` is the fraction of prompt
    tokens billed at the cheaper cached rate — the number the PR's
    ``cached_input / input`` dashboard would show.
    """
    input_total = sum((r.input_tokens or 0) for r in rows)
    cached_total = sum((r.cached_tokens or 0) for r in rows)
    output_total = sum((r.output_tokens or 0) for r in rows)
    ratio = (cached_total / input_total) if input_total else 0.0
    per_call = ", ".join(f"{(r.cached_tokens or 0)}/{(r.input_tokens or 0)}" for r in rows)
    print(
        f"\n[gemini-cache] scope={scope!r} calls={len(rows)}\n"
        f"  input_tokens   = {input_total}\n"
        f"  cached_tokens  = {cached_total}\n"
        f"  output_tokens  = {output_total}\n"
        f"  cached/input   = {ratio:.1%}  (implicit caching, no explicit prompting)\n"
        f"  per-call cached/input: {per_call}"
    )
    return ratio


@pytest.mark.hs_llm_core
class TestGeminiImplicitCacheRatio:
    async def _fetch(self, mem: MemoryEngine, bank_id: str, rc: RequestContext, scope: str) -> list[LLMRequestEntry]:
        resp = await mem.list_llm_requests(bank_id, request_context=rc, scope=scope, limit=200)
        assert resp is not None, "bank should exist"
        return [r for r in resp.items if r.status == "success"]

    async def test_retain_chunks_cached_ratio(self, memory_no_llm_verify, request_context):
        """Retain N distinct chunks → N fact-extraction calls sharing one prefix."""
        mem = await _gemini_engine(memory_no_llm_verify)
        bank_id = f"gemini-cache-retain-{uuid.uuid4().hex[:8]}"
        await mem.get_bank_profile(bank_id, request_context=request_context)

        docs = [_DOCS[i % len(_DOCS)] for i in range(_CHUNKS)]
        for i, content in enumerate(docs):
            await mem.retain_batch_async(
                bank_id=bank_id,
                contents=[{"content": content}],
                request_context=request_context,
                document_id=f"doc-{i}",
            )
        await _drain_traces(mem)

        rows = await self._fetch(mem, bank_id, request_context, "retain_extract_facts")
        ratio = _report("retain_extract_facts", rows)

        # Structural guarantees — the prefix was re-sent N times and tokens were
        # captured. The ratio itself is a measurement, not a threshold.
        assert len(rows) >= _CHUNKS, f"expected >= {_CHUNKS} extraction calls, got {len(rows)}"
        assert all((r.provider == "gemini") for r in rows)
        assert sum((r.input_tokens or 0) for r in rows) > 0, "no input tokens recorded"
        assert 0.0 <= ratio <= 1.0

        await mem.delete_bank(bank_id, request_context=request_context)

    async def test_consolidation_cached_ratio(self, memory_no_llm_verify, request_context):
        """Retain a batch, then consolidate and measure the consolidation prefix reuse."""
        mem = await _gemini_engine(memory_no_llm_verify)
        bank_id = f"gemini-cache-consol-{uuid.uuid4().hex[:8]}"
        await mem.get_bank_profile(bank_id, request_context=request_context)

        # Seed enough unconsolidated memories that consolidation makes several
        # same-prefix LLM calls.
        await mem.retain_batch_async(
            bank_id=bank_id,
            contents=[{"content": d} for d in _DOCS],
            request_context=request_context,
        )
        await mem.wait_for_background_tasks()

        await run_consolidation_job(mem, bank_id, request_context)
        await _drain_traces(mem)

        rows = await self._fetch(mem, bank_id, request_context, "consolidation")
        if not rows:
            pytest.skip("consolidation made no LLM calls for this seed (nothing to consolidate)")
        ratio = _report("consolidation", rows)

        assert all((r.provider == "gemini") for r in rows)
        assert sum((r.input_tokens or 0) for r in rows) > 0, "no input tokens recorded"
        assert 0.0 <= ratio <= 1.0

        await mem.delete_bank(bank_id, request_context=request_context)
