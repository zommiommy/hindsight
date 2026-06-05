"""Memory Defense Lite — open-source-tier extension shipping with hindsight-api-slim.

Implements ONLY the secrets/PII redaction subset of OWASP ASI06 defense via
the ``sensitive_data`` detector — the single detector ``parse_policy`` accepts.
Block and quarantine actions remain valid in the policy schema, but Lite
cannot enforce them: when a policy lists ``action: block`` or
``action: quarantine`` for ``sensitive_data``, Lite silently downgrades the
action to ``redact`` so a policy authored against a richer extension still
behaves sanely on a self-hosted dev environment.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_memory_guard.detectors.leakage import SensitiveDataDetector

from hindsight_api.extensions.memory_defense import (
    DefenseAction,
    DefenseDecision,
    DefensePolicy,
    MemoryDefenseExtension,
    apply_redaction,
)

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class MemoryDefenseLiteExtension(MemoryDefenseExtension):
    """Default Memory Defense — redaction-only. Built in to hindsight-api-slim."""

    def __init__(self, config: dict[str, str]):
        super().__init__(config)
        self._detector = SensitiveDataDetector()

    async def screen(
        self,
        *,
        policy: DefensePolicy,
        bank_id: str,
        document_id: str | None,
        content: str,
        tags: list[str],
    ) -> DefenseDecision:
        if not policy.enabled:
            return DefenseDecision(action=DefenseAction.ALLOW)

        # Lite only ever runs the sensitive_data detector. If the policy doesn't
        # include a rule for it, we have nothing to do.
        rule = next((r for r in policy.rules if r.on == "sensitive_data"), None)
        if rule is None:
            return DefenseDecision(action=DefenseAction.ALLOW)

        # Detection gate: use OUR extended pattern set (apply_redaction) as the
        # primary match check instead of OWASP's narrower detector. apply_redaction
        # covers ~33 secret types; OWASP SensitiveDataDetector only covers ~13.
        # If we don't gate on our broader set, secret types we know how to scrub
        # (xAI, Groq, HF, Stripe, Twilio, DB URLs, etc.) would pass through
        # unredacted because OWASP doesn't recognize their prefixes.
        key = self._synthesize_key(tags, document_id, bank_id)
        redacted = apply_redaction(content)

        if redacted != content:
            # Our regex set matched and produced a redacted version.
            detector_label = "sensitive_data"
            severity_value = "high"
            categories: list[str] = []
            message = "Sensitive data pattern matched by Hindsight redactor"
        else:
            # Fall back to the upstream detector for anything our regex set might
            # miss (e.g. context-dependent patterns).
            result = self._detector.inspect(key, content, operation="write")
            if not result.matched:
                return DefenseDecision(action=DefenseAction.ALLOW)
            detector_label = result.detector
            severity_value = result.severity.value if result.severity else "low"
            categories = (result.metadata or {}).get("categories", [])
            message = result.message

        # Downgrade block to redact — lite cannot enforce it.
        chosen = rule.action
        if chosen is DefenseAction.BLOCK:
            logger.warning(
                "Memory Defense Lite cannot enforce action=%s for detector=sensitive_data; "
                "downgrading to 'redact'. Install hindsight-cloud for full enforcement.",
                chosen.value,
            )
            chosen = DefenseAction.REDACT

        return DefenseDecision(
            action=chosen,
            detector=detector_label,
            severity=severity_value,
            message=message,
            redacted_content=redacted if chosen is DefenseAction.REDACT else None,
            metadata={
                "hits": categories,
                "key": key,
                "extension": "lite",
            },
        )

    async def record_violation(
        self,
        conn: "asyncpg.Connection | None",
        *,
        bank_id: str,
        document_id: str | None,
        memory_unit_id: Any | None,
        decision: DefenseDecision,
        receipt_uri: str | None,
    ) -> None:
        # Lite doesn't persist security_events. Log for visibility.
        logger.info(
            "memory_defense_lite decision bank=%s detector=%s action=%s",
            bank_id,
            decision.detector,
            decision.action.value,
        )

    @staticmethod
    def _synthesize_key(tags: list[str], document_id: str | None, bank_id: str) -> str:
        for t in tags:
            if ":" in t:
                ns = t.split(":", 1)[0]
                return f"{ns}:{document_id or bank_id}"
        return f"memory:{document_id or bank_id}"
