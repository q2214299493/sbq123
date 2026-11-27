#!/bin/bash
#SBATCH --job-name=matris-ft-speed
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=40G
#SBATCH --time=01:30:00

set -euo pipefail

# BEGIN GPU BOOTSTRAP GUARD (mirrored from aqcat25_mz73_env.sh)
# This dependency-free guard must exist even when the shared helper is missing.
gpu_bootstrap_failure() {
  local code=$? directory record
  [ "$code" -ne 0 ] || return 0
  record=$(printf '{"document_kind":"gpu_wrapper_execution_failure","status":"failed","phase":"bootstrap","exit_code":%d,"evidence_class":"producer_process_only_not_scheduler_accounting"}' "$code")
  printf '%s\n' "$record" >&2
  directory=$(pwd -P)
  case "$directory" in
    /home/sbq/sbq|/home/sbq/sbq/*)
      (umask 077; set -C; printf '%s\n' "$record" > "$directory/producer_exit_record.failure.bootstrap.$$.json") || : ;;
  esac
}
aqcat25_install_bootstrap_guard() {
  trap gpu_bootstrap_failure EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
}
# END GPU BOOTSTRAP GUARD
aqcat25_install_bootstrap_guard

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
GPU_ENV_SOURCE=$(realpath -e -- "${AQCAT_ENV:-$PILOT_ROOT/aqcat25_mz73_env.sh}") || exit 2
case "$GPU_ENV_SOURCE" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
. "$GPU_ENV_SOURCE" || exit 2
aqcat25_begin_execution || exit 2

EXPERIMENT_ROOT=${EXPERIMENT_ROOT:?EXPERIMENT_ROOT is required}
EXPERIMENT_SHA256=${EXPERIMENT_SHA256:?EXPERIMENT_SHA256 is required}
aqcat25_require_sha256 "$EXPERIMENT_SHA256" || exit 2
OUTPUT_ROOT=${OUTPUT_ROOT:-$EXPERIMENT_ROOT/results/job_$SLURM_JOB_ID}
MATRIS_SOURCE=${MATRIS_SOURCE:-/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS}
PYTHON_BIN=${PYTHON_BIN:-/home/sbq/sbq/ml_ts_acceleration/venv/bin/python}
RUNNER=${RUNNER:-$EXPERIMENT_ROOT/matris_finetune_speed_benchmark.py}

for path in "$EXPERIMENT_ROOT" "$OUTPUT_ROOT" "$MATRIS_SOURCE" "$PYTHON_BIN" "$RUNNER"; do
  aqcat25_require_remote_path "$path" || exit 2
done

test -x "$PYTHON_BIN" || exit 2
test -d "$MATRIS_SOURCE/matris" || exit 2
mkdir -p "$OUTPUT_ROOT"
export PYTHONPATH="$MATRIS_SOURCE:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor${PYTHONPATH:+:$PYTHONPATH}"
export XDG_CACHE_HOME=${XDG_CACHE_HOME:-/home/sbq/sbq/aqcat25/cache/xdg}
export TORCH_HOME=${TORCH_HOME:-/home/sbq/sbq/aqcat25/cache/torch}
export HF_HOME=${HF_HOME:-/home/sbq/sbq/aqcat25/cache/huggingface}
export TMPDIR=${TMPDIR:-/home/sbq/sbq/aqcat25/tmp}
export WITH_PYG_LIB=0
export TORCH_SPARSE_USE_PYG_LIB=0
export TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}

aqcat25_require_remote_path "$XDG_CACHE_HOME" "$TORCH_HOME" "$HF_HOME" "$TMPDIR" || exit 2

started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
exit_code=0
echo "$EXPERIMENT_SHA256  $EXPERIMENT_ROOT/experiment_manifest.json" | sha256sum -c - || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  "$PYTHON_BIN" "$RUNNER" \
    --experiment "$EXPERIMENT_ROOT/experiment_manifest.json" \
    --output "$OUTPUT_ROOT" \
    --device cuda || exit_code=$?
fi

STARTED_UTC="$started_utc" EXIT_CODE="$exit_code" OUTPUT_ROOT="$OUTPUT_ROOT" \
  EXPERIMENT_SHA256="$EXPERIMENT_SHA256" "$PYTHON_BIN" - <<'PY'
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["OUTPUT_ROOT"]) / "producer_exit_record.json"
payload = {
    "gpu_job_id": os.environ.get("SLURM_JOB_ID"),
    "hostname": socket.gethostname(),
    "started_utc": os.environ["STARTED_UTC"],
    "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "exit_code": int(os.environ["EXIT_CODE"]),
    "status": "success" if int(os.environ["EXIT_CODE"]) == 0 else "failed",
    "experiment_sha256": os.environ["EXPERIMENT_SHA256"],
    "evidence_class": "producer_process_only_not_scheduler_accounting",
}
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
PY

exit "$exit_code"
