#!/bin/bash
#SBATCH --job-name=fe110-c2-force10
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
set -euo pipefail
BATCH_ROOT=/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_force_diagnostic_20261008_v1
cd "$BATCH_ROOT"
export AQCAT_PILOT_ROOT="$BATCH_ROOT/runtime"
export AQCAT_ROOT=/home/sbq/sbq/aqcat25
export AQCAT_PYTHON=/home/sbq/sbq/ml_ts_acceleration/venv/bin/python
export TMPDIR="$BATCH_ROOT/tmp" XDG_CACHE_HOME="$BATCH_ROOT/cache/xdg"
export TORCH_HOME="$BATCH_ROOT/cache/torch" HF_HOME="$BATCH_ROOT/cache/huggingface"
. "$AQCAT_PILOT_ROOT/aqcat25_mz73_env.sh"
aqcat25_begin_execution
export OUTPUT_ROOT="$BATCH_ROOT/output"
export EXIT_RECORD="$OUTPUT_ROOT/producer_exit_record.json"
aqcat25_setup_mz73_environment
"$AQCAT_PYTHON" run_force_prediction.py
