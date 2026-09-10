#!/bin/bash
set -euo pipefail
export INHERITED_CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}
/home/sbq/sbq/ml_ts_acceleration/venv/bin/python - <<'PY'
import json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
target=os.environ['TARGET_GPU_UUID']
assert target=='GPU-483c224e-cc19-13e2-24ad-c83efd14fa75'
job=os.environ['SLURM_JOB_ID']
assert os.environ.get('SLURM_JOB_GPUS')=='0', 'scheduler must allocate physical GPU0'
q=subprocess.run(['squeue','-h','-o','%i|%T|%b'],capture_output=True,text=True,check=True)
assert not [x for x in q.stdout.splitlines() if x.split('|')[0]!=job and 'gpu' in x.lower()], 'other Slurm GPU jobs present; refuse device override'
r=subprocess.run(['nvidia-smi','-i',target,'--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
idx,uuid,free=[x.strip() for x in r.stdout.strip().split(',')]
assert idx=='0' and uuid==target
assert int(free)>=int(os.environ['MIN_FREE_GPU_MEMORY_MIB']), 'GPU0 free memory below startup threshold'
record={'observed_at':datetime.now(timezone.utc).isoformat(),'job_id':job,'physical_index':0,'target_uuid':uuid,'free_memory_MiB':int(free),'scheduler_job_gpus':os.environ.get('SLURM_JOB_GPUS'),'inherited_cuda_visible_devices':os.environ['INHERITED_CUDA_VISIBLE_DEVICES'],'binding_method':'explicit_user_requested_physical_GPU0_UUID','scheduler_allocation_matches_target':os.environ.get('SLURM_JOB_GPUS')=='0'}
with (Path(os.environ['REQUEST_ROOT'])/'gpu_binding.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record),flush=True)
PY
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="$TARGET_GPU_UUID"
export TMPDIR="$REQUEST_ROOT/tmp"
exec bash "$REAL_JOB_WRAPPER"
