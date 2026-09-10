"""Prepare and submit one explicitly requested physical-GPU1 attempt."""
import argparse
import base64
import json
import subprocess
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910.inspect_remote import BASE
from archive.int06_mid_gpu_20260910.prepare import REMOTE
from archive.int06_mid_gpu_20260910.stage import SSH, PYTHON
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ATTEMPT = BASE / 'attempt_gpu1_20260910'
REMOTE_ATTEMPT = REMOTE + '_gpu1'
UUID = 'GPU-450609b3-d1fd-ac33-d03a-79891be402da'


def invoke(code, name):
    assert not (ATTEMPT / (name + '.receipt.json')).exists()
    result = subprocess.run([*SSH, PYTHON + ' -'], input=code.encode(), capture_output=True, timeout=55)
    for suffix, data in [('stdout', result.stdout), ('stderr', result.stderr)]:
        with (ATTEMPT / (name + '.' + suffix)).open('xb') as handle:
            handle.write(data)
    write_json_exclusive(ATTEMPT / (name + '.receipt.json'), {'exit_code': result.returncode})
    result.check_returncode()
    print(result.stdout.decode()[:5000])


def prepare():
    ATTEMPT.mkdir(exist_ok=False)
    execution = ATTEMPT / 'execution'
    execution.mkdir()
    driver = (BASE / 'execution_20260910/submit_remote.py').read_text(encoding='utf-8')
    driver = driver.replace("auth['user_instruction']=='提交'", "auth['user_instruction']=='提交gpu1'")
    driver = driver.replace("auth['action']=='initial_gpu_path_candidate'", "auth['action']=='user_requested_gpu1_attempt'")
    driver = driver.replace("job_name='int06-mid-mlneb'", "job_name='int06-mid-gpu1'")
    driver = driver.replace("'MIN_FREE_GPU_MEMORY_MIB':'12000'", "'MIN_FREE_GPU_MEMORY_MIB':'12000','TARGET_GPU_UUID':auth['target_gpu_uuid']")
    with (execution / 'submit_remote.py').open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(driver)
    # Existing project wrappers support explicit physical-device selection. Keep
    # scheduler allocation and actual CUDA binding separately visible in evidence.
    guard = '''#!/bin/bash
set -euo pipefail
export INHERITED_CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}
/home/sbq/sbq/ml_ts_acceleration/venv/bin/python - <<'PY'
import json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
target=os.environ['TARGET_GPU_UUID']
assert target=='GPU-450609b3-d1fd-ac33-d03a-79891be402da'
job=os.environ['SLURM_JOB_ID']
q=subprocess.run(['squeue','-h','-o','%i|%T|%b'],capture_output=True,text=True,check=True)
assert not [x for x in q.stdout.splitlines() if x.split('|')[0]!=job and 'gpu' in x.lower()], 'other Slurm GPU jobs present; refuse device override'
r=subprocess.run(['nvidia-smi','-i',target,'--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
idx,uuid,free=[x.strip() for x in r.stdout.strip().split(',')]
assert idx=='1' and uuid==target
assert int(free)>=int(os.environ['MIN_FREE_GPU_MEMORY_MIB']), 'GPU1 free memory below startup threshold'
record={'observed_at':datetime.now(timezone.utc).isoformat(),'job_id':job,'physical_index':1,'target_uuid':uuid,'free_memory_MiB':int(free),'scheduler_job_gpus':os.environ.get('SLURM_JOB_GPUS'),'inherited_cuda_visible_devices':os.environ['INHERITED_CUDA_VISIBLE_DEVICES'],'binding_method':'explicit_user_requested_physical_GPU1_UUID','scheduler_allocation_matches_target':os.environ.get('SLURM_JOB_GPUS')=='1'}
with (Path(os.environ['REQUEST_ROOT'])/'gpu_binding.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record),flush=True)
PY
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="$TARGET_GPU_UUID"
exec bash "$REAL_JOB_WRAPPER"
'''
    with (execution / 'allocated_gpu_guard.sh').open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(guard)
    auth = load_json_object(BASE / 'execution_20260910/authorization.json')
    auth.update(authorized_at=datetime.now(timezone.utc).isoformat(), user_instruction='提交gpu1',
                action='user_requested_gpu1_attempt', remote_root=REMOTE_ATTEMPT,
                target_gpu_uuid=UUID, target_physical_gpu_index=1,
                driver_sha256=sha256_file(execution / 'submit_remote.py'),
                guard_sha256=sha256_file(execution / 'allocated_gpu_guard.sh'),
                scope='One new unchanged ML-NEB request on physical GPU1, explicitly requested again after explaining scheduler/device mismatch; use Slurm for one GPU, 4 CPUs, 40GB, six-hour job; record actual UUID separately; no automatic retry.',
                prior_failed_job='1512')
    write_json_exclusive(execution / 'authorization.json', auth)
    print('Prepared new immutable attempt; unchanged scientific request; explicit physical GPU1 binding')


def stage():
    files = {name: base64.b64encode((ATTEMPT / 'execution' / name).read_bytes()).decode()
             for name in ['submit_remote.py', 'allocated_gpu_guard.sh', 'authorization.json']}
    code = f'''import base64,json,shutil,subprocess
from pathlib import Path
source=Path({REMOTE!r});root=Path({REMOTE_ATTEMPT!r})
assert root.is_relative_to(Path('/home/sbq/sbq')) and not root.exists()
q=subprocess.run(['squeue','-h','-o','%i|%T|%b'],capture_output=True,text=True,check=True)
assert not any('gpu' in x.lower() for x in q.stdout.splitlines()), 'other scheduler GPU jobs present'
r=subprocess.run(['nvidia-smi','-i',{UUID!r},'--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
parts=[x.strip() for x in r.stdout.strip().split(',')]
assert parts[0]=='1' and int(parts[2])>=12000
root.mkdir()
names=list(json.loads((source/'payload_manifest.json').read_text())['files'])+['payload_manifest.json','preflight.py']
for name in dict.fromkeys(names):
 target=root/name
 assert target.resolve().is_relative_to(root)
 target.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(source/name,target)
(root/'execution').mkdir()
for name,data in {files!r}.items():
 with (root/'execution'/name).open('xb') as f:f.write(base64.b64decode(data))
print('GPU1 preflight: '+r.stdout.strip()+'; unchanged payload copied to new attempt')
'''
    invoke(code, 'stage')


def run(mode):
    if mode == 'submit':
        checked = json.loads((ATTEMPT / 'check.stdout').read_text())
        assert checked['status'] == 'READY' and not checked['submission_performed']
        write_json_exclusive(ATTEMPT / 'local_submission_reservation.json',
                             {'authorization_sha256': sha256_file(ATTEMPT / 'execution/authorization.json')})
    invoke(f"import runpy,sys\nsys.argv=['submit_remote.py','--mode',{mode!r}]\nrunpy.run_path({(REMOTE_ATTEMPT + '/execution/submit_remote.py')!r},run_name='__main__')\n", mode)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'stage', 'check', 'submit'])
    mode = parser.parse_args().mode
    if mode == 'prepare':
        prepare()
    elif mode == 'stage':
        stage()
    else:
        run(mode)
