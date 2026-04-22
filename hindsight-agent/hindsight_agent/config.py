"""Global config for hindsight-agent.

Config lives at ~/.hindsight-agent/config.json and maps agent IDs to their
Hindsight environment (bank, api url).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".hindsight-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AgentConfig:
    bank_id: str
    api_url: str
    harness: str
    workspace: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> AgentConfig:
        return AgentConfig(
            bank_id=d["bank_id"],
            api_url=d["api_url"],
            harness=d["harness"],
            workspace=d["workspace"],
        )


def load_config() -> dict[str, AgentConfig]:
    """Load the global config. Returns empty dict if no config exists."""
    if not CONFIG_FILE.exists():
        return {}
    raw = json.loads(CONFIG_FILE.read_text())
    return {
        agent_id: AgentConfig.from_dict(entry)
        for agent_id, entry in raw.get("agents", {}).items()
    }


def save_config(agents: dict[str, AgentConfig]) -> None:
    """Write the global config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    raw = {"agents": {k: v.to_dict() for k, v in agents.items()}}
    CONFIG_FILE.write_text(json.dumps(raw, indent=2) + "\n")


def get_agent(agent_id: str) -> AgentConfig:
    """Get config for a specific agent. Raises if not found."""
    agents = load_config()
    if agent_id not in agents:
        raise click_missing_agent(agent_id)
    return agents[agent_id]


def click_missing_agent(agent_id: str) -> SystemExit:
    import click

    raise click.ClickException(
        f"Agent '{agent_id}' not found. Run 'hindsight-agent setup' first."
    )
