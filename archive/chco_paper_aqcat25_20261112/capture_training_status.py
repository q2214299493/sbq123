"""Capture bounded native training status and original small output bytes."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

spec = importlib.util.spec_from_file_location('paper_training_capture_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)

REMOTE = '''import base64,hashlib,json,socket,subprocess
from pathlib import Path
p=json.loads(__PACKET__)
root=Path(p['remote_dir'])
if not root.resolve().is_relative_to(Path('/home/sbq/sbq').resolve(strict=True)):raise ValueError('path escape')
if socket.gethostname().split('.')[0]!=p['hostname']:raise ValueError('host mismatch')
x=subprocess.run(['scontrol','-o','show','job',p['job_id']],capture_output=True,timeout=10)
r={'hostname':socket.gethostname(),'remote_dir':str(root),'job_id':p['job_id'],'files':{},
   'native_scontrol':{'returncode':x.returncode,'stdout':x.stdout.decode(),'stderr':x.stderr.decode()}}
for name in ('output/training_failure.json','output/training_result.json','output/input_binding.json',
             'producer_exit_record.json','slurm-'+p['job_id']+'.err','slurm-'+p['job_id']+'.out'):
 f=root/name
 if f.is_file():
  size=f.stat().st_size
  if size<=100000:
   data=f.read_bytes();r['files'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'raw_base64':base64.b64encode(data).decode()}
  else:
   with f.open('rb') as stream:stream.seek(max(0,size-5000));tail=stream.read(5000)
   r['files'][name]={'bytes':size,'tail':tail.decode(errors='replace')}
print(json.dumps(r))
'''


def capture(case, replica=False):
    record = load_json_object(case / ('training_replica_submission_record.json' if replica else 'training_submission_record.json'))
    primary.require(record['status'] == 'SUBMITTED', 'no known native training job')
    packet = {'job_id': record['job_id'], 'remote_dir': record['remote_dir'], 'hostname': 'pc-G7466-M6' if replica else 'MZ73'}
    command = shlex.join(['python3', '-c', REMOTE.replace('__PACKET__', repr(json.dumps(packet)))])
    if replica:
        argv = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', 'buct2-gpu', command]
    else:
        backend = primary.remote.load_mz73_static_backend(primary.budget_owner.TIMEOUT_LEAF)
        argv = primary.remote.ssh_argv(backend, command)
    result = subprocess.run(argv, capture_output=True, timeout=25, check=True)
    primary.require(not result.stderr and len(result.stdout) <= 400000, 'unexpected capture response')
    data = json.loads(result.stdout)
    directory = case / ('training_capture_' + packet['hostname'] + '_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(exist_ok=False)
    (directory / 'remote_packet.json').write_bytes(result.stdout)
    for name, descriptor in data['files'].items():
        if 'raw_base64' in descriptor:
            raw = base64.b64decode(descriptor['raw_base64'], validate=True)
            primary.require(hashlib.sha256(raw).hexdigest() == descriptor['sha256'], 'returned file hash mismatch')
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    write_json_exclusive(directory / 'capture_receipt.json', {'argv': argv, 'returncode': result.returncode,
        'stdout_sha256': sha256_file(directory / 'remote_packet.json'), 'source_sha256': sha256_file(Path(__file__)),
        'job_id': record['job_id'], 'server': packet['hostname'], 'scheduler_evidence_class': 'native_scontrol_only'})
    from scripts.slurm_force_label import parse_scontrol_job
    native = data['native_scontrol']
    summary = parse_scontrol_job(native['stdout'], record['job_id']) if native['returncode'] == 0 else {'job_state': 'UNAVAILABLE', 'query_returncode': native['returncode']}
    failure = directory / 'output/training_failure.json'
    if failure.is_file():
        payload = load_json_object(failure)
        summary['failure'] = {'type': payload['type'], 'message': payload['message']}
    return {'capture': str(directory), 'host': packet['hostname'], **summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, required=True)
    parser.add_argument('--both', action='store_true')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda replica: capture(args.case_root.resolve(strict=True), replica), [False, True] if args.both else [False]))
    print(json.dumps(results))


if __name__ == '__main__':
    main()
