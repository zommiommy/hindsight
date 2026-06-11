"""Offline retention-stability lab.

The replay experiment proved task flips are 100% content-deterministic: given the right
recalled block the agent wins every time, and the entire treatment variance lives in the
retention pipeline's distillation draw (the temp-0 summariser emits differently-shaped
lessons even on byte-identical inputs). This lab iterates on that one component WITHOUT
running agents: it replays saved trajectories + official eval feedback through retention
variants N times and MEASURES lesson-shape stability.

The shape classifiers here are measurement only — they are never used to filter what gets
stored (a harness-side gate would rightly be criticised as gaming the benchmark). The
interventions under test are product-native: summariser prompt engineering and Hindsight
bank missions (retain_mission) steering server-side extraction.

Usage (from hindsight-dev/):
  benchmarks/swebench/.venv/bin/python -m benchmarks.swebench.retention_lab \
      --source benchmarks/swebench/results/pilot-django-retry-a2/treatment \
      --variants scoped,exemplar --reps 5
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Domain-neutral few-shot exemplars (deliberately NOT drawn from the study's tasks — using
# study content as exemplars would contaminate the very tasks being measured).
_EXEMPLAR_ADDENDUM = (
    "\n\nEXAMPLES of the required FAILED APPROACH shape (note: each binds the change to the "
    "exact method/file and names the failing tests, and never condemns the mechanism):\n"
    "GOOD: 'FAILED APPROACH: adding exponential-backoff retries in HttpClient.send "
    "(net/client.py) did not pass test_timeout_budget and test_idempotent_replay.'\n"
    "BAD (never write this): 'Avoid retry logic in the HTTP client; the real issue lies in "
    "the server-side timeout handling.' — this condemns a mechanism and redirects without "
    "evidence; the same retry mechanism may be the correct fix elsewhere.\n"
    "GOOD: 'FAILED APPROACH: widening the cache key with the session id in CacheMiddleware."
    "process_request (middleware/cache.py) did not pass test_cache_hit_ratio.'\n"
    "BAD (never write this): 'Cache-key changes are insufficient for this class of bug; "
    "prefer fixing invalidation instead.'"
)

# ---------------------------------------------------------------------------------------
# Shape measurement (offline metric, not a runtime filter)
# ---------------------------------------------------------------------------------------

_PRESCRIPTIVE = re.compile(r"\b(avoid|never|instead of|rather than|prefer|prioritize|insufficient|do not use)\b", re.I)
_REDIRECT = re.compile(r"\b(the (real )?(issue|cause|problem) (lies|is) in|does not work in general)\b", re.I)
_VERIFICATION_OK = re.compile(
    r"(reproduc|test module|test suite|runtests|git diff|cat -n|grep|inspect|verify|re-read|import the|diff is non-empty)",
    re.I,
)
_EDIT_TOOLING = re.compile(
    r"\b(sed|awk|ed|patch tools?|python scripts?|shell scripts?|editor|line-number|regex-based)\b", re.I
)
_CODE_SYMBOL = re.compile(r"[A-Za-z_]*\.\w+\(|[a-z_]+/[a-z_/]+\.py|\b[A-Z][a-z]+[A-Z][A-Za-z]+\b|\b[A-Z]{2,}\b")
_LOCATION_BOUND = re.compile(r"(applied in|in [`']?[A-Za-z_.]+\(|\([a-z_/]+\.py\)|[a-z_/]+\.py)")


def classify_line(line: str) -> str:
    """One lesson line -> shape class. Heuristic; calibrated against the runs where shape
    demonstrably decided the outcome (retry-a2 r1/r2/r3, scoped-r1)."""
    s = line.strip().lstrip("-• ").strip()
    if not s:
        return "empty"
    if s.upper().startswith("FAILED APPROACH"):
        return "failed_scoped" if _LOCATION_BOUND.search(s) else "failed_unscoped"
    prescriptive = _PRESCRIPTIVE.search(s) or _REDIRECT.search(s)
    if prescriptive:
        # Verification imperatives first: "run the test suite ... to avoid side effects" is
        # process advice, not a mechanism ban, even when it names a subsystem. The true bans
        # in the calibration set carry no verification language.
        if _VERIFICATION_OK.search(s):
            return "process_ok"
        if _CODE_SYMBOL.search(s):
            return "domain_poison"  # mechanism ban / redirect on a code symbol
        if _EDIT_TOOLING.search(s):
            return "tooling_poison"  # editing-tool prescription (caused step inflation)
        return "generic_prescriptive"
    return "neutral"


def measure(summary: str) -> dict:
    counts: dict[str, int] = {}
    for line in summary.splitlines():
        c = classify_line(line)
        counts[c] = counts.get(c, 0) + 1
    counts["clean"] = int(
        counts.get("domain_poison", 0) == 0
        and counts.get("tooling_poison", 0) == 0
        and counts.get("failed_unscoped", 0) == 0
    )
    return counts


# ---------------------------------------------------------------------------------------
# Inputs: saved trajectories + eval feedback
# ---------------------------------------------------------------------------------------


def transcript_from_traj(path: Path) -> str:
    t = json.loads(path.read_text())
    parts = []
    for m in t["messages"]:
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        parts.append(f"[{m.get('role', '?')}]\n{content}")
    return "\n\n".join(parts)


def load_cases(source: Path, only_failed: bool) -> list[dict]:
    dbg = json.loads((source / "memory_debug.json").read_text())
    cases = []
    for e in dbg:
        if only_failed and e.get("resolved"):
            continue
        iid, attempt = e["instance_id"], e.get("attempt", 1)
        traj = source / iid / f"{iid}.attempt{attempt}.traj.json"
        if not traj.exists():
            traj = source / iid / f"{iid}.traj.json"
        if not traj.exists():
            continue
        cases.append(
            {
                "instance_id": iid,
                "attempt": attempt,
                "resolved": bool(e.get("resolved")),
                "transcript": transcript_from_traj(traj),
                "eval_feedback": e.get("eval_feedback") or "",
                "problem_statement": e.get("problem_statement") or "",
            }
        )
    return cases


# ---------------------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------------------


def summarise_variant(variant: str, case: dict, summary_model: str, max_chars: int = 24000) -> str:
    """Run one retention distillation. 'scoped' = the current procedural prompts;
    'exemplar' = scoped + domain-neutral few-shot shape examples."""
    import litellm

    from .memory_glue import (
        _SUMMARY_SYSTEM_PROCEDURAL_FAILED,
        _SUMMARY_SYSTEM_PROCEDURAL_RESOLVED,
        MemoryGlue,
    )

    system = _SUMMARY_SYSTEM_PROCEDURAL_RESOLVED if case["resolved"] else _SUMMARY_SYSTEM_PROCEDURAL_FAILED
    if variant == "exemplar" and not case["resolved"]:
        system = system + _EXEMPLAR_ADDENDUM
    user = case["transcript"]
    if case["eval_feedback"]:
        user += (
            "\n\n=== OFFICIAL TEST EVALUATION RESULT (ground truth from the test harness) ===\n" + case["eval_feedback"]
        )
    resp = litellm.completion(
        model=summary_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user[-max_chars:]}],
        temperature=0.0,
        drop_params=True,
    )
    return MemoryGlue._strip_artifacts(resp.choices[0].message.content or "")


def mission_variant(case: dict, base_url: str, api_token: str, mission: str, rep: int) -> str:
    """Product-native variant: retain the RAW transcript + feedback into a throwaway bank and
    let Hindsight's server-side extraction, steered only by retain_mission, do the
    distillation. Returns the stored facts (what a future recall would see)."""
    from hindsight_client import Hindsight

    client = Hindsight(base_url=base_url, api_key=api_token)
    bank_id = f"retention-lab-{case['instance_id'][-5:]}-a{case['attempt']}-r{rep}"
    try:
        client.delete_bank(bank_id)
    except Exception:
        pass
    client.create_bank(bank_id, background="Retention-stability lab bank (throwaway).", retain_mission=mission)
    content = case["transcript"][-24000:]
    if case["eval_feedback"]:
        content += "\n\n=== OFFICIAL TEST EVALUATION RESULT ===\n" + case["eval_feedback"]
    client.retain(bank_id, content=content, document_id=case["instance_id"], update_mode="append")
    resp = client.recall(bank_id, query="lessons from this work", max_tokens=2048, budget="mid")
    facts = "\n".join((getattr(r, "text", None) or "") for r in (getattr(resp, "results", None) or []))
    try:
        client.delete_bank(bank_id)
    except Exception:
        pass
    return facts


def pipeline_variant(
    cases: list[dict], base_url: str, api_token: str, summary_model: str, rep: int, consolidation_wait_s: int = 30
) -> str:
    """The FULL production retention path, end to end: production summariser prompts →
    retain into a bank created with the production retain_mission AND observations_mission →
    wait out async consolidation → recall (all types) with the real task queries. Returns the
    merged recalled text — i.e. exactly what a future agent would be handed after every hop
    (extraction rephrasing + consolidation merging included)."""
    import time as _time

    from .memory_glue import MemoryGlue

    glue = MemoryGlue(
        base_url=base_url,
        api_token=api_token,
        bank_id=f"retention-lab-pipe-r{rep}",
        enabled=True,
        repo="django",
        summary_model=summary_model,
        context_mode="recall",
        retain_style="procedural",
    )
    glue.reset_bank()
    for case in cases:  # one shared bank — cross-failure consolidation is the risk under test
        glue.retain_after_task(
            case["instance_id"],
            case["transcript"],
            resolved=case["resolved"],
            eval_feedback=case["eval_feedback"] or None,
            attempt=case["attempt"],
        )
    _time.sleep(consolidation_wait_s)
    queries = [glue.orientation_query] + [c["problem_statement"] for c in cases if c.get("problem_statement")]
    seen: set[str] = set()
    lines: list[str] = []
    for q in queries:
        for text in glue._recall_texts(q):
            if text and text.lower() not in seen:
                seen.add(text.lower())
                lines.append(f"- {text}")
    try:
        glue._client.delete_bank(glue.bank_id)
    except Exception:
        pass
    return "\n".join(lines)


MISSION_SCOPED = (
    "Capture reusable engineering lessons from agent work transcripts. For VERIFIED successes "
    "(tests passed): working practices and the root-cause mechanism. For FAILED attempts (tests "
    "failed): capture only (a) process lessons (verification habits, environment facts) and "
    "(b) the failed approach STRICTLY SCOPED — bind the change to the exact method/file where "
    "it was applied and the tests it failed ('X applied in Y did not pass Z'). A failure proves "
    "only that one application at one location failed; the same mechanism may be the correct "
    "fix elsewhere. Never store prescriptive generalizations (avoid/never/use-instead), never "
    "condemn a mechanism, never claim where the real cause lies without direct test evidence."
)


# ---------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline retention-stability lab")
    ap.add_argument("--source", required=True, help="A run's treatment dir (memory_debug.json + traj files)")
    ap.add_argument("--variants", default="scoped,exemplar", help="Comma list: scoped, exemplar, mission")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--summary-model", default="vertex_ai/gemini-3.1-flash-lite")
    ap.add_argument("--all-outcomes", action="store_true", help="Include resolved tasks (default: failed only)")
    ap.add_argument("--out", default=None, help="Write full samples + measurements to this JSON file")
    args = ap.parse_args()

    from .run_study import load_env_files

    load_env_files()
    import os

    cases = load_cases(Path(args.source), only_failed=not args.all_outcomes)
    print(f"{len(cases)} cases from {args.source}")
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    dump: list[dict] = []

    for variant in variants:
        clean = 0
        total = 0
        agg: dict[str, int] = {}
        if variant == "pipeline":
            # End-to-end: one shared bank per rep over ALL outcomes (real banks hold both),
            # measured on what recall returns after extraction + consolidation.
            all_cases = load_cases(Path(args.source), only_failed=False)
            for rep in range(args.reps):
                recalled = pipeline_variant(
                    all_cases,
                    base_url=os.environ["HINDSIGHT_API_URL"],
                    api_token=os.environ.get("HINDSIGHT_API_TOKEN", ""),
                    summary_model=args.summary_model,
                    rep=rep,
                )
                m = measure(recalled)
                clean += m["clean"]
                total += 1
                for k, v in m.items():
                    if k != "clean":
                        agg[k] = agg.get(k, 0) + v
                dump.append({"variant": variant, "rep": rep, "summary": recalled, "measure": m})
                flag = "" if m["clean"] else "  <-- POISON/UNSCOPED"
                print(
                    f"  [pipeline] rep{rep}: { {k: v for k, v in m.items() if k not in ('clean', 'empty')} }{flag}",
                    flush=True,
                )
            print(f"== {variant}: clean {clean}/{total} ({100 * clean // max(1, total)}%) | line totals {agg}\n")
            continue
        for case in cases:
            for rep in range(args.reps):
                if variant == "mission":
                    summary = mission_variant(
                        case,
                        base_url=os.environ["HINDSIGHT_API_URL"],
                        api_token=os.environ.get("HINDSIGHT_API_TOKEN", ""),
                        mission=MISSION_SCOPED,
                        rep=rep,
                    )
                else:
                    summary = summarise_variant(variant, case, args.summary_model)
                m = measure(summary)
                clean += m["clean"]
                total += 1
                for k, v in m.items():
                    if k != "clean":
                        agg[k] = agg.get(k, 0) + v
                dump.append(
                    {
                        "variant": variant,
                        "instance_id": case["instance_id"],
                        "attempt": case["attempt"],
                        "rep": rep,
                        "summary": summary,
                        "measure": m,
                    }
                )
                flag = "" if m["clean"] else "  <-- POISON/UNSCOPED"
                print(
                    f"  [{variant}] {case['instance_id'][-5:]}.a{case['attempt']} rep{rep}: "
                    f"{ {k: v for k, v in m.items() if k not in ('clean', 'empty')} }{flag}",
                    flush=True,
                )
        print(f"== {variant}: clean {clean}/{total} ({100 * clean // max(1, total)}%) | line totals {agg}\n")

    if args.out:
        Path(args.out).write_text(json.dumps(dump, indent=2))
        print(f"samples written to {args.out}")


if __name__ == "__main__":
    main()
