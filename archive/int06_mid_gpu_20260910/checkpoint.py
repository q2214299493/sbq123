"""Capture one bounded scheduler/runtime checkpoint for GPU job 1512."""
import base64
import json
import subprocess

from archive.int06_mid_gpu_20260910.inspect_remote import BASE
from archive.int06_mid_gpu_20260910.prepare import REMOTE
from archive.int06_mid_gpu_20260910.stage import SSH, PYTHON
from scripts.artifact_io import write_json_exclusive

REMOTE_CODE = r'''
import base64,json,subprocess
from pathlib import Path
from datetime import datetime,timezone
root=Path(REMOTE_ROOT)
queries={}
for name,command in {
 'squeue':['squeue','-h','-j','1512','-o','%i|%T|%M|%R'],
 'scontrol':['scontrol','show','job','1512','-o'],
}.items():
 r=subprocess.run(command,capture_output=True,text=True,timeout=20)
 queries[name]={'exit_code':r.returncode,'stdout':r.stdout[:8000],'stderr':r.stderr[:1000]}
files={}
names=['gpu_submission_record.json','gpu_submission_reservation.json','sbatch_raw.json',
       'output/production/ml_neb_state.json']
names += [str(p.relative_to(root)) for p in (root/'output/production').glob('producer_exit_record*.json')]
for name in names:
 p=root/name
 if p.is_file() and p.stat().st_size<50000:
  files[name]=base64.b64encode(p.read_bytes()).decode()
tails={}
for name in ['logs/production-1512.out','output/production/ordinary_ml_neb.log']:
 p=root/name
 if p.is_file():
  with p.open('rb') as h:
   h.seek(max(0,p.stat().st_size-6000))
   tails[name]=h.read().decode('utf-8','replace')
print(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'queries':queries,'files':files,'tails':tails}))
'''


def main():
    destination=BASE/'checkpoint_job1512'
    destination.mkdir(exist_ok=False)
    code=REMOTE_CODE.replace('REMOTE_ROOT',repr(REMOTE))
    result=subprocess.run([*SSH,PYTHON+' -'],input=code.encode(),capture_output=True,timeout=55)
    (destination/'capture.stdout').write_bytes(result.stdout)
    (destination/'capture.stderr').write_bytes(result.stderr)
    write_json_exclusive(destination/'capture_receipt.json',{'exit_code':result.returncode})
    result.check_returncode()
    payload=json.loads(result.stdout)
    for name,encoded in payload.pop('files').items():
        target=destination/name
        assert target.resolve().is_relative_to(destination.resolve())
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(base64.b64decode(encoded))
    write_json_exclusive(destination/'checkpoint.json',payload)
    print(json.dumps(payload,ensure_ascii=False))


if __name__=='__main__':
    main()
