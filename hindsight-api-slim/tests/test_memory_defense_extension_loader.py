import pytest

from hindsight_api.extensions.builtin.memory_defense_lite import MemoryDefenseLiteExtension
from hindsight_api.extensions.loader import ExtensionLoadError, load_extension
from hindsight_api.extensions.memory_defense import MemoryDefenseExtension


def test_lite_is_default_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("HINDSIGHT_API_MEMORY_DEFENSE_EXTENSION", raising=False)
    ext = load_extension("MEMORY_DEFENSE", MemoryDefenseExtension) or MemoryDefenseLiteExtension({})
    assert isinstance(ext, MemoryDefenseLiteExtension)


def test_custom_extension_loaded_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "HINDSIGHT_API_MEMORY_DEFENSE_EXTENSION",
        "hindsight_api.extensions.builtin.memory_defense_lite:MemoryDefenseLiteExtension",
    )
    ext = load_extension("MEMORY_DEFENSE", MemoryDefenseExtension)
    assert isinstance(ext, MemoryDefenseLiteExtension)


def test_malformed_path_raises(monkeypatch) -> None:
    monkeypatch.setenv("HINDSIGHT_API_MEMORY_DEFENSE_EXTENSION", "no_colon_here")
    with pytest.raises(ExtensionLoadError):
        load_extension("MEMORY_DEFENSE", MemoryDefenseExtension)


def test_non_subclass_raises(monkeypatch) -> None:
    monkeypatch.setenv("HINDSIGHT_API_MEMORY_DEFENSE_EXTENSION", "builtins:dict")
    with pytest.raises(ExtensionLoadError):
        load_extension("MEMORY_DEFENSE", MemoryDefenseExtension)
