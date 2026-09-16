#!/bin/bash
set -euo pipefail
. "$AQCAT_PILOT_ROOT/aqcat25_mz73_env.sh"
aqcat25_begin_execution
# Map only the scheduler-assigned physical device; never borrow another GPU.
gpu_uuid=$(/home/sbq/sbq/ml_ts_acceleration/venv/bin/python - <<'PY'
import json, os, re, subprocess
from pathlib import Path
index = os.environ.get('SLURM_JOB_GPUS', '')
assert re.fullmatch(r'[0-3]', index), 'expected exactly one Slurm-assigned physical GPU'
job = os.environ['SLURM_JOB_ID']
record = subprocess.run(['scontrol', 'show', 'job', '-d', job], capture_output=True, text=True, check=True)
assert f'GRES=gpu:1(IDX:{index})' in record.stdout, 'scheduler GPU identity mismatch'
query = subprocess.run(['nvidia-smi', '-i', index, '--query-gpu=index,uuid,memory.free',
                        '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
physical, uuid, free = [s.strip() for s in query.stdout.strip().split(',')]
assert physical == index and int(free) >= int(os.environ['MIN_FREE_GPU_MEMORY_MIB'])
evidence = dict(job_id=job, physical_index=int(index), gpu_uuid=uuid, free_memory_MiB=int(free),
                inherited_cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
                scheduler_allocation_matches_target=True)
with (Path(os.environ['REQUEST_ROOT'])/'gpu_binding.json').open('x') as handle:
    json.dump(evidence, handle, indent=2)
print(uuid)
PY
)
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="$gpu_uuid"
export TMPDIR="$REQUEST_ROOT/tmp"
echo "Using scheduler-assigned device $gpu_uuid"
exec bash "$REAL_JOB_WRAPPER"
