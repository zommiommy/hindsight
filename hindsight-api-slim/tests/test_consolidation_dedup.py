"""Deterministic unit tests for the consolidation duplicate-create guard.

These exercise the dedup decision directly (no LLM, no DB), so they reliably
guard the fix in CI — unlike the real-LLM integration test, which only triggers
the path stochastically.
"""

from dataclasses import dataclass

from hindsight_api.engine.consolidation.consolidator import _duplicate_create_target, _norm_obs_text


@dataclass
class _FakeObs:
    id: str
    text: str


def _shown(*observations: _FakeObs) -> dict[str, _FakeObs]:
    return {_norm_obs_text(o.text): o for o in observations}


def test_norm_obs_text_collapses_whitespace_and_case() -> None:
    assert _norm_obs_text("  The  User  likes BASIL.\n") == "the user likes basil."
    assert _norm_obs_text(None) == ""


def test_create_matching_shown_observation_is_duplicate() -> None:
    shown = _shown(_FakeObs(id="11111111-aaaa", text="User waters the herbs early in the morning."))
    # Same text with different whitespace/case still matches.
    target = _duplicate_create_target("user waters the herbs early in the morning.", shown, set())
    assert target is not None
    assert target.startswith("shown observation 11111111")


def test_create_matching_inresponse_update_is_duplicate() -> None:
    update_texts = {_norm_obs_text("Mint is kept in its own separate bed.")}
    target = _duplicate_create_target("Mint is kept in its own separate bed.", {}, update_texts)
    assert target == "an UPDATE in this response"


def test_novel_create_is_not_duplicate() -> None:
    shown = _shown(_FakeObs(id="22222222-bbbb", text="User waters the herbs early in the morning."))
    assert _duplicate_create_target("Rosemary is drought-tolerant.", shown, set()) is None
    assert _duplicate_create_target("", {}, set()) is None
