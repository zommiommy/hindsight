"""Configuration management for the Hindsight Cline integration.

Loads settings from settings.json (plugin defaults) merged with a user
config file and environment variable overrides. Lean v1 schema — no daemon
or chunked-retain keys (see the integration README for the full rationale).
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

DEFAULTS = {
    # Recall
    "autoRecall": True,
    "recallBudget": "mid",
    "recallMaxTokens": 1024,
    "recallTimeout": 10,
    "recallTypes": ["world", "experience"],
    "recallContextTurns": 1,
    "recallMaxQueryChars": 800,
    "recallPromptPreamble": (
        "Relevant memories from past conversations (prioritize recent when "
        "conflicting). Only use memories that are directly useful to continue "
        "this task; ignore the rest:"
    ),
    # Retain
    "autoRetain": True,
    "retainContext": "cline",
    "retainTags": ["{task_id}"],
    "retainMetadata": {},
    "retainTimeout": 15,
    # Connection
    "hindsightApiUrl": None,
    "hindsightApiToken": None,
    "apiPort": 9077,
    # Bank
    "bankId": "cline",
    "bankIdPrefix": "",
    "dynamicBankId": False,
    "dynamicBankGranularity": ["agent", "project"],
    "bankMission": (
        "You are a Cline AI coding assistant. Focus on technical decisions, "
        "code changes, debugging sessions, architectural choices, and project "
        "context relevant to the user's work."
    ),
    "retainMission": (
        "Extract technical decisions, code patterns, debugging solutions, user "
        "preferences, project context, and architectural choices. Ignore "
        "routine greetings and transient operational details."
    ),
    "agentName": "cline",
    # Misc
    "debug": False,
}

# Map env var names to config keys and their types.
ENV_OVERRIDES = {
    "HINDSIGHT_API_URL": ("hindsightApiUrl", str),
    "HINDSIGHT_API_TOKEN": ("hindsightApiToken", str),
    "HINDSIGHT_BANK_ID": ("bankId", str),
    "HINDSIGHT_AGENT_NAME": ("agentName", str),
    "HINDSIGHT_AUTO_RECALL": ("autoRecall", bool),
    "HINDSIGHT_AUTO_RETAIN": ("autoRetain", bool),
    "HINDSIGHT_RECALL_BUDGET": ("recallBudget", str),
    "HINDSIGHT_RECALL_MAX_TOKENS": ("recallMaxTokens", int),
    "HINDSIGHT_RECALL_TIMEOUT": ("recallTimeout", int),
    "HINDSIGHT_RECALL_MAX_QUERY_CHARS": ("recallMaxQueryChars", int),
    "HINDSIGHT_RECALL_CONTEXT_TURNS": ("recallContextTurns", int),
    "HINDSIGHT_API_PORT": ("apiPort", int),
    "HINDSIGHT_DYNAMIC_BANK_ID": ("dynamicBankId", bool),
    "HINDSIGHT_BANK_MISSION": ("bankMission", str),
    "HINDSIGHT_DEBUG": ("debug", bool),
}


def find_settings_path() -> Optional[Path]:
    """Locate the plugin's settings.json next to this lib directory.

    The repo and installed layouts differ: in the repo settings.json sits at
    the integration root (two levels above lib/), while install.py copies it
    into the hooks dir (one level above lib/). Search upward and take the
    first hit so both layouts work without special-casing.
    """
    base = Path(__file__).resolve()
    for up in (1, 2, 3):
        candidate = base.parents[up] / "settings.json"
        if candidate.exists():
            return candidate
    return None


def _cast_env(value: str, typ):
    """Cast an environment-variable string to the target type; None on failure."""
    try:
        if typ is bool:
            return value.lower() in ("true", "1", "yes")
        if typ is int:
            return int(value)
        return value
    except (ValueError, AttributeError):
        return None


def _load_settings_file(path: str, config: dict) -> None:
    """Merge a settings.json file into config in-place. Silently skips if missing."""
    if not path or not os.path.exists(path):
        return
    try:
        with open(path) as f:
            file_config = json.load(f)
        config.update({k: v for k, v in file_config.items() if v is not None})
    except (json.JSONDecodeError, OSError) as e:
        debug_log(config, f"Failed to load {path}: {e}")


def load_config() -> dict:
    """Load plugin configuration.

    Loading order (later entries win):
      1. Built-in defaults
      2. Plugin settings.json (found via find_settings_path)
      3. User config (~/.hindsight/cline.json) — stable across updates
      4. Environment variable overrides
    """
    config = dict(DEFAULTS)

    settings_path = find_settings_path()
    if settings_path is not None:
        _load_settings_file(str(settings_path), config)

    user_config_path = os.path.join(os.path.expanduser("~"), ".hindsight", "cline.json")
    _load_settings_file(user_config_path, config)

    for env_name, (key, typ) in ENV_OVERRIDES.items():
        val = os.environ.get(env_name)
        if val is not None:
            cast_val = _cast_env(val, typ)
            if cast_val is not None:
                config[key] = cast_val

    return config


def debug_log(config: dict, *args):
    """Log to stderr if debug mode is enabled."""
    if config.get("debug"):
        print("[Hindsight]", *args, file=sys.stderr)
