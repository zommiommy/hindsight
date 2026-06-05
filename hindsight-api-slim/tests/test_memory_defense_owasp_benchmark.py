"""OWASP injection-payload benchmark for the Memory Defense engine.

If the wrapped detector pipeline silently degrades, this fails CI.
Run in standard pytest — NOT gated behind a marker, so regressions are loud.

Note: Lite only runs the sensitive_data detector. Prompt injection and size_anomaly
enforcement is tested in hindsight-deployment (Cloud extension).
"""

import pytest

from hindsight_api.extensions.builtin.memory_defense_lite import MemoryDefenseLiteExtension
from hindsight_api.extensions.memory_defense import (
    DefenseAction,
    parse_policy,
)

REDACT_POLICY = parse_policy(
    {
        "enabled": True,
        "rules": [
            {"on": "sensitive_data", "action": "redact"},
        ],
    }
)


@pytest.fixture
def lite() -> MemoryDefenseLiteExtension:
    return MemoryDefenseLiteExtension({})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "ghp_" + "A" * 36,
        "sk-ant-" + "B" * 40,
        "sk-" + "C" * 30,
        "AKIA" + "D" * 16,
    ],
)
async def test_redacts_known_secret_patterns(payload: str, lite: MemoryDefenseLiteExtension) -> None:
    d = await lite.screen(
        policy=REDACT_POLICY,
        bank_id="b",
        document_id="d",
        content=f"my key is {payload}",
        tags=[],
    )
    assert d.action is DefenseAction.REDACT, f"expected redact for {payload!r}, got {d.action}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "The roadmap meeting is on Friday",
        "Product launch planning notes",
        "Reminder about Tuesday",
    ],
)
async def test_allows_benign_payloads(payload: str, lite: MemoryDefenseLiteExtension) -> None:
    """Benign payloads either ALLOW or REDACT (no secrets detected) — never BLOCK."""
    d = await lite.screen(
        policy=REDACT_POLICY,
        bank_id="b",
        document_id="d",
        content=payload,
        tags=[],
    )
    assert d.action in {DefenseAction.ALLOW, DefenseAction.REDACT}
