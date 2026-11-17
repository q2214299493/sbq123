#!/bin/bash
#SBATCH --job-name=force614-frozen536
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --nodelist=ubuntu-R5350-G6
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:09:00
#SBATCH --no-requeue

set -euo pipefail
: "${REQUEST_SHA:?hash-bound request required}"
EXEC_ROOT=/home/sbq/sbq/force_diagnosis536_gpu_20261117_v4
AQCAT_RUNTIME=/home/sbq/sbq/compute_pool_20261117/deployed/runtime
AQCAT_PYTHON="$AQCAT_RUNTIME/bin/python3.10"
export PYTHONHOME="$AQCAT_RUNTIME" PYTHONNOUSERSITE=1
export PYTHONPATH="$AQCAT_RUNTIME/extra/vendor:$AQCAT_RUNTIME/extra/python_pkgs:$AQCAT_RUNTIME/src/arkimede:$AQCAT_RUNTIME/src/mlps_finetuning:$AQCAT_RUNTIME/lib/python3.10/site-packages"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
export WITH_PYG_LIB=0 TORCH_SPARSE_USE_PYG_LIB=0 TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
if [[ "${1:-}" == --environment-preflight-only ]]; then
    export RUN_ROOT="$EXEC_ROOT/environment"
    export CUDA_VISIBLE_DEVICES=-1
else
    : "${SLURM_JOB_ID:?native Slurm allocation required}"
    printf 'Starting fixed-force job %s in %s\n' "$SLURM_JOB_ID" "$PWD"
    test "$(realpath -e "$EXEC_ROOT")" = "$(realpath -e "$PWD")"
    export RUN_ROOT="$EXEC_ROOT/output/job_$SLURM_JOB_ID"
fi
test ! -e "$RUN_ROOT"
mkdir -p "$RUN_ROOT"
for relative in tmp cache/xdg cache/torch cache/huggingface cache/matplotlib cache/extensions; do
    mkdir -p "$RUN_ROOT/$relative"
done
export TMPDIR="$RUN_ROOT/tmp" XDG_CACHE_HOME="$RUN_ROOT/cache/xdg" TORCH_HOME="$RUN_ROOT/cache/torch"
export HF_HOME="$RUN_ROOT/cache/huggingface" MPLCONFIGDIR="$RUN_ROOT/cache/matplotlib" TORCH_EXTENSIONS_DIR="$RUN_ROOT/cache/extensions"
if [[ "${1:-}" == --environment-preflight-only ]]; then
    "$AQCAT_PYTHON" -B "$EXEC_ROOT/runner.py" environment --request "$EXEC_ROOT/request.json" --request-sha256 "$REQUEST_SHA"
    exit 0
fi
finish() {
    code=$?
    trap - EXIT
    "$AQCAT_PYTHON" -B - "$RUN_ROOT/wrapper_exit.json" "$SLURM_JOB_ID" "$code" <<'PY'
import json,sys
from pathlib import Path
from datetime import datetime,timezone
with Path(sys.argv[1]).open('x') as stream:
    json.dump({'scheduler_job_id':sys.argv[2],'wrapper_exit_code':int(sys.argv[3]),'finished_UTC':datetime.now(timezone.utc).isoformat(),'not_scheduler_terminal_evidence':True},stream,indent=2)
PY
    exit "$code"
}
trap finish EXIT
timeout --signal=TERM --kill-after=10s 520s "$AQCAT_PYTHON" -B "$EXEC_ROOT/runner.py" run --request "$EXEC_ROOT/request.json" --request-sha256 "$REQUEST_SHA"
