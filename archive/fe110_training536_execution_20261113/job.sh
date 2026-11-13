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
EXEC_ROOT=/home/sbq/sbq/fe110_force_training536_execution_20261113_v1
PACKAGE_ROOT=/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control
: "${SLURM_JOB_ID:?native Slurm job required}"
: "${EXEC_CONTRACT_SHA:?hash-bound execution contract required}"
[[ "$SLURM_JOB_ID" =~ ^[0-9]+$ ]]
export RUN_ROOT="$EXEC_ROOT/output/job_$SLURM_JOB_ID"
test ! -e "$RUN_ROOT"
mkdir -p "$RUN_ROOT"
export TMPDIR="$RUN_ROOT/tmp"
export XDG_CACHE_HOME="$RUN_ROOT/cache/xdg"
export TORCH_HOME="$RUN_ROOT/cache/torch"
export HF_HOME="$RUN_ROOT/cache/huggingface"
export MPLCONFIGDIR="$RUN_ROOT/cache/matplotlib"
export TORCH_EXTENSIONS_DIR="$RUN_ROOT/cache/extensions"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
source "$PACKAGE_ROOT/runtime/aqcat25_mz73_env.sh"
aqcat25_install_bootstrap_guard
aqcat25_require_mz73
aqcat25_setup_mz73_environment "$RUN_ROOT" "$MPLCONFIGDIR" "$TORCH_EXTENSIONS_DIR"
export PYTHONPATH="$PACKAGE_ROOT/runtime:$PYTHONPATH"
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
