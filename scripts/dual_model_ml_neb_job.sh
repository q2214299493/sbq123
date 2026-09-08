#!/bin/bash
#SBATCH --job-name=dual-ml-neb-smoke
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=40G
#SBATCH --time=00:20:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/logs/dual-ml-neb-smoke-%j.out

set -uo pipefail

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
REQUEST_ROOT=${REQUEST_ROOT:?REQUEST_ROOT is required}
SOURCE_REQUEST_SHA256=${SOURCE_REQUEST_SHA256:?SOURCE_REQUEST_SHA256 is required}
OUTPUT_ROOT=${OUTPUT_ROOT:-$REQUEST_ROOT/output/dual_model_smoke_$SLURM_JOB_ID}
PRIMARY_CHECKPOINT=${PRIMARY_CHECKPOINT:?PRIMARY_CHECKPOINT is required}
SECONDARY_CHECKPOINT=${SECONDARY_CHECKPOINT:-/home/sbq/sbq/aqcat25/demo_single/model.pt}
MATRIS_SOURCE=${MATRIS_SOURCE:-/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS}

for path in "$REQUEST_ROOT" "$OUTPUT_ROOT" "$PRIMARY_CHECKPOINT" "$SECONDARY_CHECKPOINT" "$MATRIS_SOURCE"; do
  case "$path" in
    /home/sbq/sbq/*) ;;
    *) echo "path is outside /home/sbq/sbq: $path" >&2; exit 2 ;;
  esac
done

. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$OUTPUT_ROOT"
test -d "$MATRIS_SOURCE/matris" || {
  echo "MatRIS source is missing: $MATRIS_SOURCE" >&2
  exit 2
}
export PYTHONPATH="$MATRIS_SOURCE${PYTHONPATH:+:$PYTHONPATH}"

write_failure_record() {
  local exit_code=$1
  EXIT_CODE="$exit_code" OUTPUT_ROOT="$OUTPUT_ROOT" "$AQCAT_PYTHON" - <<'PY'
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from artifact_io import write_json_atomic

write_json_atomic(
    Path(os.environ["OUTPUT_ROOT"]) / f"producer_exit_record.failure.{os.environ['SLURM_JOB_ID']}.json",
    {
        "gpu_job_id": os.environ["SLURM_JOB_ID"],
        "hostname": socket.gethostname(),
        "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "exit_code": int(os.environ["EXIT_CODE"]),
        "status": "failed",
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    },
    ensure_ascii=True,
)
PY
}

exit_code=0
echo "$SOURCE_REQUEST_SHA256  $REQUEST_ROOT/request.json" | sha256sum -c - || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  aqcat25_require_mz73 || exit_code=$?
fi
if [ "$exit_code" -eq 0 ]; then
  "$AQCAT_PYTHON" "$PILOT_ROOT/dual_model_ml_neb.py" \
    --request "$REQUEST_ROOT/request.json" \
    --primary-checkpoint "$PRIMARY_CHECKPOINT" \
    --secondary-checkpoint "$SECONDARY_CHECKPOINT" \
    --output "$OUTPUT_ROOT" \
    --device cuda || exit_code=$?
fi
if [ "$exit_code" -ne 0 ]; then
  write_failure_record "$exit_code"
fi
exit "$exit_code"
