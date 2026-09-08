#!/bin/bash
#SBATCH --job-name=matris-ft-speed
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=40G
#SBATCH --time=01:30:00

set -uo pipefail

EXPERIMENT_ROOT=${EXPERIMENT_ROOT:?EXPERIMENT_ROOT is required}
EXPERIMENT_SHA256=${EXPERIMENT_SHA256:?EXPERIMENT_SHA256 is required}
OUTPUT_ROOT=${OUTPUT_ROOT:-$EXPERIMENT_ROOT/results/job_$SLURM_JOB_ID}
MATRIS_SOURCE=${MATRIS_SOURCE:-/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS}
PYTHON_BIN=${PYTHON_BIN:-/home/sbq/sbq/ml_ts_acceleration/venv/bin/python}
RUNNER=${RUNNER:-$EXPERIMENT_ROOT/matris_finetune_speed_benchmark.py}

for path in "$EXPERIMENT_ROOT" "$OUTPUT_ROOT" "$MATRIS_SOURCE" "$PYTHON_BIN" "$RUNNER"; do
  case "$path" in
    /home/sbq/sbq/*) ;;
    *) echo "path is outside /home/sbq/sbq: $path" >&2; exit 2 ;;
  esac
done

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
