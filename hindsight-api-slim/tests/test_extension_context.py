"""Verify ExtensionContext exposes the webhook_manager + current_schema
attributes any out-of-tree extension may read when firing webhook events
or running multi-tenant DB queries."""


def test_extension_context_exposes_webhook_manager() -> None:
    """Verify webhook_manager attribute exists on ExtensionContext."""
    from hindsight_api.extensions.context import DefaultExtensionContext

    ctx = DefaultExtensionContext(database_url="postgresql://localhost/test")
    assert hasattr(ctx, "webhook_manager")
    assert ctx.webhook_manager is None  # default when not set


def test_extension_context_exposes_current_schema() -> None:
    """Verify current_schema attribute exists on ExtensionContext."""
    from hindsight_api.extensions.context import DefaultExtensionContext

    ctx = DefaultExtensionContext(database_url="postgresql://localhost/test")
    assert hasattr(ctx, "current_schema")
    assert ctx.current_schema is None  # default when not set


def test_extension_context_attributes_are_writable() -> None:
    """The engine sets these per-request after construction; verify both attrs
    are simple writable attributes (not @property-only)."""
    from hindsight_api.extensions.context import DefaultExtensionContext

    ctx = DefaultExtensionContext(database_url="postgresql://localhost/test")
    sentinel_mgr = object()
    ctx.webhook_manager = sentinel_mgr
    ctx.current_schema = "tenant_abc"
    assert ctx.webhook_manager is sentinel_mgr
    assert ctx.current_schema == "tenant_abc"


# ---------------------------------------------------------------------------
# Engine wiring tests
# ---------------------------------------------------------------------------


def _make_minimal_engine():
    """Return a MemoryEngine constructed with minimal env-level config.

    We patch out heavy dependencies (embeddings, LLM) so the __init__ runs
    without network calls or GPU loading.
    """
    import os
    from unittest.mock import MagicMock, patch

    mock_embeddings = MagicMock()
    mock_embeddings.dimension = 384

    # Use "none" provider so no API key is required and LLM calls are skipped.
    with patch.dict(
        os.environ,
        {
            "HINDSIGHT_API_LLM_PROVIDER": "none",
            "HINDSIGHT_API_LLM_MODEL": "none",
            "HINDSIGHT_API_LLM_API_KEY": "test-key",
        },
        clear=False,
    ):
        from hindsight_api.config import clear_config_cache
        from hindsight_api.engine.memory_engine import MemoryEngine

        clear_config_cache()
        engine = MemoryEngine(
            db_url="postgresql://localhost/hindsight_test",
            embeddings=mock_embeddings,
        )
    return engine


def test_engine_memory_defense_has_context() -> None:
    """After __init__, _memory_defense must have a valid context set."""
    engine = _make_minimal_engine()
    # context property raises RuntimeError if _context is None
    ctx = engine._memory_defense.context
    assert ctx is not None


def test_engine_memory_defense_context_is_ext_ctx() -> None:
    """The context on _memory_defense must be the same object as engine._ext_ctx."""
    engine = _make_minimal_engine()
    assert engine._memory_defense._context is engine._ext_ctx


def test_engine_ext_ctx_webhook_manager_initially_none() -> None:
    """Before initialize(), webhook_manager on ext_ctx is None (set in initialize())."""
    engine = _make_minimal_engine()
    assert engine._ext_ctx.webhook_manager is None


def test_engine_ext_ctx_current_schema_propagation() -> None:
    """Writing _ext_ctx.current_schema propagates the value correctly."""
    engine = _make_minimal_engine()
    engine._ext_ctx.current_schema = "tenant_x"
    # The same object is referenced by _memory_defense.context
    assert engine._memory_defense.context.current_schema == "tenant_x"
