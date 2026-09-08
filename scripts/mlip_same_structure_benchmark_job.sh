#!/bin/bash
#SBATCH --job-name=mlip-same-structure
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=24G
#SBATCH --time=02:00:00

set -uo pipefail

BENCHMARK_ROOT=${BENCHMARK_ROOT:?BENCHMARK_ROOT is required}
BACKEND=${BACKEND:?BACKEND is required}
CHECKPOINT=${CHECKPOINT:?CHECKPOINT is required}
PYTHON_BIN=${PYTHON_BIN:?PYTHON_BIN is required}
BACKEND_VERSION=${BACKEND_VERSION:?BACKEND_VERSION is required}
SOURCE_MANIFEST_SHA256=${SOURCE_MANIFEST_SHA256:?SOURCE_MANIFEST_SHA256 is required}
RUNNER=${RUNNER:-$BENCHMARK_ROOT/mlip_same_structure_benchmark.py}
OUTPUT_ROOT=${OUTPUT_ROOT:-$BENCHMARK_ROOT/results/$BACKEND/job_$SLURM_JOB_ID}
MANIFEST=$BENCHMARK_ROOT/benchmark_manifest.json
EXIT_RECORD=$OUTPUT_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case "$BENCHMARK_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "BENCHMARK_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac
case "$OUTPUT_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "OUTPUT_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac

mkdir -p "$OUTPUT_ROOT"

if [ "$BACKEND" = "aqcat25" ]; then
  AQCAT_ENV=${AQCAT_ENV:-/home/sbq/sbq/aqcat25_ts_pilot/deployments/force_prediction_batch_v1_20260820/aqcat25_mz73_env.sh}
  . "$AQCAT_ENV" || exit 2
  aqcat25_setup_mz73_environment "$OUTPUT_ROOT" || exit 2
elif [ "$BACKEND" = "matris" ]; then
  MATRIS_SOURCE=${MATRIS_SOURCE:-$BENCHMARK_ROOT/vendor/MatRIS}
  test -d "$MATRIS_SOURCE/matris" || {
    echo "MatRIS source is missing: $MATRIS_SOURCE" >&2
    exit 2
  }
  export PYTHONPATH="$MATRIS_SOURCE${PYTHONPATH:+:$PYTHONPATH}"
else
  echo "Unsupported backend: $BACKEND" >&2
  exit 2
fi

write_exit_record() {
  local exit_code=$1
  STARTED_UTC=$STARTED_UTC EXIT_CODE=$exit_code EXIT_RECORD=$EXIT_RECORD \
    BACKEND=$BACKEND SOURCE_MANIFEST_SHA256=$SOURCE_MANIFEST_SHA256 \
    "$PYTHON_BIN" - <<'PY'
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["EXIT_RECORD"])
path.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "gpu_job_id": os.environ["SLURM_JOB_ID"],
    "backend": os.environ["BACKEND"],
    "hostname": socket.gethostname(),
    "started_utc": os.environ["STARTED_UTC"],
    "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "exit_code": int(os.environ["EXIT_CODE"]),
    "status": "success" if int(os.environ["EXIT_CODE"]) == 0 else "failed",
    "source_manifest_sha256": os.environ["SOURCE_MANIFEST_SHA256"],
    "evidence_class": "producer_process_only_not_scheduler_accounting",
}
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
PY
}

run_benchmark() {
  echo "$SOURCE_MANIFEST_SHA256  $MANIFEST" | sha256sum -c - || return $?
  "$PYTHON_BIN" "$RUNNER" run \
    --manifest "$MANIFEST" \
    --backend "$BACKEND" \
    --checkpoint "$CHECKPOINT" \
    --output "$OUTPUT_ROOT" \
    --device cuda \
    --backend-version "$BACKEND_VERSION" \
    ${SAMPLE_LIMIT:+--sample-limit "$SAMPLE_LIMIT"} \
    ${SAMPLE_ID:+--sample-id "$SAMPLE_ID"} \
    ${SKIP_RELAXATION:+--skip-relaxation} || return $?
}

exit_code=0
run_benchmark || exit_code=$?
write_exit_record "$exit_code" || exit 30
exit "$exit_code"
