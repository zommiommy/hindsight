#!/bin/bash
# Run the SWE-bench Hindsight memory study (does a coding agent do better WITH Hindsight?).
#
# Uses a dedicated venv under hindsight-dev/benchmarks/swebench/.venv (heavy SWE-bench +
# agent deps kept out of the main project). Requires Docker and a study .env with
# HINDSIGHT_API_TOKEN + an agent LLM key. See that directory's README.md.
#
# Usage:
#   ./scripts/benchmarks/run-swebench.sh                         # smoke (django x10, both arms)
#   ./scripts/benchmarks/run-swebench.sh --limit 2 --skip-score  # quick wiring check
#   ./scripts/benchmarks/run-swebench.sh --config config/smoke.yaml --arms treatment
set -euo pipefail
cd "$(dirname "$0")/../.."

STUDY_DIR="hindsight-dev/benchmarks/swebench"
VENV="$STUDY_DIR/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating venv at $VENV ..."
  uv venv --python 3.11 "$VENV"
  uv pip install --python "$VENV/bin/python" -r "$STUDY_DIR/requirements.txt"
  uv pip install --python "$VENV/bin/python" -e hindsight-clients/python
fi

CONFIG="config/smoke.yaml"
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

# Run as a package from hindsight-dev (so `benchmarks.swebench` resolves), using the
# study venv's interpreter. --config resolves relative to the study dir.
VENV_PY="$(pwd)/$VENV/bin/python"
cd hindsight-dev

# Keep the machine awake for the whole run. A multi-hour study dies if the Mac sleeps:
# the network drops, gcloud ADC tokens can't refresh, and model calls fail. `caffeinate`
# (macOS) prevents idle/display/disk/system sleep for the lifetime of the process.
CAFFEINATE=""
if command -v caffeinate >/dev/null 2>&1; then CAFFEINATE="caffeinate -dimsu"; fi
exec $CAFFEINATE "$VENV_PY" -m benchmarks.swebench.run_study --config "$CONFIG" ${ARGS[@]+"${ARGS[@]}"}

