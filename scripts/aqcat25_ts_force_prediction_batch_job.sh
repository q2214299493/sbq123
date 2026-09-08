#!/bin/bash
#SBATCH --job-name=aqcat-ts-force-batch
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=24G
#SBATCH --time=00:30:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/logs/aqcat-ts-force-batch-%j.out

set -uo pipefail

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
BATCH_ROOT=${BATCH_ROOT:?BATCH_ROOT is required}
SOURCE_BATCH_SHA256=${SOURCE_BATCH_SHA256:?SOURCE_BATCH_SHA256 is required}
BATCH_MANIFEST=$BATCH_ROOT/path_prediction_batch_request.json
OUTPUT_ROOT=${OUTPUT_ROOT:-$BATCH_ROOT/output/job_$SLURM_JOB_ID}
EXIT_RECORD=$OUTPUT_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case "$BATCH_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "BATCH_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac
case "$OUTPUT_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "OUTPUT_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac

. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$OUTPUT_ROOT"

write_exit_record() {
  local exit_code=$1
  STARTED_UTC=$STARTED_UTC EXIT_CODE=$exit_code EXIT_RECORD=$EXIT_RECORD \
    SOURCE_BATCH_SHA256=$SOURCE_BATCH_SHA256 "$AQCAT_PYTHON" - <<'PY'
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from artifact_io import write_json_atomic

code = int(os.environ["EXIT_CODE"])
write_json_atomic(
    Path(os.environ["EXIT_RECORD"]),
    {
        "gpu_job_id": os.environ["SLURM_JOB_ID"],
        "hostname": socket.gethostname(),
        "started_utc": os.environ["STARTED_UTC"],
        "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "exit_code": code,
        "status": "success" if code == 0 else "failed",
        "source_batch_sha256": os.environ["SOURCE_BATCH_SHA256"],
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    },
    ensure_ascii=True,
)
PY
}

run_batch() {
  echo "$SOURCE_BATCH_SHA256  $BATCH_MANIFEST" | sha256sum -c - || return $?
  aqcat25_require_mz73 || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_force_prediction_batch.py" \
    --batch "$BATCH_MANIFEST" \
    --runner "$PILOT_ROOT/aqcat25_ts_force_prediction.py" \
    --output "$OUTPUT_ROOT" || return $?
}

exit_code=0
run_batch || exit_code=$?
write_exit_record "$exit_code" || exit 30
exit "$exit_code"
