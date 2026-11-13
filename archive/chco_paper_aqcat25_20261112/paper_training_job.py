"""Prepare or explicitly submit the case's sole bounded paper-training job.

No controller, label acceptance, automatic retry, or checkpoint promotion.
Prepare needs a real owner-accepted label; submit retains UNKNOWN reservations.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import artifact_io
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.neb_agent import mz73_static as remote, mz73_timebudget as budget_owner
from scripts.ts_strategy_engine import paper_sequential as paper

BASE = 'cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0'
TEMPLATE = '979062fea494a8ea3facce2d4af83e0677d370d0a15e57b2f69f0695b91c9ed4'
WORKER = '143efce9e8cda362e487414a6e61873675c0cb01662ef3d13ea8305d8420aa71'
PYTHON = '/home/sbq/sbq/ml_ts_acceleration/venv/bin/python'
PYTHONPATH = '/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor'
LEAF = 'training_r000'
REMOTE_CASE = '/home/sbq/sbq/chco_paper_aqcat25_ft512_20261112_v1'
RESOURCES = {'node': 'MZ73', 'partition': 'gpu', 'gpus': 1, 'tasks': 1, 'cpus': 4,
             'memory': '16G', 'time_limit': '00:10:00', 'requeue': False}
STAGED = {'structure': 'POSCAR', 'template': 'force_only_config.yml', 'worker': 'train_latest_label.py'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ref(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256_file(path)}


def bound(descriptor):
    require(isinstance(descriptor, dict) and set(descriptor) == {'path', 'sha256'}, 'invalid raw source descriptor')
    path = Path(descriptor['path']).resolve(strict=True)
    require(path.is_file() and sha256_file(path) == descriptor['sha256'], 'bound source bytes changed')
    return path


def context(inputs):
    """Read-only owner checks; no checkpoint load, GPU construction, or writes."""
    require(set(inputs) == {'state', 'budget', 'structure', 'template', 'worker', 'config', 'paper_request', 'label_poscar'}, 'unexpected training source keys')
    paths = {key: bound(value) for key, value in inputs.items()}
    state = load_json_object(paths['state'])
    request = paper.training_request(state)
    require(not any('training_result' in row for row in state['evaluations']), 'case training budget was already consumed')
    require(request['base_checkpoint']['sha256'] == BASE and inputs['template']['sha256'] == TEMPLATE
            and inputs['worker']['sha256'] == WORKER, 'unreviewed base, recipe template or worker')
    spec = importlib.util.spec_from_file_location('paper_training_bound_worker', paths['worker'])
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    label, forces, movable = worker.validated_label(request)
    require(len(forces) == 49 and len(request['training_samples']) == 1
            and label['structure']['sha256'] == inputs['structure']['sha256'] == inputs['label_poscar']['sha256'], 'latest label/structure mismatch')
    from ase.io import read
    from ase.constraints import FixAtoms

    atoms = read(paths['structure'], format='vasp')
    require(len(atoms) == 49 and all(isinstance(item, FixAtoms) for item in atoms.constraints), 'invalid training POSCAR or SD')
    fixed = sorted({int(i) for item in atoms.constraints for i in item.get_indices()})
    require(fixed == sorted(set(range(49)) - set(movable)), 'training POSCAR SD differs from the accepted label')
    label_dir = paths['paper_request'].parent
    case = paths['state'].parent
    require(label_dir.parent == case / 'labels', 'label workdir is outside this state case')
    require(paths['label_poscar'] == label_dir / 'POSCAR', 'label POSCAR source belongs to another directory')
    backend = remote.load_mz73_static_backend(label_dir.name, config_path=paths['config'])
    require(paths['config'] == Path(remote.DEFAULT_CONFIG).resolve() and backend['remote_root'] == REMOTE_CASE + '/labels', 'training backend cannot move the sole case reservation')
    dft_request = load_json_object(paths['paper_request'])
    for key in ('protocol_sha256', 'evaluation_index', 'candidate_structure_sha256', 'search_checkpoint_sha256', 'contract_sha256', 'compatibility_sha256'):
        require(dft_request[key] == state['evaluations'][-1]['request'][key], 'label paper request and state differ')
    require(dft_request['execution_budget_authorization'] == inputs['budget'], 'another typed budget was supplied')
    budget = budget_owner.validate_budget_authorization(label_dir, dft_request, backend)
    approval = load_json_object(paths['budget'])
    require(approval.get('training_time_limit') == RESOURCES['time_limit'] and budget['limits']['max_training_jobs'] == 1
            and budget['limits']['training_epochs'] == 100 and budget['protocol_sha256'] == request['protocol_sha256'], 'not the approved 100-epoch/10-minute training budget')
    bound(budget['source'])
    remote.require_mz73_path(backend, request['base_checkpoint']['path'])
    remote_root = str(PurePosixPath(backend['remote_root']).parent)
    dependencies = {'reply': budget['source'], **{name: ref(path) for name, path in {
        'wrapper': Path(__file__), 'artifact_owner': artifact_io.__file__, 'paper_owner': paper.__file__,
        'budget_owner': budget_owner.__file__, 'remote_owner': remote.__file__,
    }.items()}}
    return {'case': case, 'request': request, 'backend': backend, 'remote_dir': remote_root + '/' + LEAF,
            'remote_reservation': remote_root + '/training_submission.reservation', 'dependencies': dependencies}


def render_job(remote_dir, request_sha256, backend):
    q = shlex.quote
    path_checks = '\n'.join(check for suffix in ('', '/tmp', '/cache', '/cache/xdg', '/cache/torch',
                                                 '/cache/huggingface', '/cache/cuda', '/output')
                            for check in remote.remote_path_checks(backend, remote_dir + suffix))
    return f'''#!/bin/bash
set -euo pipefail
record_exit() {{
  code=$?
  trap - EXIT
  set -C
  printf '{{"document_kind":"paper_training_producer_exit","job_id":"%s","exit_code":%d,"request_sha256":"{request_sha256}","evidence_class":"process_only_not_scheduler_or_training_completion"}}\\n' "${{SLURM_JOB_ID:-unknown}}" "$code" > {q(remote_dir + '/producer_exit_record.json')}
  exit "$code"
}}
trap record_exit EXIT
trap 'exit 143' TERM
test "$(hostname -s)" = MZ73
test "${{SLURM_NTASKS:-0}}" = 1
test -n "${{SLURM_JOB_ID:-}}"
case "${{CUDA_VISIBLE_DEVICES:-}}" in ''|*,*) exit 2 ;; esac
test "$(pwd -P)" = "$(realpath -e -- {q(remote_dir)})"
{path_checks}
test "$(sha256sum {q(remote_dir + '/train_latest_label.py')} | cut -d' ' -f1)" = {WORKER}
export PYTHONDONTWRITEBYTECODE=1 CUDA_CACHE_DISABLE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
export PYTHONPATH={q(PYTHONPATH)}
export TMPDIR={q(remote_dir + '/tmp')} XDG_CACHE_HOME={q(remote_dir + '/cache/xdg')} TORCH_HOME={q(remote_dir + '/cache/torch')}
export HF_HOME={q(remote_dir + '/cache/huggingface')} CUDA_CACHE_PATH={q(remote_dir + '/cache/cuda')}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WANDB_MODE=disabled WITH_PYG_LIB=0 TORCH_SPARSE_USE_PYG_LIB=0 TORCH_SCATTER_USE_PYG_LIB=0
mkdir -p -- "$TMPDIR" "$XDG_CACHE_HOME" "$TORCH_HOME" "$HF_HOME" "$CUDA_CACHE_PATH"
test ! -e {q(remote_dir + '/output')}
{q(PYTHON)} -B {q(remote_dir + '/train_latest_label.py')} --request {q(remote_dir + '/request.json')} --request-sha256 {request_sha256} --structure {q(remote_dir + '/POSCAR')} --template {q(remote_dir + '/force_only_config.yml')} --template-sha256 {TEMPLATE} --output-root {q(remote_dir + '/output')} --execute-authorized
'''


def prepare(args):
    state_ref = {'path': str(args.state.resolve(strict=True)), 'sha256': args.state_sha256}
    paper.training_request(load_json_object(bound(state_ref)))  # No label: refuse before creating anything.
    inputs = {'state': state_ref, 'budget': {'path': str(args.budget.resolve(strict=True)), 'sha256': args.budget_sha256},
              **{key: ref(path) for key, path in {'structure': args.structure, 'template': args.template, 'worker': args.worker,
                  'config': args.config_path, 'paper_request': args.label_workdir / remote.PAPER_REQUEST,
                  'label_poscar': args.label_workdir / 'POSCAR'}.items()}}
    checked = context(inputs)
    case, job_dir = checked['case'], args.job_dir.absolute()
    require(job_dir == case / LEAF and job_dir.resolve() == job_dir, 'training job directory must be the fresh case/training_r000')
    require(not any((case / name).exists() or (case / name).is_symlink() for name in
                    ('training_submission_attempt.json', 'training_submission_record.json')), 'case already has a training submission reservation')
    require(args.remote_dir in (None, checked['remote_dir']), 'training remote directory is fixed by the reviewed case backend')
    job_dir.mkdir(exist_ok=False)
    for key, name in STAGED.items():
        (job_dir / name).write_bytes(bound(inputs[key]).read_bytes())
    write_json_exclusive(job_dir / 'request.json', checked['request'])
    request_sha = sha256_file(job_dir / 'request.json')
    (job_dir / 'job.sh').write_bytes(render_job(checked['remote_dir'], request_sha, checked['backend']).encode('ascii'))
    manifest = {'document_kind': 'paper_single_training_job_manifest', 'inputs': inputs, 'dependencies': checked['dependencies'],
                'remote_dir': checked['remote_dir'], 'resources': RESOURCES, 'training_request_sha256': sha256_json(checked['request']),
                'training_request_artifact_sha256': request_sha,
                'files': {name: sha256_file(job_dir / name) for name in [*STAGED.values(), 'request.json', 'job.sh']},
                'automatic_retry': False, 'checkpoint_promotion': False}
    write_json_exclusive(job_dir / 'manifest.json', manifest)
    return ref(job_dir / 'manifest.json')


def verify(path, digest):
    manifest = load_json_object(bound({'path': str(path), 'sha256': digest}))
    require(manifest.get('document_kind') == 'paper_single_training_job_manifest' and manifest.get('resources') == RESOURCES
            and manifest.get('automatic_retry') is False and manifest.get('checkpoint_promotion') is False, 'unreviewed training manifest scope')
    checked = context(manifest['inputs'])
    job_dir = Path(path).resolve(strict=True).parent
    require(job_dir == checked['case'] / LEAF and manifest['remote_dir'] == checked['remote_dir'], 'local/remote training job scope changed')
    require(manifest['dependencies'] == checked['dependencies'] and all(bound(value) for value in manifest['dependencies'].values()), 'training implementation/reply changed')
    expected_names = {*STAGED.values(), 'request.json', 'job.sh'}
    require(set(manifest['files']) == expected_names and {item.name for item in job_dir.iterdir()} == expected_names | {'manifest.json'}, 'unbound files in the training staging directory')
    for name, digest_value in manifest['files'].items():
        require(not (job_dir / name).is_symlink() and sha256_file(job_dir / name) == digest_value, 'staged training bytes changed')
    for key, name in STAGED.items():
        require(manifest['files'][name] == manifest['inputs'][key]['sha256'], 'staged file differs from original reviewed source')
    request = load_json_object(job_dir / 'request.json')
    require(sha256_json(request) == sha256_json(checked['request']) == manifest['training_request_sha256']
            and manifest['files']['request.json'] == manifest['training_request_artifact_sha256'], 'training request identity changed')
    require((job_dir / 'job.sh').read_bytes() == render_job(checked['remote_dir'], manifest['files']['request.json'], checked['backend']).encode('ascii'), 'training launcher changed')
    return manifest, checked


def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=30)
    require(len(result.stdout.encode()) <= 65536 and len(result.stderr.encode()) <= 65536, 'oversized transport response')
    return result


def submit(path, digest):
    path = Path(path).resolve(strict=True)
    manifest, checked = verify(path, digest)
    case, backend, target, lock = checked['case'], checked['backend'], checked['remote_dir'], checked['remote_reservation']
    attempt, receipt = case / 'training_submission_attempt.json', case / 'training_submission_record.json'
    require(not receipt.exists() and not receipt.is_symlink(), 'case already has a training submission receipt')
    reservation = uuid4().hex
    write_json_exclusive(attempt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'manifest': {'path': str(path), 'sha256': digest},
                                 'remote_dir': target, 'budget': manifest['inputs']['budget'], 'automatic_retry': False})
    try:
        verify(path, digest)
        parent = str(PurePosixPath(target).parent)
        checks = [*remote.remote_path_checks(backend, parent), f'test -d {shlex.quote(parent)}',
                  *remote.remote_path_checks(backend, lock), *remote.remote_path_checks(backend, target),
                  f'mkdir {shlex.quote(lock)}', f"printf '%s\\n' {reservation} > {shlex.quote(lock + '/reservation_id')}",
                  f'test ! -e {shlex.quote(target)}']
        run(remote.ssh_argv(backend, 'set -eu; ' + ' && '.join(checks)))
        run(remote.scp_argv(backend, str(path.parent), parent))
        manifest, checked = verify(path, digest)  # Recheck state, accepted label, budget/reply and every original byte.
        checks = [*remote.remote_path_checks(backend, target), *remote.remote_path_checks(backend, lock + '/reservation_id'),
                  f'test "$(cat {shlex.quote(lock + "/reservation_id")})" = {reservation}', f'test -x {PYTHON}']
        for name, value in {**manifest['files'], 'manifest.json': digest}.items():
            file_path = target + '/' + name
            checks += remote.remote_path_checks(backend, file_path)
            checks.append(f'test "$(sha256sum {shlex.quote(file_path)} | cut -d\' \' -f1)" = {value}')
        base = checked['request']['base_checkpoint']
        checks += [*remote.remote_path_checks(backend, base['path']),
                   f'test "$(sha256sum {shlex.quote(base["path"])} | cut -d\' \' -f1)" = {BASE}',
                   f'test ! -e {shlex.quote(target + "/output")}']
        checks += remote.remote_path_checks(backend, target + '/tmp') + remote.remote_path_checks(backend, target + '/cache')
        checks += [
                   f'mkdir -p {shlex.quote(target + "/tmp")} {shlex.quote(target + "/cache")}',
                   f'env TMPDIR={shlex.quote(target + "/tmp")} XDG_CACHE_HOME={shlex.quote(target + "/cache")} '
                   f'TORCH_HOME={shlex.quote(target + "/cache/torch")} HF_HOME={shlex.quote(target + "/cache/huggingface")} '
                   f'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(PYTHONPATH)} {PYTHON} -B -c ' +
                   shlex.quote('from fairchem.core.common.utils import new_trainer_context; from fairchem.core.modules.exponential_moving_average import ExponentialMovingAverage; import ase.db, torch'),
                   shlex.join(['sbatch', '--parsable', '--no-requeue', '--partition=gpu', '--nodelist=MZ73', '--nodes=1', '--ntasks=1',
                               '--cpus-per-task=4', '--gres=gpu:1', '--mem=16G', '--time=00:10:00', '--job-name=chco-paper-train-r000',
                               '--chdir=' + target, '--output=' + target + '/slurm-%j.out', '--error=' + target + '/slurm-%j.err', target + '/job.sh'])]
        result = run(remote.ssh_argv(backend, 'set -eu; ' + ' && '.join(checks)))
        payload = {'status': 'SUBMITTED', 'job_id': remote.parse_sbatch_job_id(result.stdout), 'reservation_id': reservation,
                   'manifest_sha256': digest, 'remote_dir': target, 'scheduler': 'Slurm', 'training_completed': False,
                   'submit_stdout': result.stdout, 'submit_stderr': result.stderr}
        write_json_exclusive(receipt, payload)
        return payload
    except BaseException:
        try:
            write_json_exclusive(receipt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'automatic_retry': False})
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare')
    for name in ('state', 'label-workdir', 'budget', 'structure', 'job-dir'):
        prepare_parser.add_argument('--' + name, type=Path, required=True)
    for name in ('state-sha256', 'budget-sha256'):
        prepare_parser.add_argument('--' + name, required=True)
    prepare_parser.add_argument('--remote-dir')
    prepare_parser.add_argument('--template', type=Path, default=Path(__file__).with_name('runtime_sources') / 'force_only_config.yml')
    prepare_parser.add_argument('--worker', type=Path, default=Path(__file__).with_name('train_latest_label.py'))
    prepare_parser.add_argument('--config-path', type=Path, default=remote.DEFAULT_CONFIG)
    submit_parser = commands.add_parser('submit')
    submit_parser.add_argument('--manifest', type=Path, required=True)
    submit_parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    result = prepare(args) if args.command == 'prepare' else submit(args.manifest, args.manifest_sha256)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
