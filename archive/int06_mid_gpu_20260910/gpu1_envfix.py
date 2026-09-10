"""Continue the user's GPU1 launch after a pre-model environment failure."""
import argparse
import base64
import shutil
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910 import gpu1_attempt as attempt
from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

PRIOR = attempt.ATTEMPT
attempt.ATTEMPT = BASE / 'attempt_gpu1_envfix_20260910'
attempt.REMOTE_ATTEMPT += '_envfix'


def prepare(tempdir_fix=False):
    local = attempt.ATTEMPT
    local.mkdir(exist_ok=False)
    execution = local / 'execution'
    execution.mkdir()
    updates = local / 'payload_updates'
    (updates / 'runtime').mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/aqcat25_mz73_env.sh', updates / 'runtime/aqcat25_mz73_env.sh')
    request = load_json_object(BASE / 'payload/request.json')
    request['runtime_bindings']['aqcat25_mz73_env.sh'] = sha256_file(updates / 'runtime/aqcat25_mz73_env.sh')
    write_json_exclusive(updates / 'request.json', request)
    manifest = load_json_object(BASE / 'payload/payload_manifest.json')
    for name in ['runtime/aqcat25_mz73_env.sh', 'request.json']:
        manifest['files'][name] = sha256_file(updates / name)
    manifest['request_sha256'] = sha256_file(updates / 'request.json')
    manifest['remote_root'] = attempt.REMOTE_ATTEMPT
    write_json_exclusive(updates / 'payload_manifest.json', manifest)
    for name in ['submit_remote.py', 'allocated_gpu_guard.sh']:
        shutil.copyfile(PRIOR / 'execution' / name, execution / name)
    if tempdir_fix:
        guard = execution / 'allocated_gpu_guard.sh'
        text = guard.read_text(encoding='utf-8')
        text = text.replace('exec bash "$REAL_JOB_WRAPPER"',
                            'export TMPDIR="$REQUEST_ROOT/tmp"\nexec bash "$REAL_JOB_WRAPPER"')
        guard.write_text(text, encoding='utf-8', newline='\n')
    auth = load_json_object(PRIOR / 'execution/authorization.json')
    auth.update(authorized_at=datetime.now(timezone.utc).isoformat(), remote_root=attempt.REMOTE_ATTEMPT,
                request_sha256=sha256_file(updates / 'request.json'),
                payload_manifest_sha256=sha256_file(updates / 'payload_manifest.json'),
                guard_sha256=sha256_file(execution / 'allocated_gpu_guard.sh'),
                prior_failed_job='1514' if tempdir_fix else '1513',
                scope='Complete the repeated explicit GPU1 submission request after pre-model wrapper failures. Python symlink handling corrected; use task-local TMPDIR when selected. Geometry, models, optimizer and resources unchanged. Preserve failed attempts; no automatic scheduler requeue or model retry.')
    write_json_exclusive(execution / 'authorization.json', auth)
    old = load_json_object(BASE / 'payload/request.json')
    old['runtime_bindings']['aqcat25_mz73_env.sh'] = request['runtime_bindings']['aqcat25_mz73_env.sh']
    assert old == request
    write_json_exclusive(local / 'runtime_fix_review.json', {
        'scientific_request_unchanged': True, 'changed_runtime_file': 'aqcat25_mz73_env.sh',
        'change': 'Validate venv interpreter parent within write boundary; permit executable symlink to system Python.',
        'old_request_sha256': sha256_file(BASE / 'payload/request.json'),
        'new_request_sha256': sha256_file(updates / 'request.json'),
        'prior_failed_job': auth['prior_failed_job'],
        'task_local_tmpdir': tempdir_fix,
        'prior_failure': 'pre-model Python symlink or inherited /tmp containment check',
        'actual_user_instruction': '提交gpu1', 'model_execution_in_prior_job': False})
    print('Prepared environment-only correction; scientific request equality verified')


def stage():
    local = attempt.ATTEMPT
    files = {p.relative_to(local / 'payload_updates').as_posix(): base64.b64encode(p.read_bytes()).decode()
             for p in (local / 'payload_updates').rglob('*') if p.is_file()}
    files.update({'execution/' + p.name: base64.b64encode(p.read_bytes()).decode()
                  for p in (local / 'execution').iterdir() if p.is_file()})
    code = f'''import base64,json,shutil,subprocess,os
from pathlib import Path
source=Path({attempt.REMOTE!r});root=Path({attempt.REMOTE_ATTEMPT!r})
assert root.is_relative_to(Path('/home/sbq/sbq')) and not root.exists()
files={files!r}
root.mkdir()
for name in json.loads((source/'payload_manifest.json').read_text())['files']:
 if name in files:continue
 target=root/name
 assert target.resolve().is_relative_to(root)
 target.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(source/name,target)
for name,data in files.items():
 target=root/name
 assert target.resolve().is_relative_to(root)
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as f:f.write(base64.b64decode(data))
environment=dict(os.environ,AQCAT_PILOT_ROOT=str(root/'runtime'))
command='. '+str(root/'runtime/aqcat25_mz73_env.sh')+'; aqcat25_setup_mz73_environment '+str(root/'output/environment_preflight')
r=subprocess.run(['bash','-c',command],env=environment,capture_output=True,text=True)
print(json.dumps({{'environment_preflight_exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'model_execution':False}}))
r.check_returncode()
'''
    attempt.invoke(code, 'stage')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'stage', 'check', 'submit'])
    parser.add_argument('--tempdir-fix', action='store_true')
    args = parser.parse_args()
    mode = args.mode
    if args.tempdir_fix:
        attempt.ATTEMPT = BASE / 'attempt_gpu1_ready_20260910'
        attempt.REMOTE_ATTEMPT += '_tmpfix'
    if mode == 'prepare':
        prepare(args.tempdir_fix)
    elif mode == 'stage':
        stage()
    else:
        attempt.run(mode)
