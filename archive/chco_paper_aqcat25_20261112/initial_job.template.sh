#!/bin/bash
set -uo pipefail
base=$(realpath -e -- /home/sbq/sbq) || exit 2
case "$(pwd -P)" in "$base"/*) ;; *) exit 2 ;; esac
record_exit() {
  local code=$?
  trap - EXIT
  set -C
  printf '{"document_kind":"producer_exit_record","evidence_class":"process_only_not_scheduler_authority","job_id":"%s","exit_code":%d,"request_sha256":"__REQUEST_SHA__","DFT_performed":false,"training_performed":false}\n' "${SLURM_JOB_ID:-unknown}" "$code" > producer_exit_record.json
  exit "$code"
}
trap record_exit EXIT
: "${SLURM_JOB_ID:?missing allocation}"
export PYTHONDONTWRITEBYTECODE=1 CUDA_CACHE_DISABLE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
export PYTHONPATH="$PWD:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
export XDG_CACHE_HOME="$PWD/cache" TORCH_HOME="$PWD/cache/torch" HF_HOME="$PWD/cache/huggingface" TMPDIR="$PWD/tmp"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WANDB_MODE=disabled
/home/sbq/sbq/ml_ts_acceleration/venv/bin/python -B "$PWD/initial_candidate.py" --request "$PWD/request.json" --request-sha256 __REQUEST_SHA__ --output "$PWD/output"
