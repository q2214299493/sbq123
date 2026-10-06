#!/bin/bash
#SBATCH --job-name=fe110-five-c2-ads
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=02:00:00
set -euo pipefail
BATCH_ROOT=/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_v1
export AQCAT_PILOT_ROOT="$BATCH_ROOT/runtime"
export DOMAIN_CALIBRATION=/home/sbq/sbq/aqcat25_ts_pilot/aqcat25_domain_calibration.json
export AQCAT_ROOT=/home/sbq/sbq/aqcat25
export AQCAT_PYTHON=/home/sbq/sbq/ml_ts_acceleration/venv/bin/python
export TMPDIR="$BATCH_ROOT/tmp"
export XDG_CACHE_HOME="$BATCH_ROOT/cache/xdg"
export TORCH_HOME="$BATCH_ROOT/cache/torch"
export HF_HOME="$BATCH_ROOT/cache/huggingface"
set -x
. "$AQCAT_PILOT_ROOT/aqcat25_mz73_env.sh"
aqcat25_begin_execution
aqcat25_setup_mz73_environment
cd "$BATCH_ROOT"
"$AQCAT_PYTHON" preflight.py
set +x
failed=0
while read -r name digest; do
  export HANDOFF_ROOT="$BATCH_ROOT/$name"
  export SOURCE_HANDOFF_SHA256="$digest"
  code=0
  bash "$AQCAT_PILOT_ROOT/aqcat25_gpu_job.sh" > "$BATCH_ROOT/$name/job_${SLURM_JOB_ID}.log" 2>&1 || code=$?
  printf '%s %s\n' "$name" "$code" >> "$BATCH_ROOT/batch_status_${SLURM_JOB_ID}.txt"
  if [ "$code" -ne 0 ]; then failed=1; break; fi
done < <("$AQCAT_PYTHON" -c 'import json; d=json.load(open("batch_manifest.json")); [print(x["name"],x["handoff_sha256"]) for x in d["handoffs"]]')
exit "$failed"
