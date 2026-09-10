#!/bin/bash

set -euo pipefail

MIN_FREE_GPU_MEMORY_MIB=${MIN_FREE_GPU_MEMORY_MIB:-12000}
REAL_JOB_WRAPPER=${REAL_JOB_WRAPPER:?REAL_JOB_WRAPPER is required}
allocated=${CUDA_VISIBLE_DEVICES:-}
test -n "$allocated" || {
  echo "CUDA_VISIBLE_DEVICES is empty" >&2
  exit 3
}
gpu_token=${allocated%%,*}
free_mib=$(nvidia-smi -i "$gpu_token" --query-gpu=memory.free --format=csv,noheader,nounits | tr -d '[:space:]')
gpu_uuid=$(nvidia-smi -i "$gpu_token" --query-gpu=uuid --format=csv,noheader,nounits | tr -d '[:space:]')
case "$free_mib" in
  ''|*[!0-9]*)
    echo "invalid free-memory value for allocated GPU $gpu_token: $free_mib" >&2
    exit 3
    ;;
esac
if [ "$free_mib" -lt "$MIN_FREE_GPU_MEMORY_MIB" ]; then
  echo "allocated GPU $gpu_token ($gpu_uuid) has only $free_mib MiB free; require $MIN_FREE_GPU_MEMORY_MIB MiB" >&2
  exit 3
fi
echo "ALLOCATED_GPU=$gpu_token|UUID=$gpu_uuid|FREE_MIB=$free_mib"
exec bash "$REAL_JOB_WRAPPER"
