#!/bin/bash
#SBATCH --job-name=relax545-580
#SBATCH --partition=cpu
#SBATCH --nodelist=MZ73
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=cpupool:8
#SBATCH --mem=32G
#SBATCH --time=00:09:00
#SBATCH --no-requeue
set -euo pipefail
[[ "$1" =~ ^[a-f0-9]{64}$ && "$(hostname)" == MZ73 && "$SLURM_JOB_ID" =~ ^[0-9]+$ ]]
root=$(realpath -e "$PWD")
[[ "$root" == /home/ubuntu/hdd/sbq/sbq/force545_580_relax_20261120_v1 ]]
output="$root/job_$SLURM_JOB_ID"
mkdir "$output" "$output/tmp" "$output/cache"
export CUDA_VISIBLE_DEVICES=-1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1
export OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8
export WITH_PYG_LIB=0 TORCH_SPARSE_USE_PYG_LIB=0 TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled HF_HUB_OFFLINE=1
export PYTHONPATH="$root:/home/sbq/sbq/aqcat25_ts_pilot:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
export TMPDIR="$output/tmp" XDG_CACHE_HOME="$output/cache" TORCH_HOME="$output/cache/torch"
export HF_HOME="$output/cache/hf" MPLCONFIGDIR="$output/cache/mpl" TORCH_EXTENSIONS_DIR="$output/cache/extensions"
finish() {
    local code=$?
    trap - EXIT
    python3 -B - "$output/exit.json" "$SLURM_JOB_ID" "$code" "$1" <<'PY'
import json, sys
with open(sys.argv[1], "x", encoding="utf-8") as f:
    json.dump({"job_id": sys.argv[2], "exit_code": int(sys.argv[3]), "request_sha256": sys.argv[4]}, f)
PY
    exit "$code"
}
trap 'finish "$1"' EXIT
cd "$output"
timeout --signal=TERM --kill-after=5s 535s /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -B "$root/worker.py" "$1" "$output"
