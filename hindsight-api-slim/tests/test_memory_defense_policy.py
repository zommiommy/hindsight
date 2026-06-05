"""Memory Defense policy parsing — replaces test_memory_guard_policy.py."""

import pytest

from hindsight_api.extensions.memory_defense import (
    DefenseAction,
    parse_policy,
)


def test_parse_minimal_policy() -> None:
    policy = parse_policy({"enabled": True})
    assert policy.enabled is True
    assert policy.default_action is DefenseAction.ALLOW
    assert policy.rules == ()


def test_parse_full_policy() -> None:
    policy = parse_policy(
        {
            "enabled": True,
            "default_action": "allow",
            "protected_tag_namespaces": ["system", "identity"],
            "rules": [
                {"on": "sensitive_data", "action": "redact"},
            ],
        }
    )
    assert {r.on for r in policy.rules} == {"sensitive_data"}
    assert policy.protected_tag_namespaces == ("system", "identity")


def test_invalid_action_raises() -> None:
    # Use a valid ``on`` so the parser progresses to action validation.
    with pytest.raises(ValueError, match="action"):
        parse_policy({"enabled": True, "rules": [{"on": "sensitive_data", "action": "lol"}]})


def test_invalid_default_action_raises() -> None:
    with pytest.raises(ValueError, match="default_action"):
        parse_policy({"enabled": True, "default_action": "nuke_from_orbit"})


def test_disabled_policy_is_inert() -> None:
    policy = parse_policy({"enabled": False, "rules": [{"on": "sensitive_data", "action": "redact"}]})
    assert policy.enabled is False


def test_defense_action_string_round_trip() -> None:
    assert DefenseAction("redact") is DefenseAction.REDACT
    assert DefenseAction.BLOCK.value == "block"


@pytest.mark.parametrize(
    "detector",
    [
        "sensitive_data",
        "prompt_injection",
        "size_anomaly",
        "protected_keys",
        "detect_secrets",
        "base64_decode",
        "llm_screen",
    ],
)
def test_parse_policy_accepts_full_detector_union(detector: str) -> None:
    """api-slim's parser accepts the full 7-detector vocabulary so cloud-style
    policies pass through without 422'ing at PATCH or retain. Extensions (Lite,
    Cloud) enforce dispatch and entitlement semantics; the parser is permissive."""
    policy = parse_policy({"enabled": True, "rules": [{"on": detector, "action": "redact"}]})
    assert len(policy.rules) == 1
    assert policy.rules[0].on == detector


def test_parse_policy_rejects_unknown_detector() -> None:
    with pytest.raises(ValueError, match="invalid on"):
        parse_policy({"enabled": True, "rules": [{"on": "nope", "action": "block"}]})


def test_parse_policy_accepts_block_action_on_sensitive_data() -> None:
    """Block is a valid action in the schema; Lite downgrades it at screen
    time, but the parser must accept it."""
    policy = parse_policy(
        {
            "enabled": True,
            "default_action": "allow",
            "rules": [
                {"on": "sensitive_data", "action": "block"},
            ],
            "detector_overrides": {"sensitive_data": {"min_severity": "high"}},
        }
    )
    assert policy.rules[0].action is DefenseAction.BLOCK
    assert policy.detector_overrides == {"sensitive_data": {"min_severity": "high"}}
