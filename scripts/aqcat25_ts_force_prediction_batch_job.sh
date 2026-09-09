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
GPU_ENV_SOURCE=$(realpath -e -- "$PILOT_ROOT/aqcat25_mz73_env.sh") || exit 2
case "$GPU_ENV_SOURCE" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
. "$GPU_ENV_SOURCE" || exit 2
aqcat25_begin_execution || exit 2

BATCH_ROOT=${BATCH_ROOT:?BATCH_ROOT is required}
SOURCE_BATCH_SHA256=${SOURCE_BATCH_SHA256:?SOURCE_BATCH_SHA256 is required}
aqcat25_require_sha256 "$SOURCE_BATCH_SHA256" || exit 2
BATCH_MANIFEST=$BATCH_ROOT/path_prediction_batch_request.json
OUTPUT_ROOT=${OUTPUT_ROOT:-$BATCH_ROOT/output/job_$SLURM_JOB_ID}
EXIT_RECORD=$OUTPUT_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aqcat25_require_remote_path "$BATCH_ROOT" || exit 2
aqcat25_require_remote_path "$OUTPUT_ROOT" || exit 2

aqcat25_setup_mz73_environment "$OUTPUT_ROOT" || exit 2

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
