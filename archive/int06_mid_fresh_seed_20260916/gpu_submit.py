"""Prepare, stage, preflight and submit one reviewed nine-frame GPU request."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

from archive.int06_mid_fresh_seed_20260916.prepare import ROOT, BASE, DEST, PATH
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.ts_strategy_engine.path_evidence import validate_path_review

REMOTE = '/home/sbq/sbq/aqcat25_ts_pilot/handoffs/int06_mid_fresh_seed_20260916'
LOCAL = DEST/'submission_20260916'
PACKAGE = LOCAL/'payload'
EXECUTION = LOCAL/'execution'
SSH = ['ssh','-p','36039','-i','C:/Users/86177/.ssh/id_ed25519_fe_agent',
       '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15','sbq@10sx4jr711576.vicp.fun']
PYTHON = '/home/sbq/sbq/ml_ts_acceleration/venv/bin/python'
OLD = BASE/'h_migration_int06_to_mid_gpu_20260910/payload'


def save_text(path, value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(value)


def prepare():
    LOCAL.mkdir(exist_ok=False)
    PACKAGE.mkdir()
    EXECUTION.mkdir()
    review = load_json_object(PATH/'path_review.draft.json')
    review.update(status='accepted',reviewer='user via explicit submit; Codex work-side checks',
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        notes='User accepted the presented fresh nine-frame initial seed with 提交. Geometry only; no TS or energy acceptance.')
    write_json_exclusive(PATH/'path_review.json',review)
    assert validate_path_review(PATH/'path_review.json',PATH/'path_generation_report.json')[0]
    save_text(LOCAL/'user_authorization.md',
        '# GPU authorization 2026-09-16\n\nUser: 提交, following the presented INT06-to-MID nine-frame seed.\n'
        'One MatRIS ordinary ML-NEB and AQCat25 exact-path audit; 1 GPU, 4 CPUs, 40 GB, 6 hours, maximum 400 steps.\n'
        'No ML-CI, Sella, training, automatic retry, or VASP submission. Preserve the retired SCF branch.\n')
    request=load_json_object(DEST/'gpu_request/request.draft.json')
    request.pop('preparation_status')
    for row in request['images']:
        source=DEST/'gpu_request'/row['path']
        assert sha256_file(source)==row['sha256']
        target=PACKAGE/row['path']
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source,target)
    files={'reaction_contract.normalized.json':DEST/'contract.json',
           'review/path_review.json':PATH/'path_review.json',
           'review/path_generation_report.json':PATH/'path_generation_report.json',
           'review/exact_mic_geometry.json':PATH/'exact_mic_geometry.json',
           'review/dist.dat':PATH/'dist.dat','review/movie.xyz':PATH/'movie.xyz',
           'review/vtst_checks.json':PATH/'vtst_checks.json','review/path_review.png':DEST/'path_review.png'}
    for target,source in files.items():
        (PACKAGE/target).parent.mkdir(exist_ok=True)
        shutil.copyfile(source,PACKAGE/target)
    # Portable review paths reference the unchanged copied evidence.
    portable=load_json_object(PACKAGE/'review/path_review.json')
    portable['dist_file']='dist.dat'
    portable['nebmovie_file']='movie.xyz'
    from scripts.artifact_io import write_json
    write_json(PACKAGE/'review/path_review.json',portable)
    assert validate_path_review(PACKAGE/'review/path_review.json',PACKAGE/'review/path_generation_report.json')[0]
    request['source_seed_review']={'path':'review/path_review.json',
        'sha256':sha256_file(PACKAGE/'review/path_review.json'),'review_status':'accepted_for_initial_geometry_only'}
    request['source_evidence_files']={name:sha256_file(PACKAGE/name) for name in files}
    runtime=list(load_json_object(OLD/'request.json')['runtime_bindings'])
    (PACKAGE/'runtime').mkdir()
    for name in runtime:
        shutil.copyfile(ROOT/'scripts'/name,PACKAGE/'runtime'/name)
    request['runtime_bindings']={name:sha256_file(PACKAGE/'runtime'/name) for name in runtime}
    write_json_exclusive(PACKAGE/'request.json',request)
    preflight=(OLD/'preflight.py').read_text(encoding='utf-8')
    assert preflight.count('len(images) == 5')==1
    save_text(PACKAGE/'preflight.py',preflight.replace('len(images) == 5','len(images) == 9'))
    manifest={'schema_version':1,'remote_root':REMOTE,'request_sha256':sha256_file(PACKAGE/'request.json'),
        'files':{p.relative_to(PACKAGE).as_posix():sha256_file(p) for p in PACKAGE.rglob('*') if p.is_file()}}
    write_json_exclusive(PACKAGE/'payload_manifest.json',manifest)
    driver=(ROOT/'archive/int06_mid_gpu_20260910/submit_remote.py').read_text(encoding='utf-8')
    assert driver.count("len(request['images'])==5")==1
    driver=driver.replace("len(request['images'])==5","len(request['images'])==9")
    driver=driver.replace("job_name='int06-mid-mlneb'","job_name='int06-mid-fresh9'")
    driver=driver.replace("command=['sbatch','--parsable'","command=['sbatch','--parsable','--no-requeue'")
    save_text(EXECUTION/'submit_remote.py',driver)
    shutil.copyfile(Path(__file__).with_name('allocated_gpu_guard.sh'),EXECUTION/'allocated_gpu_guard.sh')
    auth={'schema_version':1,'document_kind':'user_gpu_execution_authorization','authorized':True,
        'authorized_at':datetime.now(timezone.utc).isoformat(),'user_instruction':'提交',
        'action':'initial_gpu_path_candidate','request_sha256':sha256_file(PACKAGE/'request.json'),
        'payload_manifest_sha256':sha256_file(PACKAGE/'payload_manifest.json'),
        'source':{'path':str(LOCAL/'user_authorization.md'),'sha256':sha256_file(LOCAL/'user_authorization.md')},
        'driver_sha256':sha256_file(EXECUTION/'submit_remote.py'),
        'guard_sha256':sha256_file(EXECUTION/'allocated_gpu_guard.sh'),
        'remote_root':REMOTE,'scheduler_resources':request['scheduler_resources'],
        'automatic_retry':False,'vasp_authorized':False,
        'scope':'One new nine-frame initial GPU path on its scheduler-assigned device, no VASP.'}
    write_json_exclusive(EXECUTION/'authorization.json',auth)
    run=subprocess.run([sys.executable,'-B',str(PACKAGE/'preflight.py')],capture_output=True,text=True,check=True)
    write_json_exclusive(LOCAL/'local_preflight.json',json.loads(run.stdout))
    for name in ('runtime/dual_model_ml_neb_job.sh','runtime/aqcat25_mz73_env.sh'):
        subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(PACKAGE/name)],check=True)
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(EXECUTION/'allocated_gpu_guard.sh')],check=True)
    print(json.dumps({'local_preflight':'PASS','request_sha256':auth['request_sha256'],'files':len(manifest['files'])}))


def invoke(code,name):
    if (LOCAL/(name+'.receipt.json')).exists():
        raise RuntimeError('Prior receipt exists; reconcile before repeating '+name)
    result=subprocess.run([*SSH,PYTHON+' -B -'],input=code.encode('utf-8'),capture_output=True,timeout=55)
    for suffix,data in (('stdout',result.stdout),('stderr',result.stderr)):
        with (LOCAL/(name+'.'+suffix)).open('xb') as handle:
            handle.write(data)
    write_json_exclusive(LOCAL/(name+'.receipt.json'),{'exit_code':result.returncode})
    if result.returncode:
        print(result.stderr.decode('utf-8',errors='replace')[-3500:])
    result.check_returncode()
    parsed=json.loads(result.stdout)
    write_json_exclusive(LOCAL/(name+'.result.json'),parsed)
    print(json.dumps(parsed)[:4000])


def stage():
    manifest=load_json_object(PACKAGE/'payload_manifest.json')
    files={name:(PACKAGE/name).read_bytes() for name in [*manifest['files'],'payload_manifest.json']}
    files.update({'execution/'+p.name:p.read_bytes() for p in EXECUTION.iterdir() if p.is_file()})
    encoded={name:base64.b64encode(value).decode('ascii') for name,value in files.items()}
    code=f'''import base64,json,os,subprocess
from pathlib import Path
root=Path({REMOTE!r})
assert root.resolve().is_relative_to(Path('/home/sbq/sbq'))
root.mkdir(exist_ok=False)
files={encoded!r}
for name,data in files.items():
 target=root/name
 assert target.resolve().is_relative_to(root)
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as f:f.write(base64.b64decode(data))
for name in ['runtime/dual_model_ml_neb_job.sh','runtime/aqcat25_mz73_env.sh','execution/allocated_gpu_guard.sh']:
 subprocess.run(['bash','-n',str(root/name)],check=True)
env=dict(os.environ,AQCAT_PILOT_ROOT=str(root/'runtime'),TMPDIR=str(root/'tmp'))
command='. '+str(root/'runtime/aqcat25_mz73_env.sh')+'; aqcat25_setup_mz73_environment '+str(root/'output/environment_preflight')
subprocess.run(['bash','-c',command],env=env,check=True,capture_output=True,text=True)
r=subprocess.run([{PYTHON!r},'-B',str(root/'preflight.py')],check=True,capture_output=True,text=True)
print(r.stdout,end='')
'''
    invoke(code,'remote_preflight')


def execute(mode):
    if mode=='submit':
        checked=load_json_object(LOCAL/'check.result.json')
        assert checked['status']=='READY' and not checked['submission_performed']
        write_json_exclusive(LOCAL/'local_submission_reservation.json',{
            'authorization_sha256':sha256_file(EXECUTION/'authorization.json'),'automatic_retry':False})
    invoke(f"import runpy,sys\nsys.argv=['submit_remote.py','--mode',{mode!r}]\nrunpy.run_path({(REMOTE+'/execution/submit_remote.py')!r},run_name='__main__')\n",mode)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','stage','check','submit'])
    mode=parser.parse_args().mode
    if mode=='prepare':
        prepare()
    elif mode=='stage':
        stage()
    else:
        execute(mode)
