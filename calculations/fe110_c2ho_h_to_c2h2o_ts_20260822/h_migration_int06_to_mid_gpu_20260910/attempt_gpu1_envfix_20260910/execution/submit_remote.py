"""Submit the explicitly authorized, hash-bound initial GPU candidate once."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def write_new(path, value):
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['check','submit'],required=True)
    args=parser.parse_args()
    execution=Path(__file__).resolve().parent
    auth=json.loads((execution/'authorization.json').read_text())
    root=Path(auth['remote_root']).resolve()
    assert root.is_relative_to(Path('/home/sbq/sbq')) and execution.parent==root
    assert socket.gethostname()=='MZ73'
    assert auth['authorized'] is True and auth['user_instruction']=='提交gpu1'
    assert auth['action']=='user_requested_gpu1_attempt' and not auth['vasp_authorized']
    assert auth['driver_sha256']==digest(Path(__file__))
    assert auth['guard_sha256']==digest(execution/'allocated_gpu_guard.sh')
    assert auth['request_sha256']==digest(root/'request.json')
    assert auth['payload_manifest_sha256']==digest(root/'payload_manifest.json')
    request=json.loads((root/'request.json').read_text())
    assert request['scheduler_resources']==auth['scheduler_resources']
    assert request['ordinary_ml_neb']['max_steps']==400 and request['ordinary_ml_neb']['ml_ci']=='off'
    assert len(request['images'])==5 and request['fixed_atom_indices_zero_based']==list(range(18))
    receipt=root/'gpu_submission_record.json'
    reservation=root/'gpu_submission_reservation.json'
    assert not receipt.exists() and not reservation.exists(), 'existing submission requires reconciliation, never retry'
    output=root/'output/production'
    assert not output.exists(), 'existing output must not be overwritten'
    preflight=subprocess.run([sys.executable,'-B',str(root/'preflight.py')],capture_output=True,text=True,check=True)
    checked=json.loads(preflight.stdout)
    assert checked['status']=='PASS' and not checked['model_execution_performed']
    queue=subprocess.run(['squeue','-h','-u','sbq','-o','%i|%j|%T|%R'],capture_output=True,text=True,check=True)
    job_name='int06-mid-gpu1'
    assert all(row.split('|')[1]!=job_name for row in queue.stdout.splitlines()), 'duplicate live job name'
    resources=auth['scheduler_resources']
    assert resources=={'backend':'MZ73_slurm','nodes':1,'tasks':1,'cpus_per_task':4,'gpus':1,'memory_GB':40,'walltime':'06:00:00'}
    environment={
        'AQCAT_PILOT_ROOT':str(root/'runtime'),'REQUEST_ROOT':str(root),
        'SOURCE_REQUEST_SHA256':auth['request_sha256'],'OUTPUT_ROOT':str(output),
        'PRIMARY_CHECKPOINT':request['models']['primary']['remote_checkpoint_path'],
        'SECONDARY_CHECKPOINT':request['models']['secondary']['remote_checkpoint_path'],
        'MATRIS_SOURCE':'/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS',
        'MIN_FREE_GPU_MEMORY_MIB':'12000','TARGET_GPU_UUID':auth['target_gpu_uuid'],'REAL_JOB_WRAPPER':str(root/'runtime/dual_model_ml_neb_job.sh'),
    }
    command=['sbatch','--parsable','--job-name='+job_name,'--partition=normal','--nodes=1','--ntasks=1',
             '--cpus-per-task=4','--gres=gpu:1','--mem=40G','--time=06:00:00','--chdir='+str(root),
             '--output='+str(root/'logs/production-%j.out'),
             '--export=ALL,'+','.join(k+'='+v for k,v in environment.items()),str(execution/'allocated_gpu_guard.sh')]
    if args.mode=='check':
        print(json.dumps({'status':'READY','request_sha256':auth['request_sha256'],
                          'preflight':checked,'queue_checked':True,'sbatch_argv':command,'submission_performed':False}))
        return
    (root/'logs').mkdir(exist_ok=True)
    (root/'output').mkdir(exist_ok=True)
    # Keep original runtime bytes; Slurm reads the guard, which calls Bash explicitly.
    write_new(reservation,{'status':'SUBMISSION_ATTEMPT_PENDING_RECONCILIATION',
                          'at':datetime.now(timezone.utc).isoformat(),
                          'authorization_sha256':digest(execution/'authorization.json'),
                          'request_sha256':auth['request_sha256'],'sbatch_argv':command})
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    except BaseException as exc:
        write_new(root/'gpu_submission_uncertain.json',{'error_type':type(exc).__name__,'automatic_retry':False})
        raise
    write_new(root/'sbatch_raw.json',{'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    result.check_returncode()
    job_id=result.stdout.strip().split(';')[0]
    assert re.fullmatch('[1-9][0-9]*',job_id), 'unknown submission result; inspect reservation, never retry'
    record={'status':'SUBMITTED','job_id':job_id,'submitted_at':datetime.now(timezone.utc).isoformat(),
            'request_sha256':auth['request_sha256'],'authorization_sha256':digest(execution/'authorization.json'),
            'remote_root':str(root),'output_root':str(output),'scheduler':'Slurm','hostname':socket.gethostname()}
    write_new(receipt,record)
    print(json.dumps(record))


if __name__=='__main__':
    main()
