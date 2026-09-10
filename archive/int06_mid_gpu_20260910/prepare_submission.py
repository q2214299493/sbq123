"""Bind the user's submit instruction to the unchanged GPU package."""
from datetime import datetime, timezone
import shutil
import subprocess

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from archive.int06_mid_gpu_20260910.prepare import PARENT, REMOTE, SOURCE
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.execution_gate import validate_decision


def main():
    execution=BASE/'execution_20260910'
    execution.mkdir(exist_ok=False)
    shutil.copyfile(ROOT/'archive/int06_mid_gpu_20260910/submit_remote.py',execution/'submit_remote.py')
    guard=(PARENT/'allocated_gpu_guard.sh').read_text(encoding='utf-8')
    assert 'exec "$REAL_JOB_WRAPPER"' in guard
    guard=guard.replace('exec "$REAL_JOB_WRAPPER"','exec bash "$REAL_JOB_WRAPPER"')
    with (execution/'allocated_gpu_guard.sh').open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(guard)
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(execution/'allocated_gpu_guard.sh')],check=True)
    gate=build_decision(SOURCE/'plan/path_candidate/execution_gate_request.json',execution/'vasp_gate_scope.json')
    validate_decision(gate)
    assert not gate['SUBMISSION_ALLOWED']
    request=load_json_object(BASE/'payload/request.json')
    auth={
        'schema_version':1,'document_kind':'user_gpu_execution_authorization',
        'authorized':True,'authorized_at':datetime.now(timezone.utc).isoformat(),
        'user_instruction':'提交','action':'initial_gpu_path_candidate',
        'request_sha256':sha256_file(BASE/'payload/request.json'),
        'payload_manifest_sha256':sha256_file(BASE/'payload/payload_manifest.json'),
        'review_sha256':sha256_file(ROOT/'docs/reviews/int06_mid_gpu_prepared_20260910.md'),
        'driver_sha256':sha256_file(execution/'submit_remote.py'),
        'guard_sha256':sha256_file(execution/'allocated_gpu_guard.sh'),
        'remote_root':REMOTE,'scheduler_resources':request['scheduler_resources'],
        'automatic_retry':False,'vasp_authorized':False,
        'scope':'One initial MatRIS ordinary ML-NEB plus fixed-path AQCat25 audit, unchanged reviewed seed and request.',
    }
    assert auth['request_sha256']=='d0a3a7d657b362deb077ed6b181f76129ba63d4c64948700cbc1ca9a408eb85e'
    write_json_exclusive(execution/'authorization.json',auth)
    write_json_exclusive(execution/'gate_scope_review.json',{
        'backend_authority':'configs/execution_backends.yaml: dual_model_ts_path_acceleration',
        'initial_gpu_candidate_execution':'explicit user instruction bound to request and resources',
        'vasp_execution_gate_sha256':sha256_file(execution/'vasp_gate_scope.json'),
        'vasp_allowed_actions':gate['ALLOWED_ACTIONS'],
        'scope_note':'The VASP/VTST execution gate has no GPU-submission action. This is a new predicted GPU candidate run, not a VASP submission, restart, or rebuild of a useful running calculation.',
    })
    print('User submission authority bound; GPU-only; no VASP action authorized')


if __name__=='__main__':
    main()
