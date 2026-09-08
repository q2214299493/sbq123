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

set -uo pipefail

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot/deployments/ml_neb_v1_20260819}
BATCH_ROOT=${BATCH_ROOT:?BATCH_ROOT is required}
SOURCE_REQUEST_SHA256=${SOURCE_REQUEST_SHA256:?SOURCE_REQUEST_SHA256 is required}
PRIMARY_CHECKPOINT=${PRIMARY_CHECKPOINT:?PRIMARY_CHECKPOINT is required}
SECONDARY_CHECKPOINT=${SECONDARY_CHECKPOINT:?SECONDARY_CHECKPOINT is required}
MATRIS_SOURCE=${MATRIS_SOURCE:-/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS}
TARGET_GPU_ID=${TARGET_GPU_ID:-}
MIN_FREE_GPU_MIB=${MIN_FREE_GPU_MIB:-0}
REQUEST=$BATCH_ROOT/dual_model_prediction_batch_request.json
OUTPUT=${OUTPUT:-$BATCH_ROOT/output/predictions_$SLURM_JOB_ID.json}
EXIT_RECORD=${OUTPUT%.json}.producer_exit_record.$SLURM_JOB_ID.json
RUNNER=${RUNNER:-$BATCH_ROOT/runtime/dual_model_ts_force_prediction_batch.py}
ARTIFACT_IO=$BATCH_ROOT/runtime/artifact_io.py
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

for path in "$BATCH_ROOT" "$OUTPUT" "$RUNNER" "$ARTIFACT_IO" "$PRIMARY_CHECKPOINT" "$SECONDARY_CHECKPOINT" "$MATRIS_SOURCE"; do
  case "$path" in
    /home/sbq/sbq/*) ;;
    *) echo "path is outside /home/sbq/sbq: $path" >&2; exit 2 ;;
  esac
done

. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$(dirname "$OUTPUT")"
test -d "$MATRIS_SOURCE/matris" || {
  echo "MatRIS source is missing: $MATRIS_SOURCE" >&2
  exit 2
}
test -f "$ARTIFACT_IO" || {
  echo "artifact writer is missing: $ARTIFACT_IO" >&2
  exit 2
}
export PYTHONPATH="$BATCH_ROOT/runtime:$MATRIS_SOURCE${PYTHONPATH:+:$PYTHONPATH}"

write_exit_record() {
  local exit_code=$1
  STARTED_UTC=$STARTED_UTC EXIT_CODE=$exit_code EXIT_RECORD=$EXIT_RECORD \
    SOURCE_REQUEST_SHA256=$SOURCE_REQUEST_SHA256 \
    WRAPPER_PREFLIGHT_ONLY=${WRAPPER_PREFLIGHT_ONLY:-0} "$AQCAT_PYTHON" - <<'PY'
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
        "preflight_only": os.environ.get("WRAPPER_PREFLIGHT_ONLY", "0") == "1",
    },
    ensure_ascii=True,
)
PY
}

if [ -n "$TARGET_GPU_ID" ]; then
  FREE_GPU_MIB=$(nvidia-smi --id="$TARGET_GPU_ID" \
    --query-gpu=memory.free --format=csv,noheader,nounits | tr -d '[:space:]') || {
      write_exit_record 41 || exit 30
      exit 41
    }
  case "$FREE_GPU_MIB:$MIN_FREE_GPU_MIB" in
    *[!0-9:]*|:*|*:) write_exit_record 41 || exit 30; exit 41 ;;
  esac
  if [ "$FREE_GPU_MIB" -lt "$MIN_FREE_GPU_MIB" ]; then
    echo "GPU availability gate failed: target=$TARGET_GPU_ID free=${FREE_GPU_MIB}MiB required=${MIN_FREE_GPU_MIB}MiB" >&2
    write_exit_record 42 || exit 30
    exit 42
  fi
  export CUDA_DEVICE_ORDER=PCI_BUS_ID
  export CUDA_VISIBLE_DEVICES="$TARGET_GPU_ID"
  echo "GPU availability gate passed: target=$TARGET_GPU_ID free=${FREE_GPU_MIB}MiB required=${MIN_FREE_GPU_MIB}MiB"
fi

if [ "${WRAPPER_PREFLIGHT_ONLY:-0}" = "1" ]; then
  write_exit_record 0 || exit 30
  exit 0
fi

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
