#!/bin/bash
#SBATCH --job-name=aqcat536-smoke
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --nodelist=MZ73
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:29:00
#SBATCH --no-requeue

set -euo pipefail
EXEC_ROOT=/home/sbq/sbq/fe110_force_training536_execution_20261113_v2
PACKAGE_ROOT=/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control
AQCAT_ROOT=/home/sbq/sbq/aqcat25
AQCAT_PYTHON=/home/sbq/sbq/ml_ts_acceleration/venv/bin/python
: "${EXEC_CONTRACT_SHA:?hash-bound execution contract required}"
[[ "$(hostname)" == MZ73 ]]
BOUNDARY=$(realpath -e /home/sbq/sbq)
[[ "$BOUNDARY" == /home/ubuntu/hdd/sbq/sbq ]]
for path in "$EXEC_ROOT" "$PACKAGE_ROOT" "$AQCAT_ROOT" "$AQCAT_PYTHON"; do
  case "$path" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
  case "$(realpath -m "$path")" in "$BOUNDARY"/*) ;; *) exit 2 ;; esac
done
python3 -B - "$EXEC_ROOT" "$EXEC_CONTRACT_SHA" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);contract=root/'execution_contract.json'
assert hashlib.sha256(contract.read_bytes()).hexdigest()==sys.argv[2]
record=json.loads(contract.read_text())
assert record['canonical_remote_boundary_observed']==str(Path('/home/sbq/sbq').resolve())
assert record['previous_allocated_seconds']+record['scheduler_seconds']+record['scheduler_killwait_seconds']<=1800
for item in record['execution_files']:
 path=root/item['path']
 assert path.resolve().is_relative_to(root.resolve())
 assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
PY
if [[ "${1:-}" == --environment-preflight-only ]]; then
  export RUN_ROOT="$EXEC_ROOT/environment_preflight"
  export CUDA_VISIBLE_DEVICES=-1
else
  : "${SLURM_JOB_ID:?native Slurm job required}"
  [[ "$SLURM_JOB_ID" =~ ^[0-9]+$ ]]
  export RUN_ROOT="$EXEC_ROOT/output/job_$SLURM_JOB_ID"
fi
test ! -e "$RUN_ROOT"
mkdir -p "$RUN_ROOT"
for name in tmp cache/xdg cache/torch cache/huggingface cache/matplotlib cache/extensions; do
  case "$(realpath -m "$RUN_ROOT/$name")" in "$BOUNDARY"/*) ;; *) exit 2 ;; esac
  mkdir -p "$RUN_ROOT/$name"
done
export TMPDIR="$RUN_ROOT/tmp" XDG_CACHE_HOME="$RUN_ROOT/cache/xdg"
export TORCH_HOME="$RUN_ROOT/cache/torch" HF_HOME="$RUN_ROOT/cache/huggingface"
export MPLCONFIGDIR="$RUN_ROOT/cache/matplotlib" TORCH_EXTENSIONS_DIR="$RUN_ROOT/cache/extensions"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
export WITH_PYG_LIB=0 TORCH_SPARSE_USE_PYG_LIB=0 TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PYTHONPATH="$PACKAGE_ROOT/runtime:$AQCAT_ROOT/python_pkgs:$AQCAT_ROOT/vendor"
if [[ "${1:-}" == --environment-preflight-only ]]; then
  "$AQCAT_PYTHON" -B -m scripts.adsorption.force_training_preflight \
    --request "$PACKAGE_ROOT/training_request.json" --native-cli
  exit 0
fi
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
finish() {
  code=$?
  trap - EXIT
  python3 -B - "$RUN_ROOT/job_exit_record.json" "$SLURM_JOB_ID" "$STARTED_UTC" "$code" "$EXEC_CONTRACT_SHA" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
path,job,started,code,contract=sys.argv[1:]
with Path(path).open('x') as handle:
 json.dump({'scheduler_job_id':job,'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),
  'producer_exit_code':int(code),'execution_contract_sha256':contract,
  'scheduler_terminal_state_not_inferred':True,'model_promoted':False,'new_DFT':False},handle,indent=2)
PY
  exit "$code"
}
trap finish EXIT
timeout --signal=TERM --kill-after=10s 1700s "$AQCAT_PYTHON" -B "$EXEC_ROOT/entry.py" \
  --contract "$EXEC_ROOT/execution_contract.json" --contract-sha256 "$EXEC_CONTRACT_SHA"
