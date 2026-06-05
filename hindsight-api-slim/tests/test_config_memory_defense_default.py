"""Test memory_defense_enabled_default static config field."""

from hindsight_api.config import HindsightConfig


def test_default_memory_defense_disabled(monkeypatch) -> None:
    """Default: memory_defense_enabled_default is False."""
    monkeypatch.delenv("HINDSIGHT_API_MEMORY_DEFENSE_ENABLED_DEFAULT", raising=False)
    cfg = HindsightConfig.from_env()
    assert cfg.memory_defense_enabled_default is False


def test_env_enables_memory_defense_default(monkeypatch) -> None:
    """Env var 'true' enables memory_defense_enabled_default."""
    monkeypatch.setenv("HINDSIGHT_API_MEMORY_DEFENSE_ENABLED_DEFAULT", "true")
    cfg = HindsightConfig.from_env()
    assert cfg.memory_defense_enabled_default is True


def test_memory_defense_enabled_default_is_not_in_configurable_fields() -> None:
    """Static field — must NOT be in _CONFIGURABLE_FIELDS so per-bank overrides reject it."""
    assert "memory_defense_enabled_default" not in HindsightConfig.get_configurable_fields()
