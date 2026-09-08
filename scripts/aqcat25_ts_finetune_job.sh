#!/bin/bash
#SBATCH --job-name=aqcat-ts-force-ft
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/logs/aqcat-ts-force-ft-%j.out

set -uo pipefail

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
export AQCAT_PILOT_ROOT="$PILOT_ROOT"
TRAINING_MANIFEST=${TRAINING_MANIFEST:?TRAINING_MANIFEST is required}
SOURCE_MANIFEST_SHA256=${SOURCE_MANIFEST_SHA256:?SOURCE_MANIFEST_SHA256 is required}
RUN_ROOT=$PILOT_ROOT/active_learning/job_$SLURM_JOB_ID
OUTPUT_ROOT=$RUN_ROOT/output
EXIT_RECORD=$OUTPUT_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$RUN_ROOT" "$OUTPUT_ROOT"

write_exit_record() {
  local exit_code=$1
  STARTED_UTC=$STARTED_UTC EXIT_CODE=$exit_code EXIT_RECORD=$EXIT_RECORD \
    SOURCE_MANIFEST_SHA256=$SOURCE_MANIFEST_SHA256 "$AQCAT_PYTHON" - <<'PY'
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from artifact_io import write_json_atomic

path = Path(os.environ["EXIT_RECORD"])
code = int(os.environ["EXIT_CODE"])
payload = {
    "gpu_job_id": os.environ["SLURM_JOB_ID"],
    "hostname": socket.gethostname(),
    "started_utc": os.environ["STARTED_UTC"],
    "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "exit_code": code,
    "status": "success" if code == 0 else "failed",
    "training_manifest_sha256": os.environ["SOURCE_MANIFEST_SHA256"],
    "evidence_class": "producer_process_only_not_scheduler_accounting",
}
write_json_atomic(path, payload, ensure_ascii=True)
PY
}

run_training() {
  echo "$SOURCE_MANIFEST_SHA256  $TRAINING_MANIFEST" | sha256sum -c - || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_schema.py" "$TRAINING_MANIFEST" \
    --kind aqcat25_ts_force_only_training_manifest || return $?
  aqcat25_require_mz73 || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_training_data.py" build-db \
    --manifest "$TRAINING_MANIFEST" --output "$RUN_ROOT/training.db" --split train || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_training_data.py" build-db \
    --manifest "$TRAINING_MANIFEST" --output "$RUN_ROOT/validation.db" --split validation || return $?
  EPOCHS=$(
    "$AQCAT_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["epochs"])' \
      "$TRAINING_MANIFEST"
  ) || return $?
  BASE_CHECKPOINT=$(
    "$AQCAT_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["base_checkpoint"]["path"])' \
      "$TRAINING_MANIFEST"
  ) || return $?
  BASE_SHA=$(
    "$AQCAT_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["base_checkpoint"]["sha256"])' \
      "$TRAINING_MANIFEST"
  ) || return $?
  echo "$BASE_SHA  $BASE_CHECKPOINT" | sha256sum -c - || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_training_data.py" prepare-config \
    --template "$PILOT_ROOT/force_only_config.yml" --dataset "$RUN_ROOT/training.db" \
    --validation-dataset "$RUN_ROOT/validation.db" --output "$RUN_ROOT/config.yml" --epochs "$EPOCHS" || return $?
  cd "$RUN_ROOT" || return $?
  "$AQCAT_PYTHON" -m fairchem.core._cli \
    --checkpoint "$BASE_CHECKPOINT" --mode train --config-yml config.yml --amp || return $?
  NEW_CHECKPOINT=$(find "$RUN_ROOT" -type f -name 'best_checkpoint.pt' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)
  if [ -z "$NEW_CHECKPOINT" ]; then
    NEW_CHECKPOINT=$(find "$RUN_ROOT" -type f -name 'checkpoint.pt' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)
  fi
  test -n "$NEW_CHECKPOINT" -a -s "$NEW_CHECKPOINT" || return 20
  cp "$NEW_CHECKPOINT" "$OUTPUT_ROOT/model.pt" || return $?
  THRESHOLDS_REL=$(
    "$AQCAT_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["replay_evidence"]["thresholds_path"])' \
      "$TRAINING_MANIFEST"
  ) || return $?
  THRESHOLDS_PATH=$(dirname "$TRAINING_MANIFEST")/$THRESHOLDS_REL
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_checkpoint_validation.py" \
    --checkpoint "$OUTPUT_ROOT/model.pt" --database "$RUN_ROOT/validation.db" \
    --thresholds "$THRESHOLDS_PATH" --output "$OUTPUT_ROOT/checkpoint_validation.json" || return $?
}

write_result() {
  local result_path=$OUTPUT_ROOT/finetune_result_manifest.json
  RESULT_PATH=$result_path CHECKPOINT=$OUTPUT_ROOT/model.pt \
    CHECKPOINT_VALIDATION=$OUTPUT_ROOT/checkpoint_validation.json \
    TRAINING_MANIFEST=$TRAINING_MANIFEST EXIT_RECORD=$EXIT_RECORD \
    "$AQCAT_PYTHON" - <<'PY'
import os
import socket
from pathlib import Path
from artifact_io import load_json_object, sha256_file, write_json_atomic

manifest_path = Path(os.environ["TRAINING_MANIFEST"])
manifest = load_json_object(manifest_path)
checkpoint = Path(os.environ["CHECKPOINT"])
checkpoint_validation = Path(os.environ["CHECKPOINT_VALIDATION"])
validation = load_json_object(checkpoint_validation)
exit_record = Path(os.environ["EXIT_RECORD"])
payload = {
    "schema_version": 1,
    "document_kind": "aqcat25_ts_force_only_finetune_result",
    "status": "success",
    "result_class": "force_only_finetuned_checkpoint_candidate",
    "hostname": socket.gethostname(),
    "gpu_job_id": os.environ["SLURM_JOB_ID"],
    "training_manifest_sha256": sha256_file(manifest_path),
    "base_checkpoint_sha256": manifest["base_checkpoint"]["sha256"],
    "checkpoint": {"path": str(checkpoint), "sha256": sha256_file(checkpoint)},
    "checkpoint_validation": {
        "path": checkpoint_validation.name,
        "sha256": sha256_file(checkpoint_validation),
        "status": validation["status"],
        "checkpoint_sha256": validation["checkpoint_sha256"],
        "metrics": validation["metrics"],
        "scope": validation["scope"],
    },
    "producer_exit_record": {"path": str(exit_record), "sha256": sha256_file(exit_record)},
    "reportable_final_energy": False,
    "scientific_acceptance": False,
}
write_json_atomic(Path(os.environ["RESULT_PATH"]), payload, ensure_ascii=True)
PY
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_ts_schema.py" "$result_path" \
    --kind aqcat25_ts_force_only_finetune_result
}

exit_code=0
run_training || exit_code=$?
write_exit_record "$exit_code"
if [ "$exit_code" -eq 0 ]; then
  write_result || exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    write_exit_record "$exit_code"
  fi
fi
exit "$exit_code"
