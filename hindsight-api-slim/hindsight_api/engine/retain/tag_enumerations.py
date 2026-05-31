"""
Tag enumerations: caller-declared namespaced vocabularies for dynamic
tag classification during retain.

Distinct from entity_labels: tag_enumerations stay flat string tags on
the memory; they do not become entities and do not participate in the
knowledge graph.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model, model_validator


class TagEnumValue(BaseModel):
    value: str
    description: str = ""


class TagEnumeration(BaseModel):
    namespace: str
    description: str = ""
    type: Literal["value", "multi-values"] = "value"
    optional: bool = True
    values: list[TagEnumValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "TagEnumeration":
        if not self.namespace.strip():
            raise ValueError("tag_enumeration.namespace must be non-empty")
        if ":" in self.namespace:
            raise ValueError(
                "tag_enumeration.namespace must not contain ':' (reserved as the namespace/value separator)"
            )
        if not self.values:
            raise ValueError(f"tag_enumeration '{self.namespace}' requires at least one value")
        return self


class TagEnumerationsConfig(BaseModel):
    enumerations: list[TagEnumeration] = Field(default_factory=list)


def parse_tag_enumerations(raw: list | dict | None) -> TagEnumerationsConfig | None:
    """Parse raw config (list of dicts or {enumerations: [...]}) into the model.

    Returns None for None or empty input.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("enumerations", [])
    if not raw:
        return None
    enums = [TagEnumeration.model_validate(e) for e in raw]
    return TagEnumerationsConfig(enumerations=enums)


def merge_tag_enumerations(
    bank: TagEnumerationsConfig | None,
    per_retain: TagEnumerationsConfig | None,
) -> TagEnumerationsConfig | None:
    """Merge two configs by namespace; per-retain replaces bank on collision."""
    if bank is None and per_retain is None:
        return None
    by_ns: dict[str, TagEnumeration] = {}
    if bank is not None:
        for e in bank.enumerations:
            by_ns[e.namespace] = e
    if per_retain is not None:
        for e in per_retain.enumerations:
            by_ns[e.namespace] = e
    return TagEnumerationsConfig(enumerations=list(by_ns.values()))


def build_tag_enumerations_response_field(
    cfg: TagEnumerationsConfig | None,
) -> tuple[type, Any] | tuple[None, None]:
    """
    Build a (field_type, FieldInfo) pair to add to the fact-extraction
    response schema as the `tags` field.

    The field is a nested Pydantic model with one field per declared namespace:
    - type="value", optional=True  → Literal[...] | None
    - type="value", optional=False → Literal[...]
    - type="multi-values"          → list[Literal[...]]

    Returns (None, None) when there's nothing to classify.
    """
    if cfg is None or not cfg.enumerations:
        return None, None

    fields: dict[str, Any] = {}
    for e in cfg.enumerations:
        values = tuple(v.value for v in e.values if v.value)
        if not values:
            continue
        literal = Literal[values]  # type: ignore[valid-type]
        description = e.description or f"Classification on the {e.namespace} axis"
        if e.type == "multi-values":
            fields[e.namespace] = (
                list[literal],  # type: ignore[valid-type]
                Field(default_factory=list, description=description),
            )
        elif e.optional:
            fields[e.namespace] = (
                literal | None,  # type: ignore[valid-type]
                Field(default=None, description=description),
            )
        else:
            fields[e.namespace] = (literal, Field(description=description))

    if not fields:
        return None, None

    TagsModel = create_model("TagEnumerationAssignments", **fields)
    return (
        TagsModel,
        Field(
            default_factory=TagsModel,
            description=(
                "Enumerated-tag classification of this fact along each "
                "declared namespace. Omit or leave empty if nothing fits."
            ),
        ),
    )


def render_tag_enumerations_to_prompt_section(cfg: TagEnumerationsConfig | None) -> str:
    """Build the prompt section describing each enumeration to the extractor."""
    if cfg is None or not cfg.enumerations:
        return ""
    lines: list[str] = [
        "",
        "## Enumerated tag classification",
        "",
        "For each fact, classify it along each axis below using the `tags` "
        "object in your response. Keys are the namespaces; values must come "
        "from the allowed lists.",
        "",
    ]
    for e in cfg.enumerations:
        cardinality = (
            "(pick zero or more)"
            if e.type == "multi-values"
            else ("(pick one or omit)" if e.optional else "(pick exactly one)")
        )
        desc = f" — {e.description}" if e.description else ""
        lines.append(f"- `{e.namespace}` {cardinality}{desc}")
        for v in e.values:
            vdesc = f" — {v.description}" if v.description else ""
            lines.append(f"    - `{v.value}`{vdesc}")
    lines.append("")
    lines.append(
        "Only assign a value when the fact clearly fits its description. "
        "If nothing fits, leave the namespace empty (or omit it)."
    )
    return "\n".join(lines)


def assignments_to_tag_strings(
    assignments: dict[str, Any] | Any | None,
    cfg: TagEnumerationsConfig | None,
) -> list[str]:
    """Convert a parsed `tags` value from the LLM response into a flat list
    of lowercase `namespace:value` strings.

    Accepts either a plain dict (e.g., from raw JSON) or a Pydantic model
    instance (the dynamic TagEnumerationAssignments). Drops anything not in
    the configured vocabulary as defense in depth.
    """
    if not assignments or cfg is None:
        return []
    # Normalize Pydantic model -> dict
    if hasattr(assignments, "model_dump"):
        assignments = assignments.model_dump()
    if not isinstance(assignments, dict):
        return []
    valid: dict[str, set[str]] = {e.namespace: {v.value for v in e.values} for e in cfg.enumerations}
    out: list[str] = []
    for ns, picked in assignments.items():
        allowed = valid.get(ns)
        if allowed is None:
            continue
        items: list[str]
        if isinstance(picked, list):
            items = [str(p) for p in picked]
        elif picked is None or picked == "":
            items = []
        else:
            items = [str(picked)]
        for value in items:
            if value in allowed:
                out.append(f"{ns}:{value}".lower())
    return out
