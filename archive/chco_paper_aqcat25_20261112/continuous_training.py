"""One fresh, authorized 100-epoch fit in the force-0.03 sequential campaign."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import shlex
import sys
from uuid import uuid4

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.neb_agent import mz73_continuation as continuation
from scripts.neb_agent.utils_structure import read_poscar
from scripts.ts_strategy_engine import paper_sequential as paper
from scripts.ts_strategy_engine.paper_stopping import effective_force_target

spec = importlib.util.spec_from_file_location('continuous_training_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)
require, bound, ref = primary.require, primary.bound, primary.ref
RESOURCES = {**primary.RESOURCES, 'memory': '15G'}


def context(state_reference, authorization_reference):
    state_path = bound(state_reference)
    approval, origin = continuation.authorization(authorization_reference)
    case = Path(approval['origin_state']['path']).resolve(strict=True).parent
    require(state_path.is_relative_to(case), 'training state escapes the authorized case')
    require(sha256_file(case / 'paper_state.v3.json') == state_reference['sha256'], 'active state changed')
    state = load_json_object(state_path)
    paper.validate_state(state)
    request = paper.training_request(state)
    require(effective_force_target(state) == 0.03
            and state['stopping_revision']['reviewed_authorization']['artifact_sha256'] == continuation.AUTHORIZATION_SHA
            and state['protocol_sha256'] == continuation.PROTOCOL_SHA, 'not the approved stopping revision')
    require(origin['completed_label_count'] <= state['completed_label_count'] < 250, 'training is outside the remaining sequential rounds')
    require(request['base_checkpoint']['sha256'] == primary.BASE, 'training must reset the original frozen base')
    index = state['reserved_dft_slots'] - 1
    leaf = f'training_r{index:03d}_force003'
    backend = primary.remote.load_mz73_static_backend(continuation.NAMES[index - 1])
    config = yaml.safe_load(Path(primary.remote.DEFAULT_CONFIG).read_text(encoding='utf-8'))
    require('force_only_fine_tuning' in config['backends']['aqcat_gpu']['allowed'], 'GPU training role unavailable')
    worker = Path(__file__).with_name('train_latest_label.py')
    require(sha256_file(worker) == primary.WORKER, 'reviewed training worker changed')
    original_manifest = case / 'training_r000_metadata_recovery01/manifest.json'
    require(sha256_file(original_manifest) == 'b5116823357d31323520416c9f90af53704ede76d84c48c566d1e7ee29e3bcf2', 'original successful training recipe binding changed')
    template = bound(load_json_object(original_manifest)['inputs']['template'])
    require(sha256_file(template) == primary.TEMPLATE, 'force-only recipe changed')
    structure_source = state['latest_label']['label']['structure']
    structure = bound({key: structure_source[key] for key in ('path', 'sha256')})
    require(structure.parent.parent == case / 'labels', 'training structure is outside accepted case labels')
    worker_spec = importlib.util.spec_from_file_location('continuous_label_worker', worker)
    runtime = importlib.util.module_from_spec(worker_spec)
    worker_spec.loader.exec_module(runtime)
    label, forces, movable = runtime.validated_label(request)
    atoms = read_poscar(structure)
    require(len(forces) == len(atoms.labels) == 49 and len(movable) == 31
            and atoms.labels == label['structure']['symbols'], '49-atom latest label mismatch')
    require(atoms.selective and [i for i, flags in enumerate(atoms.flags) if tuple(flags) == ('F', 'F', 'F')]
            == label['fixed_atom_indices_zero_based'], 'training Selective Dynamics mask mismatch')
    target = primary.REMOTE_CASE + '/' + leaf
    require(approval['resources']['training'] == {'gpus': 1, 'cpus_per_task': 4, 'memory': '15G', 'time_limit': '00:10:00'}, 'unapproved training resources')
    dependencies = {name: ref(path) for name, path in {
        'implementation': __file__, 'primary': primary.__file__, 'paper_owner': paper.__file__,
        'stopping_owner': Path(paper.__file__).with_name('paper_stopping.py'),
        'continuation_owner': continuation.__file__, 'remote_owner': primary.remote.__file__,
        'backend_config': primary.remote.DEFAULT_CONFIG,
    }.items()}
    return {'case': case, 'state': state, 'request': request, 'backend': backend,
            'leaf': leaf, 'target': target, 'dependencies': dependencies,
            'files': {'POSCAR': structure, 'force_only_config.yml': template, 'train_latest_label.py': worker}}


def prepare(state_path, state_sha, approval_path, approval_sha):
    state_reference = {'path': str(state_path.resolve(strict=True)), 'sha256': state_sha}
    approval_reference = {'path': str(approval_path.resolve(strict=True)), 'sha256': approval_sha}
    checked = context(state_reference, approval_reference)
    directory = checked['case'] / checked['leaf']
    require(not (checked['case'] / (checked['leaf'] + '_submission_attempt.json')).exists(), 'round already has a submission reservation')
    directory.mkdir(exist_ok=False)
    for name, source in checked['files'].items():
        (directory / name).write_bytes(source.read_bytes())
    write_json_exclusive(directory / 'request.json', checked['request'])
    request_sha = sha256_file(directory / 'request.json')
    (directory / 'job.sh').write_bytes(primary.render_job(checked['target'], request_sha, checked['backend']).encode('ascii'))
    manifest = {'document_kind': 'paper_continuous_training_manifest', 'state': state_reference,
                'authorization': approval_reference, 'dependencies': checked['dependencies'],
                'remote_dir': checked['target'], 'resources': RESOURCES,
                'training_request_sha256': sha256_json(checked['request']),
                'training_request_artifact_sha256': request_sha,
                'files': {p.name: sha256_file(p) for p in directory.iterdir() if p.is_file()},
                'automatic_retries': 0, 'checkpoint_promotion': False}
    write_json_exclusive(directory / 'manifest.json', manifest)
    return ref(directory / 'manifest.json')


def verify(path, digest):
    path = bound({'path': str(path.resolve(strict=True)), 'sha256': digest})
    manifest = load_json_object(path)
    checked = context(manifest['state'], manifest['authorization'])
    require(manifest['document_kind'] == 'paper_continuous_training_manifest'
            and manifest['resources'] == RESOURCES and manifest['automatic_retries'] == 0
            and manifest['checkpoint_promotion'] is False
            and manifest['remote_dir'] == checked['target'] and path.parent == checked['case'] / checked['leaf'], 'training manifest scope changed')
    require(manifest['dependencies'] == checked['dependencies'], 'training implementation or backend changed')
    require(set(p.name for p in path.parent.iterdir()) == set(manifest['files']) | {'manifest.json'}, 'unbound local training payload')
    require(all(sha256_file(path.parent / name) == value for name, value in manifest['files'].items()), 'training payload bytes changed')
    request_path = path.parent / 'request.json'
    require(manifest['training_request_artifact_sha256'] == sha256_file(request_path)
            and manifest['training_request_sha256'] == sha256_json(checked['request'])
            and sha256_json(load_json_object(request_path)) == manifest['training_request_sha256'], 'latest-label training request changed')
    for name, source in checked['files'].items():
        require(manifest['files'][name] == sha256_file(source), 'staged training source differs')
    require((path.parent / 'job.sh').read_bytes() == primary.render_job(checked['target'], sha256_file(request_path), checked['backend']).encode('ascii'), 'training launcher changed')
    return manifest, checked


def submit(path, digest):
    manifest, checked = verify(path, digest)
    case, leaf, backend, target = checked['case'], checked['leaf'], checked['backend'], checked['target']
    attempt, receipt = case / (leaf + '_submission_attempt.json'), case / (leaf + '_submission_record.json')
    require(not receipt.exists(), 'round already has a training submission receipt')
    reservation = uuid4().hex
    write_json_exclusive(attempt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'manifest': ref(path),
                                  'authorization': manifest['authorization'], 'automatic_retries': 0})
    q = shlex.quote
    lock = target + '_submission.reservation'
    try:
        checks = [*primary.remote.remote_path_checks(backend, primary.REMOTE_CASE),
                  *primary.remote.remote_path_checks(backend, lock), *primary.remote.remote_path_checks(backend, target),
                  'mkdir ' + q(lock), f"printf '%s\\n' {reservation} > {q(lock + '/reservation_id')}", 'test ! -e ' + q(target)]
        primary.run(primary.remote.ssh_argv(backend, 'set -eu; ' + ' && '.join(checks)))
        primary.run(primary.remote.scp_argv(backend, str(path.parent), primary.REMOTE_CASE))
        verify(path, digest)
        checks = [*primary.remote.remote_path_checks(backend, target),
                  f'test "$(cat {q(lock + "/reservation_id")})" = {reservation}', 'test -x ' + q(primary.PYTHON)]
        for name, value in {**manifest['files'], 'manifest.json': digest}.items():
            remote_file = target + '/' + name
            checks += primary.remote.remote_path_checks(backend, remote_file)
            checks.append(f'test "$(sha256sum {q(remote_file)} | cut -d\' \' -f1)" = {value}')
        base = checked['request']['base_checkpoint']
        checks += [*primary.remote.remote_path_checks(backend, base['path']),
                   f'test "$(sha256sum {q(base["path"])} | cut -d\' \' -f1)" = {primary.BASE}',
                   'test ! -e ' + q(target + '/output')]
        checks += primary.remote.remote_path_checks(backend, target + '/tmp') + primary.remote.remote_path_checks(backend, target + '/cache')
        checks += ['mkdir -p ' + q(target + '/tmp') + ' ' + q(target + '/cache'),
                   f'env TMPDIR={q(target + "/tmp")} XDG_CACHE_HOME={q(target + "/cache")} '
                   f'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={q(primary.PYTHONPATH)} {q(primary.PYTHON)} -B -c ' +
                   q('import ase.db, torch; from fairchem.core.common.utils import new_trainer_context; from fairchem.core.modules.exponential_moving_average import ExponentialMovingAverage'),
                   shlex.join(['sbatch', '--parsable', '--no-requeue', '--partition=gpu', '--nodelist=MZ73', '--nodes=1', '--ntasks=1',
                               '--cpus-per-task=4', '--gres=gpu:1', '--mem=15G', '--time=00:10:00', '--job-name=chco-' + leaf,
                               '--chdir=' + target, '--output=' + target + '/slurm-%j.out', '--error=' + target + '/slurm-%j.err', target + '/job.sh'])]
        result = primary.run(primary.remote.ssh_argv(backend, 'set -eu; ' + ' && '.join(checks)))
        payload = {'status': 'SUBMITTED', 'job_id': primary.remote.parse_sbatch_job_id(result.stdout),
                   'reservation_id': reservation, 'manifest_sha256': digest, 'remote_dir': target,
                   'scheduler': 'Slurm', 'training_completed': False, 'submit_stdout': result.stdout,
                   'submit_stderr': result.stderr, 'automatic_retries': 0}
        write_json_exclusive(receipt, payload)
        return payload
    except BaseException:
        if not receipt.exists():
            write_json_exclusive(receipt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'automatic_retries': 0})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    command = subparsers.add_parser('prepare')
    command.add_argument('--state', type=Path, required=True)
    command.add_argument('--state-sha256', required=True)
    command.add_argument('--authorization', type=Path, required=True)
    command.add_argument('--authorization-sha256', required=True)
    for name in ('verify', 'submit'):
        command = subparsers.add_parser(name)
        command.add_argument('--manifest', type=Path, required=True)
        command.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.state, args.state_sha256, args.authorization, args.authorization_sha256)
    elif args.command == 'verify':
        manifest, _ = verify(args.manifest, args.manifest_sha256)
        result = {'verified': True, 'remote_dir': manifest['remote_dir'], 'submitted': False}
    else:
        result = submit(args.manifest, args.manifest_sha256)
    print(result)


if __name__ == '__main__':
    main()
