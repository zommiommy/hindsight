import pytest
from hindsight_api.extensions.memory_defense import parse_policy


def test_parse_policy_rejects_quarantine_action_on_rule():
    raw = {
        "enabled": True,
        "rules": [{"on": "size_anomaly", "action": "quarantine"}],
    }
    with pytest.raises(ValueError, match="invalid action"):
        parse_policy(raw)


def test_parse_policy_rejects_quarantine_default_action():
    raw = {"enabled": True, "default_action": "quarantine"}
    with pytest.raises(ValueError, match="invalid default_action"):
        parse_policy(raw)


def test_parse_policy_accepts_block_redact_allow():
    raw = {
        "enabled": True,
        "default_action": "allow",
        "rules": [
            {"on": "sensitive_data", "action": "redact"},
            {"on": "prompt_injection", "action": "block"},
        ],
    }
    policy = parse_policy(raw)
    assert policy.enabled is True
    assert len(policy.rules) == 2
