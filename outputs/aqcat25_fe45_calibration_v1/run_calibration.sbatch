#!/bin/bash
#SBATCH --job-name=aqcat25-cal-v1
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:15:00
#SBATCH --output=/home/sbq/sbq/aqcat25_calibration/aqcat25_fe45_v1/calibration-%j.out

set -uo pipefail

AQCAT_ROOT=/home/sbq/sbq/aqcat25
PILOT_ROOT=/home/sbq/sbq/aqcat25_ts_pilot
AQCAT_PYTHON=/home/sbq/sbq/ml_ts_acceleration/venv/bin/python
CHECKPOINT="$AQCAT_ROOT/demo_single/model.pt"
CALIBRATION_ROOT=/home/sbq/sbq/aqcat25_calibration/aqcat25_fe45_v1
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

export PYTHONPATH="$AQCAT_ROOT/python_pkgs:$AQCAT_ROOT/vendor${PYTHONPATH:+:$PYTHONPATH}"
export XDG_CACHE_HOME="$AQCAT_ROOT/cache/xdg"
export TORCH_HOME="$AQCAT_ROOT/cache/torch"
export HF_HOME="$AQCAT_ROOT/cache/huggingface"
export TMPDIR="$AQCAT_ROOT/tmp"
export WITH_PYG_LIB=0
export TORCH_SPARSE_USE_PYG_LIB=0
export TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled

write_exit_record() {
  local exit_code=$1
  STARTED_UTC="$STARTED_UTC" EXIT_CODE="$exit_code" CALIBRATION_ROOT="$CALIBRATION_ROOT" \
    "$AQCAT_PYTHON" - <<'PY'
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ["CALIBRATION_ROOT"])
exit_code = int(os.environ["EXIT_CODE"])
job_id = os.environ["SLURM_JOB_ID"]
record = {
    "gpu_job_id": job_id,
    "hostname": socket.gethostname(),
    "started_utc": os.environ["STARTED_UTC"],
    "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "exit_code": exit_code,
    "status": "success" if exit_code == 0 else "failed",
    "evidence_class": "producer_process_only_not_scheduler_accounting",
}
target = root / f"producer_exit_record_job_{job_id}.json"
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
temporary.replace(target)
PY
}

exit_code=0
"$AQCAT_PYTHON" "$PILOT_ROOT/evaluate_fe45_calibration.py" \
  --checkpoint "$CHECKPOINT" \
  --labels "$CALIBRATION_ROOT/labels.json" \
  --structures "$CALIBRATION_ROOT/structures" \
  --output "$CALIBRATION_ROOT/predictions.json" || exit_code=$?
write_exit_record "$exit_code"
exit "$exit_code"
