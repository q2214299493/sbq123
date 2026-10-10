#!/bin/bash
#SBATCH --job-name=c2-ads-force-ft
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=c2-ads-force-ft-%j.out

set -euo pipefail
PACKAGE_ROOT=${PACKAGE_ROOT:?explicit package root required}
AUTHORIZATION=${AUTHORIZATION:?hash-bound explicit user authorization required}
case "$PACKAGE_ROOT" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
source "$PACKAGE_ROOT/runtime/aqcat25_mz73_env.sh"
aqcat25_require_remote_path "$PACKAGE_ROOT" "$AUTHORIZATION"
aqcat25_require_mz73
: "${SLURM_JOB_ID:?Slurm job id required}"
REQUEST=$PACKAGE_ROOT/training_request.json
ADAPTER=$PACKAGE_ROOT/runtime/force_finetune.py
RUN_ROOT=$PACKAGE_ROOT/output/job_$SLURM_JOB_ID
test ! -e "$RUN_ROOT"
aqcat25_setup_mz73_environment "$RUN_ROOT"
EXIT_RECORD=$RUN_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
finish() {
  code=$?
  trap - EXIT
  "$AQCAT_PYTHON" - "$EXIT_RECORD" "$REQUEST" "$SLURM_JOB_ID" "$STARTED_UTC" "$code" <<'PY'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
path,request,job,started,code=sys.argv[1:]
payload={'document_kind':'adsorption_finetune_producer_exit_record','job_id':job,
 'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),
 'exit_code':int(code),'request_sha256':hashlib.sha256(Path(request).read_bytes()).hexdigest(),
 'evidence_class':'producer_process_only_not_scheduler_accounting',
 'checkpoint_promoted':False,'scientific_acceptance':False}
with Path(path).open('x',encoding='utf-8') as f:json.dump(payload,f,indent=2)
PY
  exit "$code"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
"$AQCAT_PYTHON" "$ADAPTER" verify --request "$REQUEST"
"$AQCAT_PYTHON" "$ADAPTER" warm-start --request "$REQUEST" --authorization "$AUTHORIZATION" --output "$RUN_ROOT/warmstart.pt"
cd "$RUN_ROOT"
"$AQCAT_PYTHON" -m fairchem.core._cli --checkpoint "$RUN_ROOT/warmstart.pt" --mode train --config-yml "$PACKAGE_ROOT/config.yml" --amp
# Only this job's validation-selected checkpoint may be exported. Never fall
# back silently to an unvalidated last checkpoint or overwrite the baseline.
mapfile -t candidates < <(find "$RUN_ROOT" -type f -name best_checkpoint.pt)
[ "${#candidates[@]}" -eq 1 ]
cp -- "${candidates[0]}" "$RUN_ROOT/candidate.pt"
"$AQCAT_PYTHON" "$ADAPTER" evaluate-development --request "$REQUEST" --candidate "$RUN_ROOT/candidate.pt" --output "$RUN_ROOT/development_comparison.json"
