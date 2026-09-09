#!/bin/bash
#SBATCH --job-name=mlip-same-structure
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=24G
#SBATCH --time=02:00:00

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
GPU_ENV_SOURCE=$(realpath -e -- "${AQCAT_ENV:-/home/sbq/sbq/aqcat25_ts_pilot/deployments/force_prediction_batch_v1_20260820/aqcat25_mz73_env.sh}") || exit 2
case "$GPU_ENV_SOURCE" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
. "$GPU_ENV_SOURCE" || exit 2
aqcat25_begin_execution || exit 2

BENCHMARK_ROOT=${BENCHMARK_ROOT:?BENCHMARK_ROOT is required}
BACKEND=${BACKEND:?BACKEND is required}
CHECKPOINT=${CHECKPOINT:?CHECKPOINT is required}
PYTHON_BIN=${PYTHON_BIN:?PYTHON_BIN is required}
BACKEND_VERSION=${BACKEND_VERSION:?BACKEND_VERSION is required}
SOURCE_MANIFEST_SHA256=${SOURCE_MANIFEST_SHA256:?SOURCE_MANIFEST_SHA256 is required}
aqcat25_require_sha256 "$SOURCE_MANIFEST_SHA256" || exit 2
RUNNER=${RUNNER:-$BENCHMARK_ROOT/mlip_same_structure_benchmark.py}
OUTPUT_ROOT=${OUTPUT_ROOT:-$BENCHMARK_ROOT/results/$BACKEND/job_$SLURM_JOB_ID}
MANIFEST=$BENCHMARK_ROOT/benchmark_manifest.json
EXIT_RECORD=$OUTPUT_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aqcat25_require_remote_path "$BENCHMARK_ROOT" || exit 2
aqcat25_require_remote_path "$OUTPUT_ROOT" || exit 2

aqcat25_require_remote_path "$CHECKPOINT" "$PYTHON_BIN" "$RUNNER" || exit 2
test -x "$PYTHON_BIN" || exit 2
mkdir -p "$OUTPUT_ROOT"

if [ "$BACKEND" = "aqcat25" ]; then
  AQCAT_ENV=${AQCAT_ENV:-/home/sbq/sbq/aqcat25_ts_pilot/deployments/force_prediction_batch_v1_20260820/aqcat25_mz73_env.sh}
  aqcat25_setup_mz73_environment "$OUTPUT_ROOT" || exit 2
elif [ "$BACKEND" = "matris" ]; then
  MATRIS_SOURCE=${MATRIS_SOURCE:-$BENCHMARK_ROOT/vendor/MatRIS}
  aqcat25_require_remote_path "$MATRIS_SOURCE" || exit 2
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
