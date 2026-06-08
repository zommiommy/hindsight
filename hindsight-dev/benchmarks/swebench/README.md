# SWE-bench memory study — do coding agents do better *with* Hindsight?

Quantitative evidence that a coding agent backed by Hindsight outperforms the same agent
without it. The headline metric is **efficiency at equal quality**: as the agent works a
sequence of issues on the *same repository*, a memory-backed agent should spend fewer
**tokens** and **steps** (and, on native hardware, less **wall-clock**) at equal-or-better
**resolve rate**. The wedge: coding is the domain the market already trusts agents in, so if
memory makes coding agents cheaper/faster, it generalises to every agent type.

This mirrors (and lets us rebut) the competitor TencentDB Agent-Memory SWE-bench claim
(+9.93% resolve / −33% tokens), measured by running consecutive tasks per session.

## Why "consecutive tasks on one repo"

Vanilla SWE-bench scores each instance independently from a clean checkout, so a memory
system has nothing to recall and only adds overhead. We instead run the tasks of **one repo
(django)** in chronological order through **one persistent memory bank**. Durable codebase
knowledge (where modules live, how to run tests, conventions, pitfalls) accumulates and is
recalled on later tasks. The money chart is the **warm-up curve**: ~0 advantage at task 1
(empty memory), a growing gap by task N.

## Design

- **Scaffold:** [`mini-swe-agent`](https://github.com/SWE-agent/mini-swe-agent) (recognised,
  ~100-line linear-history agent, official SWE-bench Docker runner, litellm for any provider).
- **Arms (identical task order, only memory differs):**
  - `control` — `MeteredAgent` (DefaultAgent + token/step counting), no memory.
  - `treatment` — `MemoryAgent`: recall before each task (injected via a `{% if
    recalled_memories %}` block appended to the *same* stock prompt), retain a distilled
    durable-knowledge summary after each task.
- **Memory:** Hindsight Cloud dev instance (`api.dev.hindsight.vectorize.io`), one bank per
  `(repo, arm, seed)`, reset for a clean cold start.
- **Scoring:** the official `swebench.harness.run_evaluation` in Docker (FAIL_TO_PASS /
  PASS_TO_PASS). We never hand-judge a patch.

## Files

| File | Role |
|------|------|
| `run_study.py` | Orchestrator: build task sequence, run both arms sequentially, score, aggregate. |
| `memory_glue.py` | Hindsight recall-before / retain-after + memory-layer cost accounting. |
| `agent_hooks.py` | `MeteredAgent` (token/step metering) and `MemoryAgent` (recall/retain). |
| `scoring.py` | Wraps the official SWE-bench harness → `{instance_id: resolved}`. |
| `metrics.py` | Per-task records, arm summaries, warm-up curve, results JSON. |
| `config/smoke.yaml` | Smoke config (django ×10, Groq model, 1 seed). |

## Setup

```bash
# from repo root
uv venv --python 3.11 hindsight-dev/benchmarks/swebench/.venv
uv pip install --python hindsight-dev/benchmarks/swebench/.venv/bin/python \
    -r hindsight-dev/benchmarks/swebench/requirements.txt
uv pip install --python hindsight-dev/benchmarks/swebench/.venv/bin/python \
    -e hindsight-clients/python
```

Create `hindsight-dev/benchmarks/swebench/.env` (gitignored):

```
HINDSIGHT_API_URL=https://api.dev.hindsight.vectorize.io
HINDSIGHT_API_TOKEN=hsk_...           # dev instance token
GROQ_API_KEY=gsk_...                  # agent + summariser model for the smoke config
GEMINI_API_KEY=...                    # agent + summariser model for the pilot config
```

litellm reads the provider key matching the configured `model_name` (`groq/...` →
`GROQ_API_KEY`, `gemini/...` → `GEMINI_API_KEY`, `anthropic/...` → `ANTHROPIC_API_KEY`).

## Run

```bash
# quick wiring check (no Docker, no scoring) — proves imports/recall/retain plumbing
./scripts/benchmarks/run-swebench.sh --limit 2 --skip-score --arms treatment

# smoke (django, cheap open model, both arms, Docker scoring)
./scripts/benchmarks/run-swebench.sh --config config/smoke.yaml --limit 4

# pilot / definitive (gemini-flash-latest via Vertex ADC, clustered django tasks)
./scripts/benchmarks/run-swebench.sh --config config/pilot.yaml --limit 15 \
  --context-mode reflect --recall-types all
```

### Reusing the control arm (don't waste compute)

The control arm is **deterministic** (temperature 0, ignores memory) — re-running it for every
memory config is wasted compute *and* re-scoring. Run it once, then reuse it for all variants on
the **same task-set / model / step_limit**:

```bash
# first run produces results/<run_id>/results.json (control + treatment)
./scripts/benchmarks/run-swebench.sh --config config/pilot.yaml --limit 15 --context-mode recall

# later variants only run + score the TREATMENT arm; control is loaded from the prior results
./scripts/benchmarks/run-swebench.sh --config config/pilot.yaml --limit 15 --context-mode reflect \
  --control-from results/pilot-django-s0/results.json
```

`--control-from` validates the instance list matches and refuses to reuse a mismatched task-set.

Results land in `results/<run_id>/results.json` with `headline`, per-arm summaries, the
`warm_up_curve`, and per-task records.

### Recall strategy

The treatment arm runs **two** recalls per task and merges them (deduped): a fixed
**orientation** query (repo layout / how to run tests / conventions — useful to *any* task) and
the **task-specific** problem statement. How much each recall returns is governed by Hindsight's
`max_tokens` + `budget` — Hindsight has no top-K, and we impose no client-side cap, so the agent
gets everything that fit the token budget. Without orientation recall, hits are sparse at small N
because the facts learned on one task rarely match an unrelated later task (observed in the
smoke: hit on task 2, missed on tasks 3–4). Toggle with `memory.orientation_enabled` / override
`memory.orientation_query`.

Recall is **not** filtered to observations — those require async server-side consolidation that
lags retain, so at minutes-apart task spacing the freshly-stored `world`/`experience` facts
(available in ~3s) would be invisible. `memory.recall_types: null` recalls all types.

## Caveats

- **Apple Silicon (arm64):** SWE-bench's prebuilt images are x86_64 and run under emulation —
  slow and RAM-tight, and **wall-clock becomes noisy**. Tokens and steps are LLM-side and stay
  valid. Run pilots/full studies on an x86_64 Linux box; the code is identical there.
- **Smoke ≠ headline:** a cheap open model resolves few django tasks. The smoke validates the
  pipeline and the *efficiency* signal (tokens/steps), not publishable resolve numbers.
- Each higher tier (pilot, full) is a separate, more expensive run — see the plan file.
