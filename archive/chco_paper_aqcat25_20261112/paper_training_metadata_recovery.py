"""Prepare one metadata repair; execute only with a new exact user approval.

Preserve the failed job, original request, label, base and recipe. No implicit
retry, additional AL round, new DFT budget or model/TS acceptance is granted.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shlex
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('metadata_recovery_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)
require, bound, ref = primary.require, primary.bound, primary.ref
LEAF = 'training_r000_metadata_recovery01'
RESOURCES = {**primary.RESOURCES, 'memory': '15G'}


def sources(references):
    paths = {key: bound(value) for key, value in references.items()}
    old = load_json_object(paths['original_manifest'])
    for value in [*old['inputs'].values(), *old['dependencies'].values()]:
        bound(value)
    case = Path(old['inputs']['state']['path']).parent
    original = load_json_object(case / 'training_submission_record.json')
    require(original['status'] == 'SUBMITTED' and original['manifest_sha256'] == references['original_manifest']['sha256'], 'original job manifest/receipt mismatch')
    packet = load_json_object(paths['failure_packet'])
    native = packet['native_scontrol']
    require(native['returncode'] == 0 and packet['hostname'] == 'MZ73', 'missing actual native failure record')
    parsed = parse_scontrol_job(native['stdout'], original['job_id'])
    require(parsed['job_state'] == 'FAILED' and parsed['exit_code'] == '1:0'
            and parsed['remote_dir'] == original['remote_dir'] == packet['remote_dir']
            and parsed['command'] == original['remote_dir'] + '/job.sh', 'failure belongs to another job or stage')
    raw_failure = base64.b64decode(packet['files']['output/training_failure.json']['raw_base64'], validate=True)
    import hashlib

    require(hashlib.sha256(raw_failure).hexdigest() == packet['files']['output/training_failure.json']['sha256'], 'failure artifact changed')
    failure = json.loads(raw_failure)
    require(failure['type'] == 'UnsupportedDatasetError'
            and 'metadata attributed with number of atoms' in failure['message']
            and failure['training_request_artifact_sha256'] == old['training_request_artifact_sha256'], 'not the reviewed sampler initialization failure')
    require(paths['failure_receipt'] == paths['failure_packet'].parent / 'capture_receipt.json', 'capture receipt path mismatch')
    capture_receipt = load_json_object(paths['failure_receipt'])
    require(capture_receipt['stdout_sha256'] == sha256_file(paths['failure_packet']), 'native capture source changed')
    preflight = load_json_object(paths['preflight'])
    require(preflight['status'] == 'passed' and preflight['training_performed'] is False
            and preflight['GPU_model_constructed'] is False and preflight['trainer_constructed'] is False
            and preflight['worker_sha256'] == primary.WORKER
            and preflight['raw_request_sha256'] == old['training_request_artifact_sha256']
            and preflight['dataset_length'] == preflight['metadata']['sample_count'] == 1
            and preflight['metadata']['natoms'] == [49] and preflight['movable_atom_count'] == 31
            and preflight['sampler_batches'] == [[0]] and preflight['configured_targets_present'] == ['energy', 'forces']
            and preflight['batch_tensor_shapes']['forces'] == [49, 3]
            and preflight['preflight_source_sha256'] == sha256_file(Path(__file__).with_name('preflight_single_label_dataset.py')),
            'actual installed dataset/sampler/batch preflight did not pass for this worker')
    inputs = {**old['inputs'], 'worker': ref(Path(__file__).with_name('train_latest_label.py')),
              'config': ref(primary.remote.DEFAULT_CONFIG)}
    require(inputs['config']['sha256'] == old['inputs']['config']['sha256'], 'recovery cannot change the DFT/backend configuration')
    checked = primary.context(inputs)
    require(case == checked['case'] and sha256_json(checked['request']) == old['training_request_sha256'], 'recovery changes the logical training request')
    for name, digest in old['files'].items():
        require(sha256_file(paths['original_manifest'].parent / name) == digest, 'original staged inputs changed')
    return old, checked, inputs


def prepare(args):
    references = {key: ref(value) for key, value in {'original_manifest': args.original_manifest,
                 'failure_packet': args.failure_packet, 'preflight': args.preflight,
                 'failure_receipt': args.failure_packet.parent / 'capture_receipt.json'}.items()}
    old, checked, inputs = sources(references)
    job_dir = checked['case'] / LEAF
    job_dir.mkdir(exist_ok=False)
    for key, name in primary.STAGED.items():
        (job_dir / name).write_bytes(bound(inputs[key]).read_bytes())
    (job_dir / 'request.json').write_bytes((args.original_manifest.parent / 'request.json').read_bytes())
    require(sha256_file(job_dir / 'request.json') == old['training_request_artifact_sha256'], 'original raw request changed')
    target = str(PurePosixPath(checked['remote_dir']).parent / LEAF)
    script = primary.render_job(target, old['training_request_artifact_sha256'], checked['backend'])
    (job_dir / 'job.sh').write_bytes(script.encode('ascii'))
    manifest = {'document_kind': 'paper_single_metadata_recovery_manifest',
                'status': 'prepared_requires_new_exact_execution_approval', 'case_root': str(checked['case']),
                'sources': references, 'inputs': inputs, 'dependencies': checked['dependencies'],
                'implementation': ref(__file__), 'resources': RESOURCES, 'remote_dir': target,
                'training_request_sha256': old['training_request_sha256'], 'additional_logical_AL_rounds': 0,
                'automatic_retries': 0, 'submission_allowed': False,
                'files': {name: sha256_file(job_dir / name) for name in old['files']},
                'retire_old_copy': ref(checked['case'] / 'training_replica_submission_record.json')}
    path = job_dir / 'manifest.json'
    write_json_exclusive(path, manifest)
    return ref(path)


def verify(path, digest):
    manifest = load_json_object(bound({'path': str(path.resolve(strict=True)), 'sha256': digest}))
    old, checked, inputs = sources(manifest['sources'])
    require(manifest['document_kind'] == 'paper_single_metadata_recovery_manifest'
            and manifest['implementation'] == ref(__file__) and sha256_json(manifest['resources']) == sha256_json(RESOURCES)
            and manifest['inputs'] == inputs and manifest['dependencies'] == checked['dependencies']
            and manifest['submission_allowed'] is False and manifest['automatic_retries'] == 0
            and manifest['additional_logical_AL_rounds'] == 0, 'recovery scope, source or budget changed')
    target = str(PurePosixPath(checked['remote_dir']).parent / LEAF)
    require(manifest['remote_dir'] == target and Path(manifest['case_root']) == checked['case']
            and path.parent == checked['case'] / LEAF
            and manifest['training_request_sha256'] == old['training_request_sha256'], 'recovery target/request mismatch')
    require(set(manifest['files']) == set(old['files']), 'recovery payload file set changed')
    for name, value in manifest['files'].items():
        require(sha256_file(path.parent / name) == value, 'recovery payload changed')
    for key, name in primary.STAGED.items():
        require(manifest['files'][name] == inputs[key]['sha256'], 'staged recovery differs from source')
    require(manifest['files']['request.json'] == old['training_request_artifact_sha256'], 'raw request changed')
    require((path.parent / 'job.sh').read_bytes() == primary.render_job(target, old['training_request_artifact_sha256'], checked['backend']).encode('ascii'), 'launcher changed')
    bound(manifest['retire_old_copy'])
    return manifest, checked


def authorization(reference, manifest_path, manifest_sha256):
    approval = load_json_object(bound(reference))
    require(approval.get('document_kind') == 'user_metadata_training_recovery_authorization'
            and approval.get('decision') == 'approved_one_exact_recovery_job'
            and approval.get('manifest') == {'path': str(manifest_path.resolve(strict=True)), 'sha256': manifest_sha256}
            and type(approval.get('maximum_recovery_jobs')) is int and approval['maximum_recovery_jobs'] == 1
            and sha256_json(approval.get('resources')) == sha256_json(RESOURCES)
            and approval.get('retire_pending_broken_BUCT2_copy') is True
            and approval.get('additional_DFT_jobs') == 0 and approval.get('automatic_retries') == 0,
            'new explicit user approval for this exact recovery is required')
    source = bound(approval['source'])
    require(0 < source.stat().st_size < 10000, 'missing actual user reply')
    return approval


def retire_old_copy(manifest, case):
    """The new approval explicitly names only this still-pending broken copy."""
    record = load_json_object(bound(manifest['retire_old_copy']))
    require(record['status'] == 'SUBMITTED' and record['server_alias'] == 'buct2-gpu'
            and record['observed_hostname'] == 'pc-G7466-M6', 'wrong obsolete copy')
    argv = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', 'buct2-gpu']
    receipt = case / 'training_broken_copy_retirement.json'
    if receipt.exists():
        prior = load_json_object(receipt)
        native = parse_scontrol_job(prior['after_stdout'], record['job_id'])
        require(prior['job_id'] == record['job_id'] and prior['after_state'] == native['job_state']
                and native['job_state'] in ('CANCELLED', 'FAILED', 'TIMEOUT')
                and native['remote_dir'] == record['remote_dir']
                and native['command'] == record['remote_dir'] + '/job.sh', 'unverified prior retirement')
        return
    before = primary.run([*argv, 'scontrol -o show job ' + record['job_id']])
    parsed = parse_scontrol_job(before.stdout, record['job_id'])
    require(parsed['remote_dir'] == record['remote_dir'] and parsed['command'] == record['remote_dir'] + '/job.sh', 'obsolete job identity mismatch')
    if parsed['job_state'] == 'PENDING':
        primary.run([*argv, 'scancel ' + record['job_id']])
    else:
        require(parsed['job_state'] in ('FAILED', 'TIMEOUT', 'CANCELLED'), 'do not retire a running or unexpectedly successful copy')
    after = primary.run([*argv, 'scontrol -o show job ' + record['job_id']])
    final = parse_scontrol_job(after.stdout, record['job_id'])
    require(final['job_state'] in ('FAILED', 'TIMEOUT', 'CANCELLED'), 'obsolete copy not yet confirmed terminal')
    write_json_exclusive(receipt, {'job_id': record['job_id'], 'after_state': final['job_state'],
        'before_stdout': before.stdout, 'after_stdout': after.stdout, 'data_deleted': False})


def submit(path, digest, approval_ref):
    manifest, checked = verify(path, digest)
    authorization(approval_ref, path, digest)
    case, backend, target = checked['case'], checked['backend'], manifest['remote_dir']
    attempt, receipt = case / (LEAF + '_submission_attempt.json'), case / (LEAF + '_submission_record.json')
    require(not receipt.exists(), 'recovery already has a submission receipt')
    retire_old_copy(manifest, case)
    reservation = uuid4().hex
    write_json_exclusive(attempt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'manifest': ref(path), 'authorization': approval_ref, 'automatic_retry': False})
    try:
        lock = str(PurePosixPath(target).parent / 'training_metadata_recovery01_submission.reservation')
        checks = [*primary.remote.remote_path_checks(backend, target), *primary.remote.remote_path_checks(backend, lock),
                  'mkdir ' + shlex.quote(lock), f"printf '%s\\n' {reservation} > {shlex.quote(lock + '/reservation_id')}",
                  'test ! -e ' + shlex.quote(target)]
        primary.run(primary.remote.ssh_argv(backend, 'set -eu; ' + ' && '.join(checks)))
        primary.run(primary.remote.scp_argv(backend, str(path.parent), str(PurePosixPath(target).parent)))
        verify(path, digest)
        authorization(approval_ref, path, digest)
        checks = []
        for name, value in {**manifest['files'], 'manifest.json': digest}.items():
            p = target + '/' + name
            checks += primary.remote.remote_path_checks(backend, p)
            checks.append(f'test "$(sha256sum {shlex.quote(p)} | cut -d\' \' -f1)" = {value}')
        base = checked['request']['base_checkpoint']
        checks += [f'test "$(cat {shlex.quote(lock + "/reservation_id")})" = {reservation}',
                   f'test "$(sha256sum {shlex.quote(base["path"])} | cut -d\' \' -f1)" = {primary.BASE}',
                   'test ! -e ' + shlex.quote(target + '/output'), 'bash -n ' + shlex.quote(target + '/job.sh')]
        argv = ['sbatch', '--parsable', '--no-requeue', '--partition=gpu', '--nodelist=MZ73', '--nodes=1', '--ntasks=1',
                '--cpus-per-task=4', '--gres=gpu:1', '--mem=15G', '--time=00:10:00', '--job-name=chco-train-metadata-recovery',
                '--chdir=' + target, '--output=' + target + '/slurm-%j.out', '--error=' + target + '/slurm-%j.err', target + '/job.sh']
        result = primary.run(primary.remote.ssh_argv(backend, 'set -eu; ' + ' && '.join([*checks, shlex.join(argv)])))
        record = {'status': 'SUBMITTED', 'job_id': primary.remote.parse_sbatch_job_id(result.stdout), 'remote_dir': target,
                  'scheduler': 'Slurm', 'manifest': ref(path), 'authorization': approval_ref, 'reservation_id': reservation,
                  'training_completed': False, 'submit_stdout': result.stdout, 'submit_stderr': result.stderr}
        write_json_exclusive(receipt, record)
        return record
    except BaseException:
        if not receipt.exists():
            write_json_exclusive(receipt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'automatic_retry': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    for name in ('original-manifest', 'failure-packet', 'preflight'):
        prep.add_argument('--' + name, type=Path, required=True)
    execute = commands.add_parser('submit')
    for name in ('manifest', 'authorization'):
        execute.add_argument('--' + name, type=Path, required=True)
        execute.add_argument('--' + name + '-sha256', required=True)
    args = parser.parse_args()
    result = prepare(args) if args.command == 'prepare' else submit(args.manifest.resolve(strict=True), args.manifest_sha256,
        {'path': str(args.authorization.resolve(strict=True)), 'sha256': args.authorization_sha256})
    print(json.dumps(result))


if __name__ == '__main__':
    main()
