"""
Tests for the HINDSIGHT_API_STORE_DOCUMENT_TEXT privacy flag.

When disabled, the retain pipeline still extracts facts/entities and embeds
them, but the raw source text is dropped: documents.original_text is stored as
NULL and chunks.chunk_text is stored as an empty string. Recall must be
unaffected because it reads from memory_units, not original_text.
"""

import os
from datetime import datetime, timezone

import pytest

from hindsight_api import config as config_module
from hindsight_api.engine.memory_engine import Budget
from hindsight_api.engine.reflect.tools_schema import get_reflect_tools

LONG_CONTENT = """
Alice Johnson is a senior software engineer at Acme Corp. She specializes in
distributed systems and leads the platform team. Bob Smith works in marketing
and reports to Carol. The team uses Kubernetes and deploys to AWS. Code reviews
are mandatory before merging.
"""


@pytest.fixture
def store_document_text_disabled():
    """Disable raw document/chunk text storage for the duration of a test.

    Restores the environment and clears the config cache afterwards so other
    tests in the same worker see the default behaviour again.
    """
    original = os.environ.get("HINDSIGHT_API_STORE_DOCUMENT_TEXT")
    os.environ["HINDSIGHT_API_STORE_DOCUMENT_TEXT"] = "false"
    config_module.clear_config_cache()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("HINDSIGHT_API_STORE_DOCUMENT_TEXT", None)
        else:
            os.environ["HINDSIGHT_API_STORE_DOCUMENT_TEXT"] = original
        config_module.clear_config_cache()


@pytest.mark.asyncio
async def test_privacy_mode_nulls_text_but_keeps_memories(memory, request_context, store_document_text_disabled):
    """With the flag off, raw text is dropped but facts/recall still work."""
    bank_id = f"test_privacy_off_{datetime.now(timezone.utc).timestamp()}"
    document_id = "doc-privacy-001"

    try:
        unit_ids = await memory.retain_async(
            bank_id=bank_id,
            content=LONG_CONTENT,
            context="team overview",
            document_id=document_id,
            request_context=request_context,
        )

        # Pipeline still ran: facts were extracted and stored.
        assert len(unit_ids) > 0, "Facts should still be extracted in privacy mode"

        # documents.original_text is dropped (NULL).
        doc = await memory.get_document(document_id, bank_id, request_context=request_context)
        assert doc is not None
        assert doc["original_text"] is None, "Raw document text must not be stored"
        assert doc["memory_unit_count"] > 0, "Memory units should still be created"

        # chunks.chunk_text is blanked.
        chunks = await memory.list_document_chunks(
            bank_id=bank_id, document_id=document_id, request_context=request_context
        )
        assert chunks["total"] > 0, "Chunks should still be stored (for graph/structure)"
        for chunk in chunks["items"]:
            assert chunk["chunk_text"] == "", "Raw chunk text must not be stored"

        # Recall is unaffected — it reads from memory_units, not original_text.
        result = await memory.recall_async(
            bank_id=bank_id,
            query="Where does Alice work?",
            budget=Budget.LOW,
            max_tokens=500,
            request_context=request_context,
        )
        assert len(result.results) > 0, "Recall must still return facts in privacy mode"
    finally:
        await memory.delete_bank(bank_id, request_context=request_context)


@pytest.mark.asyncio
async def test_default_mode_stores_text(memory, request_context):
    """By default (flag on) raw document and chunk text are persisted."""
    bank_id = f"test_privacy_on_{datetime.now(timezone.utc).timestamp()}"
    document_id = "doc-privacy-002"

    try:
        await memory.retain_async(
            bank_id=bank_id,
            content=LONG_CONTENT,
            context="team overview",
            document_id=document_id,
            request_context=request_context,
        )

        doc = await memory.get_document(document_id, bank_id, request_context=request_context)
        assert doc is not None
        assert doc["original_text"] is not None
        assert "Alice Johnson" in doc["original_text"]

        chunks = await memory.list_document_chunks(
            bank_id=bank_id, document_id=document_id, request_context=request_context
        )
        assert chunks["total"] > 0
        assert any(chunk["chunk_text"] for chunk in chunks["items"]), "Chunk text should be stored by default"
    finally:
        await memory.delete_bank(bank_id, request_context=request_context)


@pytest.mark.asyncio
async def test_append_mode_rejected_in_privacy_mode(memory, request_context, store_document_text_disabled):
    """update_mode='append' must be rejected when document text storage is disabled.

    Append rebuilds the document by reading back the stored original_text; with
    storage off there is nothing to read, so appending would silently drop the
    prior content. The pipeline rejects it instead of losing data.
    """
    bank_id = f"test_append_privacy_{datetime.now(timezone.utc).timestamp()}"

    with pytest.raises(ValueError, match="update_mode='append' is not supported"):
        await memory.retain_batch_async(
            bank_id=bank_id,
            contents=[
                {
                    "content": "Some content",
                    "document_id": "doc-append-privacy",
                    "update_mode": "append",
                }
            ],
            request_context=request_context,
        )


def test_reflect_excludes_expand_tool_when_text_disabled():
    """The reflect 'expand' tool (get chunk/document source text) is dropped in privacy mode."""
    with_text = {t["function"]["name"] for t in get_reflect_tools(include_expand=True)}
    without_text = {t["function"]["name"] for t in get_reflect_tools(include_expand=False)}

    assert "expand" in with_text, "expand should be available by default"
    assert "expand" not in without_text, "expand must be excluded when document text is not stored"
    # Other reflect tools are unaffected.
    assert "recall" in without_text
    assert "done" in without_text
