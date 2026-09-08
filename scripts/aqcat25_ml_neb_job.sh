#!/bin/bash
#SBATCH --job-name=aqcat25-ml-neb
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=40G
#SBATCH --time=02:00:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/logs/aqcat25-ml-neb-%j.out

set -uo pipefail

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
HANDOFF_ROOT=${HANDOFF_ROOT:?HANDOFF_ROOT is required}
SOURCE_HANDOFF_SHA256=${SOURCE_HANDOFF_SHA256:?SOURCE_HANDOFF_SHA256 is required}
OUTPUT_ROOT=${OUTPUT_ROOT:-$HANDOFF_ROOT/output/ml_neb_job_$SLURM_JOB_ID}
CHECKPOINT=${CHECKPOINT:-/home/sbq/sbq/aqcat25/demo_single/model.pt}

case "$HANDOFF_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "HANDOFF_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac
case "$OUTPUT_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "OUTPUT_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac

. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$OUTPUT_ROOT"
resume_args=()
if [ "${ML_NEB_RESUME:-0}" = "1" ]; then
  resume_args+=(--resume)
fi

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
echo "$SOURCE_HANDOFF_SHA256  $HANDOFF_ROOT/handoff.json" | sha256sum -c - || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  aqcat25_require_mz73 || exit_code=$?
fi
if [ "$exit_code" -eq 0 ]; then
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_handoff.py" \
    "$HANDOFF_ROOT/handoff.json" --root "$HANDOFF_ROOT" \
    --schema "$PILOT_ROOT/aqcat25_handoff.schema.json" || exit_code=$?
fi
if [ "$exit_code" -eq 0 ]; then
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ml_neb.py" \
    --handoff "$HANDOFF_ROOT/handoff.json" \
    --checkpoint "$CHECKPOINT" \
    --schema "$PILOT_ROOT/aqcat25_handoff.schema.json" \
    --output "$OUTPUT_ROOT" \
    --images-per-segment "${ML_NEB_IMAGES_PER_SEGMENT:-5}" \
    --spring-constant "${ML_NEB_SPRING:-0.10}" \
    --ordinary-fmax "${ML_NEB_FMAX:-0.10}" \
    --ordinary-steps "${ML_NEB_STEPS:-300}" \
    --ml-ci "${ML_CI_MODE:-auto}" \
    --ci-fmax "${ML_CI_FMAX:-0.05}" \
    --ci-steps "${ML_CI_STEPS:-200}" \
    --checkpoint-interval "${ML_NEB_CHECKPOINT_INTERVAL:-5}" \
    "${resume_args[@]}" || exit_code=$?
fi
if [ "$exit_code" -ne 0 ]; then
  write_failure_record "$exit_code"
fi
exit "$exit_code"
