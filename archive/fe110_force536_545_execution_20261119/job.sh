#!/bin/bash
#SBATCH --partition=gpu
#SBATCH --nodelist=pc-G7466-M6
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --time=00:29:00
#SBATCH --no-requeue
set -euo pipefail
root=/home/sbq/sbq/force536_545_comparison_20261119_v1
runtime=/home/sbq/sbq/compute_pool_20261117/deployed/runtime/python
arm=$1
contract=$2
[[ "$arm" == control536 || "$arm" == increment545 ]]
[[ "$contract" =~ ^[0-9a-f]{64}$ ]]
[[ "$(hostname)" == pc-G7466-M6 && "$(realpath -e "$root")" == "$root" ]]
[[ "${SLURM_JOB_ID:-}" =~ ^[0-9]+$ ]]
output="$root/${arm}_$SLURM_JOB_ID"
mkdir "$output" "$output/tmp" "$output/cache"
export TMPDIR="$output/tmp" XDG_CACHE_HOME="$output/cache" TORCH_HOME="$output/cache/torch"
export HF_HOME="$output/cache/huggingface" MPLCONFIGDIR="$output/cache/matplotlib" TORCH_EXTENSIONS_DIR="$output/cache/extensions"
export CUDA_CACHE_PATH="$output/cache/cuda" CUDA_DEVICE_ORDER=PCI_BUS_ID
export PYTHONUTF8=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
export WITH_PYG_LIB=0 TORCH_SPARSE_USE_PYG_LIB=0 TORCH_SCATTER_USE_PYG_LIB=0
export WANDB_MODE=disabled HF_HUB_OFFLINE=1
started=$(date +%s)
finish() {
    code=$?
    trap - EXIT
    python3 -B - "$output/job_exit_record.json" "$SLURM_JOB_ID" "$arm" "$started" "$code" "$contract" <<'PY'
import json,sys,time
name, job, arm, start, code, sha = sys.argv[1:]
with open(name, "x", encoding="utf-8") as f:
    json.dump({"job_id":job,"arm":arm,"started_unix":int(start),"finished_unix":int(time.time()),
               "producer_exit_code":int(code),"contract_sha256":sha}, f, indent=2)
PY
    exit "$code"
}
trap finish EXIT
cd "$output"
timeout --signal=TERM --kill-after=10s 1700s "$runtime" -B "$root/payload/worker.py" "$arm" --contract-sha256 "$contract" --output "$output"
