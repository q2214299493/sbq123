"""Capture bounded, byte-preserved runtime evidence for the corrected attempt."""
import base64
import json

from archive.int06_mid_gpu_20260910.gpu1_envfix import attempt
from scripts.artifact_io import write_json_exclusive


def main():
    record = json.loads((attempt.ATTEMPT / 'submit.stdout').read_bytes())
    job = record['job_id']
    code = f'''import subprocess,json,base64
from pathlib import Path
from datetime import datetime,timezone
root=Path({attempt.REMOTE_ATTEMPT!r});queries={{}}
for name,cmd in [
 ('scheduler',['scontrol','show','job',{job!r},'-o']),
 ('gpu_processes',['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory,process_name','--format=csv,noheader,nounits']),
 ('job_pids',['scontrol','listpids',{job!r}])]:
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
 queries[name]={{'exit_code':r.returncode,'stdout':r.stdout[:8000],'stderr':r.stderr[:1000]}}
files={{}}
names=['gpu_binding.json','gpu_submission_record.json','gpu_submission_reservation.json','sbatch_raw.json','output/production/ml_neb_state.json']
names += [str(p.relative_to(root)) for p in (root/'output/production').glob('producer_exit_record*.json')]
for name in names:
 p=root/name
 if p.is_file() and p.stat().st_size<200000:files[name]=base64.b64encode(p.read_bytes()).decode()
logs={{}}
for p in [root/'logs'/('production-'+{job!r}+'.out'),*(root/'output/production').glob('*.log')]:
 if p.is_file():
  with p.open('rb') as f:
   f.seek(max(0,p.stat().st_size-4500));logs[str(p.relative_to(root))]=f.read().decode('utf-8','replace')
print(json.dumps({{'observed_at':datetime.now(timezone.utc).isoformat(),'queries':queries,'files':files,'logs':logs}}))
'''
    # invoke preserves the complete remote stdout; the terminal view is bounded.
    attempt.invoke(code, 'checkpoint')
    data = json.loads((attempt.ATTEMPT / 'checkpoint.stdout').read_bytes())
    folder = attempt.ATTEMPT / ('checkpoint_job' + job)
    folder.mkdir(exist_ok=False)
    for name, encoded in data.pop('files').items():
        target = folder / name
        assert target.resolve().is_relative_to(folder.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(base64.b64decode(encoded))
    write_json_exclusive(folder / 'checkpoint.json', data)
    print(json.dumps(data['logs'], ensure_ascii=False))


if __name__ == '__main__':
    main()
