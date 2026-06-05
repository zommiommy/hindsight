"""Memory Defense extension contract and shared policy types.

Lives in extensions/ (not engine/) because it defines the public contract
between the retain orchestrator and any installed Memory Defense extension —
the same shape as TenantExtension and OperationValidatorExtension.

api-slim ships the :class:`MemoryDefenseExtension` protocol and a Lite default
that scrubs the ``sensitive_data`` detector. Any richer policy enforcement
(block, additional detectors, security_events persistence) is provided by a
separate extension that subclasses this protocol.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from agent_memory_guard import Policy as OwaspPolicy
from agent_memory_guard.events import Action as OwaspAction
from agent_memory_guard.events import Severity as OwaspSeverity
from agent_memory_guard.policies.policy import PolicyRule as OwaspPolicyRule

from hindsight_api.extensions.base import Extension

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class DefenseAction(str, Enum):
    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"


_VALID_ACTIONS = {a.value for a in DefenseAction}
_VALID_SEVERITIES = {"low", "medium", "high", "critical"}

# Canonical set of detector identifiers that are valid as ``policy.rules[*].on``.
#
# Lite (the OSS default extension) only enforces ``sensitive_data``. The other
# names are reserved for Cloud-tier extensions (``prompt_injection``,
# ``size_anomaly``, ``protected_keys``, ``detect_secrets``, ``base64_decode``,
# ``llm_screen``). api-slim's parser accepts the full union so cloud-style
# policies pass through cleanly without 422'ing at PATCH or retain time;
# extensions enforce their own entitlement/dispatch semantics, and Lite
# silently ignores rules it cannot enforce.
_VALID_DETECTORS = {
    "sensitive_data",
    "prompt_injection",
    "size_anomaly",
    "protected_keys",
    "detect_secrets",
    "base64_decode",
    "llm_screen",
}


@dataclass(frozen=True)
class PolicyRule:
    on: str
    action: DefenseAction
    min_severity: Literal["low", "medium", "high", "critical"] = "low"


@dataclass(frozen=True)
class DefensePolicy:
    enabled: bool = False
    default_action: DefenseAction = DefenseAction.ALLOW
    protected_tag_namespaces: tuple[str, ...] = ()
    immutable_tag_namespaces: tuple[str, ...] = ()
    rules: tuple[PolicyRule, ...] = ()
    detector_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class DefenseDecision:
    action: DefenseAction
    detector: str | None = None
    severity: str | None = None
    message: str = ""
    redacted_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_policy(raw: dict | None) -> DefensePolicy:
    """Parse a raw bank-config dict into a frozen DefensePolicy.

    Raises ValueError for unknown actions or severities; the HTTP layer
    converts those into a 422 response.
    """
    if raw is None:
        return DefensePolicy()

    default_action_raw = raw.get("default_action", "allow")
    if default_action_raw not in _VALID_ACTIONS:
        raise ValueError(f"invalid default_action {default_action_raw!r}")

    rules: list[PolicyRule] = []
    for item in raw.get("rules", []) or []:
        on_raw = item.get("on")
        if on_raw not in _VALID_DETECTORS:
            raise ValueError(f"invalid on {on_raw!r}; must be one of {sorted(_VALID_DETECTORS)}")
        action_raw = item.get("action")
        if action_raw not in _VALID_ACTIONS:
            raise ValueError(f"invalid action {action_raw!r}; must be one of {sorted(_VALID_ACTIONS)}")
        severity = item.get("min_severity", "low")
        if severity not in _VALID_SEVERITIES:
            raise ValueError(f"invalid min_severity {severity!r}")
        rules.append(PolicyRule(on=on_raw, action=DefenseAction(action_raw), min_severity=severity))

    return DefensePolicy(
        enabled=bool(raw.get("enabled", False)),
        default_action=DefenseAction(default_action_raw),
        protected_tag_namespaces=tuple(raw.get("protected_tag_namespaces", ()) or ()),
        immutable_tag_namespaces=tuple(raw.get("immutable_tag_namespaces", ()) or ()),
        rules=tuple(rules),
        detector_overrides=dict(raw.get("detector_overrides", {}) or {}),
    )


def to_owasp_policy(policy: DefensePolicy) -> OwaspPolicy:
    return OwaspPolicy(
        default_action=OwaspAction(policy.default_action.value),
        protected_keys=tuple(f"{ns}:*" for ns in policy.protected_tag_namespaces),
        immutable_keys=tuple(f"{ns}:*" for ns in policy.immutable_tag_namespaces),
        rules=[
            OwaspPolicyRule(
                name=f"{r.on}_{r.action.value}",
                on=r.on,
                action=OwaspAction(r.action.value),
                min_severity=OwaspSeverity(r.min_severity),
            )
            for r in policy.rules
        ],
    )


# Secret/PII redaction — shared between lite and any richer extension so the
# substitution is identical regardless of which extension is loaded.
#
# Scope: high-confidence patterns with unambiguous prefixes (low false-positive
# rate). Context-dependent matches (e.g. Cohere/Mistral keys that only stand
# out near surrounding "cohere"/"mistral" tokens) are NOT covered by pure
# regex — operators who need that should layer a context-aware secret
# scanner (detect-secrets, trufflehog) on top.
#
# Order matters: more-specific patterns first so broader ones don't consume
# substrings partially. Example: `sk-ant-...` and `sk-proj-...` must run
# before the generic `sk-...` pattern.
_REDACTION_PATTERNS: list[tuple[str, str]] = [
    # --- AI / LLM providers ---
    ("anthropic_key", r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    ("openai_project_key", r"\bsk-proj-[A-Za-z0-9_-]{48,}\b"),
    ("openai_admin_key", r"\bsk-admin-[A-Za-z0-9_-]{40,}\b"),
    ("openai_key", r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("google_oauth_token", r"\bya29\.[0-9A-Za-z_-]{20,}\b"),
    ("xai_key", r"\bxai-[A-Za-z0-9]{40,}\b"),
    ("groq_key", r"\bgsk_[A-Za-z0-9]{20,}\b"),
    ("huggingface_token", r"\bhf_[A-Za-z0-9]{30,}\b"),
    ("replicate_token", r"\br8_[A-Za-z0-9]{30,}\b"),
    ("perplexity_key", r"\bpplx-[A-Za-z0-9]{40,}\b"),
    ("databricks_token", r"\bdapi[A-Za-z0-9]{32}\b"),
    # --- Cloud providers ---
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("aws_session_token", r"\bASIA[0-9A-Z]{16}\b"),
    (
        "aws_secret_key",
        r"(?i)aws(.{0,20})?(secret|private)?[\s_-]?access[\s_-]?key[\s_-]?[:=][\s\"']*([A-Za-z0-9/+=]{40})",
    ),
    ("digitalocean_token", r"\bdop_v1_[a-f0-9]{64}\b"),
    # --- Source control & CI ---
    ("github_fg_pat", r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    ("github_token", r"\bghp_[A-Za-z0-9]{36}\b"),
    ("github_app_token", r"\bghs_[A-Za-z0-9]{36}\b"),
    ("github_user_token", r"\bghu_[A-Za-z0-9]{36}\b"),
    ("github_refresh", r"\bghr_[A-Za-z0-9]{36}\b"),
    ("github_oauth", r"\bgho_[A-Za-z0-9]{36}\b"),
    ("gitlab_pat", r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    ("npm_token", r"\bnpm_[A-Za-z0-9]{30,}\b"),
    ("pypi_token", r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{20,}\b"),
    # --- Payment processors ---
    ("stripe_secret", r"\bsk_(?:live|test)_[A-Za-z0-9]{20,}\b"),
    ("stripe_restricted", r"\brk_(?:live|test)_[A-Za-z0-9]{20,}\b"),
    ("square_token", r"\bsq0[a-z]{3}-[A-Za-z0-9_-]{22,}\b"),
    ("braintree_token", r"\baccess_token\$production\$[a-z0-9]{16}\$[a-f0-9]{32}\b"),
    # --- Communication / email ---
    ("slack_token", r"\bxox[abpr]-[0-9A-Za-z-]{10,}\b"),
    ("slack_webhook", r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]{8,}/B[A-Za-z0-9_]{8,}/[A-Za-z0-9_]{20,}"),
    ("twilio_api_key", r"\bSK[0-9a-fA-F]{32}\b"),
    ("twilio_account_sid", r"\bAC[0-9a-fA-F]{32}\b"),
    ("sendgrid_key", r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b"),
    ("mailgun_key", r"\bkey-[A-Za-z0-9]{32}\b"),
    ("discord_bot", r"\b[MNO][A-Za-z0-9]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}\b"),
    ("telegram_bot", r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b"),
    # --- Commerce ---
    ("shopify_token", r"\bshpat_[a-fA-F0-9]{32}\b"),
    # --- Database connection strings (creds embedded in URL) ---
    ("db_url_postgres", r"postgres(?:ql)?://[^\s:/@]+:[^\s/@]+@[^\s]+"),
    ("db_url_mysql", r"mysql://[^\s:/@]+:[^\s/@]+@[^\s]+"),
    ("db_url_mongodb", r"mongodb(?:\+srv)?://[^\s:/@]+:[^\s/@]+@[^\s]+"),
    # --- Private keys & generic credentials ---
    ("private_key_pem", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY( BLOCK)?-----"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    # --- PII (US-centric defaults; can be tuned per deployment) ---
    # NOTE: credit_card regex is intentionally narrowed to 13-19 digits with
    # exact separators to reduce false positives on long product IDs.
    ("credit_card", r"\b(?:\d{4}[ -]?){3}\d{1,4}\b"),
    ("ssn_us", r"\b\d{3}-\d{2}-\d{4}\b"),
]
_COMPILED_REDACTIONS: list[tuple[str, re.Pattern]] = [
    (label, re.compile(pattern)) for label, pattern in _REDACTION_PATTERNS
]


def apply_redaction(content: str) -> str:
    """Scrub known secret/PII patterns from content with [REDACTED:type] markers.

    Covers the same pattern set OWASP SensitiveDataDetector matches by default,
    so anything the detector flags is also scrubbed.
    """
    for label, pattern in _COMPILED_REDACTIONS:
        content = pattern.sub(f"[REDACTED:{label}]", content)
    return content


class MemoryDefenseExtension(Extension, ABC):
    """Abstract base for Memory Defense extensions.

    Implementations decide whether to allow, redact, or block a given retain
    item by inspecting its content/tags against a per-bank policy. They also
    persist any side effects (security_events rows, webhook events, etc.)
    themselves — the orchestrator delegates the full decision lifecycle to
    the extension.
    """

    @abstractmethod
    async def screen(
        self,
        *,
        policy: DefensePolicy,
        bank_id: str,
        document_id: str | None,
        content: str,
        tags: list[str],
    ) -> DefenseDecision:
        """Inspect content under the given policy and return a decision."""
        ...

    @abstractmethod
    async def record_violation(
        self,
        conn: "asyncpg.Connection",
        *,
        bank_id: str,
        document_id: str | None,
        memory_unit_id: Any | None,
        decision: DefenseDecision,
        receipt_uri: str | None,
    ) -> None:
        """Persist a security event and emit any side effects (webhook, SIEM, etc.).

        Called once per non-ALLOW decision. Implementations that don't track
        events (e.g. lite) can no-op.
        """
        ...
