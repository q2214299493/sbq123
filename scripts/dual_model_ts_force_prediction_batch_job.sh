#!/bin/bash
#SBATCH --job-name=dual-ts-force-batch
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=40G
#SBATCH --time=00:20:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/logs/dual-ts-force-batch-%j.out

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

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot/deployments/ml_neb_v1_20260819}
GPU_ENV_SOURCE=$(realpath -e -- "$PILOT_ROOT/aqcat25_mz73_env.sh") || exit 2
case "$GPU_ENV_SOURCE" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
. "$GPU_ENV_SOURCE" || exit 2
aqcat25_begin_execution || exit 2

BATCH_ROOT=${BATCH_ROOT:?BATCH_ROOT is required}
SOURCE_REQUEST_SHA256=${SOURCE_REQUEST_SHA256:?SOURCE_REQUEST_SHA256 is required}
aqcat25_require_sha256 "$SOURCE_REQUEST_SHA256" || exit 2
PRIMARY_CHECKPOINT=${PRIMARY_CHECKPOINT:?PRIMARY_CHECKPOINT is required}
SECONDARY_CHECKPOINT=${SECONDARY_CHECKPOINT:?SECONDARY_CHECKPOINT is required}
MATRIS_SOURCE=${MATRIS_SOURCE:-/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS}
REQUEST=$BATCH_ROOT/dual_model_prediction_batch_request.json
OUTPUT=${OUTPUT:-$BATCH_ROOT/output/predictions_$SLURM_JOB_ID.json}
EXIT_RECORD=${OUTPUT%.json}.producer_exit_record.$SLURM_JOB_ID.json
RUNNER=${RUNNER:-$BATCH_ROOT/runtime/dual_model_ts_force_prediction_batch.py}
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

for path in "$BATCH_ROOT" "$OUTPUT" "$RUNNER" "$PRIMARY_CHECKPOINT" "$SECONDARY_CHECKPOINT" "$MATRIS_SOURCE"; do
  aqcat25_require_remote_path "$path" || exit 2
done

aqcat25_setup_mz73_environment "$(dirname "$OUTPUT")" || exit 2
test -d "$MATRIS_SOURCE/matris" || {
  echo "MatRIS source is missing: $MATRIS_SOURCE" >&2
  exit 2
}
export PYTHONPATH="$MATRIS_SOURCE${PYTHONPATH:+:$PYTHONPATH}"

write_exit_record() {
  local exit_code=$1
  STARTED_UTC=$STARTED_UTC EXIT_CODE=$exit_code EXIT_RECORD=$EXIT_RECORD \
    SOURCE_REQUEST_SHA256=$SOURCE_REQUEST_SHA256 "$AQCAT_PYTHON" - <<'PY'
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
        "source_request_sha256": os.environ["SOURCE_REQUEST_SHA256"],
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    },
    ensure_ascii=True,
)
PY
}

exit_code=0
echo "$SOURCE_REQUEST_SHA256  $REQUEST" | sha256sum -c - || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  aqcat25_require_mz73 || exit_code=$?
fi
if [ "$exit_code" -eq 0 ]; then
  "$AQCAT_PYTHON" "$RUNNER" \
    --request "$REQUEST" \
    --primary-checkpoint "$PRIMARY_CHECKPOINT" \
    --secondary-checkpoint "$SECONDARY_CHECKPOINT" \
    --output "$OUTPUT" \
    --device cuda || exit_code=$?
fi
write_exit_record "$exit_code" || exit 30
exit "$exit_code"
