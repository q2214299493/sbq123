"""Stage/check/submit the authorized remote driver; every call retains receipts."""
import argparse
import base64
import json
import subprocess

from archive.int06_mid_gpu_20260910.inspect_remote import BASE
from archive.int06_mid_gpu_20260910.prepare import REMOTE
from archive.int06_mid_gpu_20260910.stage import SSH, PYTHON
from scripts.artifact_io import sha256_file, write_json_exclusive


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['stage','check','submit'],required=True)
    mode=parser.parse_args().mode
    execution=BASE/'execution_20260910'
    if mode=='stage':
        files={name:base64.b64encode((execution/name).read_bytes()).decode('ascii') for name in
               ['submit_remote.py','allocated_gpu_guard.sh','authorization.json']}
        code=('from pathlib import Path\nimport base64\np=Path('+repr(REMOTE+'/execution_20260910')+')\n'
              'assert p.is_relative_to(Path("/home/sbq/sbq"))\np.mkdir(exist_ok=False)\n'
              'files='+repr(files)+'\n'
              'for name, data in files.items():\n with (p/name).open("xb") as handle: handle.write(base64.b64decode(data))\n'
              'print("execution driver staged")\n')
        command=[*SSH,PYTHON+' -']
        data=code.encode()
    else:
        command=[*SSH,PYTHON+' -B '+REMOTE+'/execution_20260910/submit_remote.py --mode '+mode]
        data=None
    assert not (execution/(mode+'.receipt.json')).exists(), 'inspect prior receipt before any retry'
    if mode=='submit':
        ready=json.loads((execution/'check.result.json').read_text(encoding='utf-8'))
        assert ready['status']=='READY' and not ready['submission_performed']
        write_json_exclusive(execution/'local_submission_reservation.json',{
            'status':'pending_remote_receipt','authorization_sha256':sha256_file(execution/'authorization.json')})
    result=subprocess.run(command,input=data,capture_output=True,timeout=55)
    with (execution/(mode+'.stdout')).open('xb') as handle:
        handle.write(result.stdout)
    with (execution/(mode+'.stderr')).open('xb') as handle:
        handle.write(result.stderr)
    write_json_exclusive(execution/(mode+'.receipt.json'),{'exit_code':result.returncode})
    result.check_returncode()
    if mode!='stage':
        payload=json.loads(result.stdout)
        write_json_exclusive(execution/(mode+'.result.json'),payload)
        print({key:payload[key] for key in ('status','request_sha256','job_id','submitted_at') if key in payload})
    else:
        print(result.stdout.decode())


if __name__=='__main__':
    main()
