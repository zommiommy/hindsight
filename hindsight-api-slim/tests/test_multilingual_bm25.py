"""Tests for multilingual BM25 wiring.

Covers:
- ``HINDSIGHT_API_RETAIN_OUTPUT_LANGUAGE`` directive injection in the fact
  extraction system prompt.
- The new alembic migration's structural shape (chains off the right head).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from hindsight_api.engine.retain.fact_extraction import _build_extraction_prompt_and_schema


def _baseline_config() -> MagicMock:
    """Mock config with the minimal fields needed by _build_extraction_prompt_and_schema."""
    config = MagicMock()
    config.entity_labels = None
    config.entities_allow_free_form = True
    config.retain_extraction_mode = "concise"
    config.retain_extract_causal_links = False
    config.retain_mission = None
    config.retain_custom_instructions = None
    config.retain_output_language = None
    return config


def test_retain_output_language_unset_does_not_inject_directive():
    config = _baseline_config()
    config.retain_output_language = None

    prompt, _ = _build_extraction_prompt_and_schema(config)

    assert "Respond exclusively in" not in prompt
    assert "Translate any source content" not in prompt


def test_retain_output_language_injects_directive():
    config = _baseline_config()
    config.retain_output_language = "Japanese"

    prompt, _ = _build_extraction_prompt_and_schema(config)

    assert "Respond exclusively in Japanese" in prompt
    assert "Translate any source content into Japanese" in prompt


def test_retain_output_language_directive_appears_after_base_prompt():
    """The directive is appended at the end so mode-specific guidelines are
    still respected — the LLM reads them, then applies the language constraint."""
    config = _baseline_config()
    config.retain_output_language = "Spanish"

    prompt, _ = _build_extraction_prompt_and_schema(config)

    directive_idx = prompt.find("Respond exclusively in Spanish")
    assert directive_idx > 0
    # A non-trivial extraction prompt body precedes the directive.
    assert directive_idx > 100


def test_retain_output_language_works_with_custom_mode():
    """Custom extraction mode + retain_output_language: directive must still appear."""
    config = _baseline_config()
    config.retain_extraction_mode = "custom"
    config.retain_custom_instructions = "Extract only product mentions."
    config.retain_output_language = "French"

    prompt, _ = _build_extraction_prompt_and_schema(config)

    assert "Extract only product mentions." in prompt
    assert "Respond exclusively in French" in prompt


# ---------------------------------------------------------------------------
# Migration shape regression test
# ---------------------------------------------------------------------------


def test_configurable_bm25_language_migration_chains_off_head():
    """The new migration must descend from the head it was authored against.

    Tests that re-pointing the migration's down_revision wouldn't go
    unnoticed — it would silently break the chain on a fresh DB.
    """
    versions_dir = Path(__file__).resolve().parent.parent / "hindsight_api" / "alembic" / "versions"
    target = versions_dir / "p4q5r6s7t8u9_configurable_bm25_language.py"
    assert target.exists(), "configurable_bm25_language migration file is missing"

    src = target.read_text()
    assert 'revision: str = "p4q5r6s7t8u9"' in src
    assert 'down_revision: str | Sequence[str] | None = "m3rg3h3ad5f6"' in src
