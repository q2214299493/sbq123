"""One explicitly authorized BUCT2 copy of the already queued training round.

Keep the primary request bytes, label, base model and recipe unchanged. This
does not allocate another AL round, retry a failed training, or accept a result.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from uuid import uuid4

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('paper_training_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)
require = primary.require
ref = primary.ref
bound = primary.bound
ROOT = '/home/sbq/sbq'
NODE = 'pc-G7466-M6'
ALIAS = 'buct2-gpu'
DEPLOYED = ROOT + '/fe110_c2_supplement_buct2_20261106_v1'
PYTHON = DEPLOYED + '/deps/usr/bin/python3.10'
SITE = DEPLOYED + '/deps/home/sbq/sbq/ml_ts_acceleration/venv/lib/python3.10/site-packages'
AQCAT = DEPLOYED + '/deps/home/sbq/sbq/aqcat25'
PYTHONPATH = AQCAT + '/python_pkgs:' + AQCAT + '/vendor:' + SITE


def ssh(command):
    return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o',
            'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8', ALIAS, command]


def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=55, check=True)
    require(len(result.stdout.encode()) + len(result.stderr.encode()) <= 65536, 'oversized transport response')
    return result


def replica_backend(path):
    configured = yaml.safe_load(path.read_text(encoding='utf-8'))['backends']['buct2_gpu']
    require(configured['role'] == 'candidate_acceleration_only' and configured['ssh'] == {'alias': ALIAS}
            and configured['remote_write_boundary'] == ROOT, 'unreviewed BUCT2 execution backend')
    return {'remote_write_boundary': ROOT, 'canonical_write_boundary': ROOT}


def launcher(target, digest, backend):
    script = primary.render_job(target, digest, backend)
    require(script.count('test "$(hostname -s)" = MZ73') == 1, 'primary hostname guard changed')
    script = script.replace('test "$(hostname -s)" = MZ73', f'test "$(hostname -s)" = {NODE}')
    script = script.replace(primary.PYTHON, PYTHON)
    script = script.replace('export PYTHONPATH=' + shlex.quote(primary.PYTHONPATH),
        'export PYTHONNOUSERSITE=1\nexport PYTHONHOME=' + shlex.quote(DEPLOYED + '/deps/usr') +
        '\nexport LD_LIBRARY_PATH=' + shlex.quote(DEPLOYED + '/native_libs') +
        '\nexport PYTHONPATH=' + shlex.quote(PYTHONPATH))
    return script.encode('ascii')


def queued_primary(checked, receipt):
    record = load_json_object(bound(receipt))
    require(record['status'] == 'SUBMITTED' and record['remote_dir'] == checked['remote_dir'], 'primary job identity changed')
    result = primary.run(primary.remote.ssh_argv(checked['backend'], 'scontrol -o show job ' + record['job_id']))
    fields = parse_scontrol_job(result.stdout, record['job_id'])
    require(fields['remote_dir'] == checked['remote_dir']
            and fields['command'] == checked['remote_dir'] + '/job.sh', 'primary live job directory/command mismatch')
    reason = re.findall(r'(?:^|\s)Reason=(\S+)', result.stdout)
    require(fields['job_state'] == 'PENDING' and len(reason) == 1 and reason[0] in ('Resources', 'Priority'),
            'backup is permitted only while the original job is resource/priority queued')
    return result


def verify_authorization(path, case, manifest, receipt):
    authorization = load_json_object(path)
    require(authorization.get('document_kind') == 'user_same_round_replica_authorization'
            and authorization.get('decision') == 'approved_MZ73_BUCT2_first_valid_result'
            and authorization.get('allowed_hosts') == ['MZ73', NODE]
            and authorization.get('logical_training_rounds') == 1
            and authorization.get('maximum_physical_training_copies') == 2
            and authorization.get('additional_AL_rounds') == 0
            and authorization.get('automatic_failure_retry') is False,
            'missing explicit, bounded same-round two-server authorization')
    require(Path(authorization['case_root']).resolve() == case and authorization['primary_manifest'] == manifest
            and authorization['primary_receipt'] == receipt, 'replica authorization belongs to another case/job')
    bound(authorization['source'])
    return authorization


def prepare(args):
    manifest_ref = {'path': str(args.primary_manifest.resolve(strict=True)), 'sha256': args.primary_sha256}
    manifest, checked = primary.verify(bound(manifest_ref), args.primary_sha256)
    case = checked['case']
    receipt_ref = ref(case / 'training_submission_record.json')
    verify_authorization(args.authorization, case, manifest_ref, receipt_ref)
    queued_primary(checked, receipt_ref)
    backend = replica_backend(args.config)
    job_dir = case / 'training_r000_buct2'
    job_dir.mkdir(exist_ok=False)
    for name in manifest['files']:
        if name != 'job.sh':
            (job_dir / name).write_bytes((args.primary_manifest.parent / name).read_bytes())
    (job_dir / 'job.sh').write_bytes(launcher(checked['remote_dir'], manifest['files']['request.json'], backend))
    copied = {name: sha256_file(job_dir / name) for name in manifest['files']}
    result = {'document_kind': 'paper_same_round_BUCT2_training_replica', 'primary_manifest': manifest_ref,
              'primary_receipt': receipt_ref, 'authorization': ref(args.authorization), 'config': ref(args.config),
              'implementation': ref(__file__), 'remote_dir': checked['remote_dir'],
              'resources': {**primary.RESOURCES, 'node': NODE}, 'files': copied,
              'logical_training_request_sha256': manifest['training_request_sha256'], 'automatic_retry': False}
    path = job_dir / 'replica_manifest.json'
    write_json_exclusive(path, result)
    return ref(path)


def verify(path, digest):
    manifest = load_json_object(bound({'path': str(path.resolve(strict=True)), 'sha256': digest}))
    original, checked = primary.verify(bound(manifest['primary_manifest']), manifest['primary_manifest']['sha256'])
    require(manifest['document_kind'] == 'paper_same_round_BUCT2_training_replica'
            and manifest['implementation'] == ref(__file__) and manifest['automatic_retry'] is False,
            'unreviewed replica implementation or scope')
    verify_authorization(bound(manifest['authorization']), checked['case'], manifest['primary_manifest'], manifest['primary_receipt'])
    backend = replica_backend(bound(manifest['config']))
    require(manifest['resources'] == {**primary.RESOURCES, 'node': NODE}
            and manifest['remote_dir'] == checked['remote_dir']
            and manifest['logical_training_request_sha256'] == original['training_request_sha256'], 'replica resource or request drift')
    require(path.parent == checked['case'] / 'training_r000_buct2' and set(manifest['files']) == set(original['files']), 'replica local scope changed')
    for name, value in manifest['files'].items():
        require(sha256_file(path.parent / name) == value, 'replica staged bytes changed')
        if name != 'job.sh':
            require(value == original['files'][name], 'replica changed scientific input bytes')
    require((path.parent / 'job.sh').read_bytes() == launcher(checked['remote_dir'], original['files']['request.json'], backend), 'replica launcher drift')
    return manifest, checked


def remote_preflight(manifest, request, reservation):
    """Reserve once, verify exact payloads, and copy the existing base exclusively."""
    packet = {'target': manifest['remote_dir'], 'reservation': reservation, 'base': request['base_checkpoint'],
              'files': manifest['files'], 'source_base': DEPLOYED + '/deps' + request['base_checkpoint']['path'], 'node': NODE}
    return '''import hashlib,json,os,socket,shutil
from pathlib import Path
p=json.loads(__PACKET__)
root=Path('/home/sbq/sbq').resolve(strict=True)
def safe(s):
 path=Path(s)
 if not path.is_absolute() or not path.resolve().is_relative_to(root):raise ValueError('remote path escape')
 return path
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
if socket.gethostname().split('.')[0]!=p['node']:raise ValueError('wrong replica host')
target=safe(p['target'])
for name,value in p['files'].items():
 if digest(safe(str(target/name)))!=value:raise ValueError('staged file hash mismatch')
lock=safe(str(target.parent/'training_submission.reservation'))
lock.mkdir()
(lock/'reservation_id').write_text(p['reservation'])
base=safe(p['base']['path']);source=safe(p['source_base'])
if digest(source)!=p['base']['sha256']:raise ValueError('deployed base hash mismatch')
if not base.exists():
 base.parent.mkdir(parents=True,exist_ok=True)
 with source.open('rb') as src,base.open('xb') as out:shutil.copyfileobj(src,out)
 base.chmod(0o600)
if digest(base)!=p['base']['sha256']:raise ValueError('exact base path hash mismatch')
if (target/'output').exists():raise ValueError('replica already has output')
print(json.dumps({'hostname':socket.gethostname(),'base_sha256':digest(base),'files_verified':p['files'],'reservation':p['reservation']}))
'''.replace('__PACKET__', repr(json.dumps(packet)))


def submit(path, digest):
    manifest, checked = verify(path, digest)
    queued_primary(checked, manifest['primary_receipt'])
    case, target, reservation = checked['case'], manifest['remote_dir'], uuid4().hex
    attempt = case / 'training_replica_submission_attempt.json'
    receipt = case / 'training_replica_submission_record.json'
    require(not receipt.exists(), 'replica receipt already exists')
    write_json_exclusive(attempt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'manifest': ref(path), 'automatic_retry': False})
    try:
        parent = str(Path(target).parent).replace('\\', '/')
        checks = primary.remote.remote_path_checks(replica_backend(bound(manifest['config'])), target)
        run(ssh('set -eu; ' + ' && '.join([*checks, 'mkdir -p ' + shlex.quote(parent), 'mkdir ' + shlex.quote(target)])))
        argv = ['scp', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
                *[str(path.parent / name) for name in manifest['files']], ALIAS + ':' + target + '/']
        run(argv)
        proof = run(ssh(shlex.join(['python3', '-c', remote_preflight(manifest, checked['request'], reservation)])))
        write_json_exclusive(case / 'training_replica_remote_preflight.json', {'argv': ssh(shlex.join(['python3', '-c', remote_preflight(manifest, checked['request'], reservation)])),
            'returncode': proof.returncode, 'stdout': proof.stdout, 'stderr': proof.stderr})
        verify(path, digest)
        queued_primary(checked, manifest['primary_receipt'])
        argv = ['sbatch', '--parsable', '--no-requeue', '--partition=gpu', '--nodelist=' + NODE,
                '--nodes=1', '--ntasks=1', '--cpus-per-task=4', '--gres=gpu:1', '--mem=16G', '--time=00:10:00',
                '--job-name=chco-paper-train-r000-copy', '--chdir=' + target, '--output=' + target + '/slurm-%j.out',
                '--error=' + target + '/slurm-%j.err', target + '/job.sh']
        result = run(ssh(shlex.join(argv)))
        record = {'status': 'SUBMITTED', 'job_id': primary.remote.parse_sbatch_job_id(result.stdout),
                  'server_alias': ALIAS, 'observed_hostname': NODE, 'remote_dir': target, 'manifest': ref(path),
                  'reservation_id': reservation, 'scheduler': 'Slurm', 'training_completed': False,
                  'logical_training_rounds': 1, 'additional_AL_rounds': 0,
                  'submit_stdout': result.stdout, 'submit_stderr': result.stderr}
        write_json_exclusive(receipt, record)
        return record
    except BaseException:
        if not receipt.exists():
            write_json_exclusive(receipt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'automatic_retry': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare')
    for name in ('primary-manifest', 'authorization', 'config'):
        prepare_parser.add_argument('--' + name, type=Path, required=True)
    prepare_parser.add_argument('--primary-sha256', required=True)
    submit_parser = commands.add_parser('submit')
    submit_parser.add_argument('--manifest', type=Path, required=True)
    submit_parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args) if args.command == 'prepare' else submit(args.manifest.resolve(strict=True), args.manifest_sha256)))


if __name__ == '__main__':
    main()
