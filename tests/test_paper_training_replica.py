"""Bounded replica controls with synthetic payloads and mocked SSH only."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import sha256_file, write_json_exclusive

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/paper_training_replica.py'
spec = importlib.util.spec_from_file_location('paper_training_replica_tests', SOURCE)
replica = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replica)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    case = tmp_path / 'MOCK_CASE'
    staging = case / 'training_r000'
    staging.mkdir(parents=True)
    target = replica.primary.REMOTE_CASE + '/training_r000'
    for name in ('POSCAR', 'request.json', 'force_only_config.yml', 'train_latest_label.py', 'job.sh'):
        (staging / name).write_text('MOCK NOT SCIENTIFIC: ' + name)
    original = {'files': {p.name: sha256_file(p) for p in staging.iterdir()}, 'training_request_sha256': 'a' * 64}
    path = staging / 'manifest.json'
    write_json_exclusive(path, original)
    request = {'base_checkpoint': {'path': replica.ROOT + '/mock/checkpoint.pt', 'sha256': replica.primary.BASE}}
    checked = {'case': case, 'remote_dir': target, 'backend': {}, 'request': request}
    monkeypatch.setattr(replica.primary, 'verify', lambda *_: (original, checked))
    monkeypatch.setattr(replica.primary.remote, 'ssh_argv', lambda _backend, command: ['MOCK_SSH', command])
    native = f'JobId=14279 JobState=PENDING Reason=Resources ExitCode=0:0 WorkDir={target} Command={target}/job.sh\n'
    monkeypatch.setattr(replica.primary, 'run', lambda *_: SimpleNamespace(stdout=native, stderr='', returncode=0))
    receipt = case / 'training_submission_record.json'
    write_json_exclusive(receipt, {'status': 'SUBMITTED', 'job_id': '14279', 'remote_dir': target})
    reply = case / 'MOCK_REPLY.txt'
    reply.write_text('TEST FIXTURE: no actual compute authorization')
    authorization = case / 'authorization.json'
    write_json_exclusive(authorization, {'document_kind': 'user_same_round_replica_authorization',
        'decision': 'approved_MZ73_BUCT2_first_valid_result', 'allowed_hosts': ['MZ73', replica.NODE],
        'logical_training_rounds': 1, 'maximum_physical_training_copies': 2, 'additional_AL_rounds': 0,
        'automatic_failure_retry': False, 'case_root': str(case), 'primary_manifest': replica.ref(path),
        'primary_receipt': replica.ref(receipt), 'source': replica.ref(reply)})
    config = case / 'backends.yaml'
    config.write_text('backends:\n  buct2_gpu:\n    role: candidate_acceleration_only\n'
                      '    ssh: {alias: buct2-gpu}\n    remote_write_boundary: /home/sbq/sbq\n')
    args = SimpleNamespace(primary_manifest=path, primary_sha256=sha256_file(path), authorization=authorization, config=config)
    generated = replica.prepare(args)
    return SimpleNamespace(case=case, args=args, path=Path(generated['path']), digest=generated['sha256'],
                           checked=checked, original=original, native=native)


def test_identical_request_and_recipe_bytes_with_host_only_launcher(prepared):
    manifest, _ = replica.verify(prepared.path, prepared.digest)
    for name in ('request.json', 'POSCAR', 'force_only_config.yml', 'train_latest_label.py'):
        assert manifest['files'][name] == prepared.original['files'][name]
    script = (prepared.path.parent / 'job.sh').read_text()
    assert 'test "$(hostname -s)" = pc-G7466-M6' in script
    assert 'PYTHONHOME=' + replica.DEPLOYED + '/deps/usr' in script
    assert replica.PYTHON in script and '100' not in manifest['resources']['time_limit']
    assert '/home/ubuntu/hdd' not in script
    assert manifest['resources'] == {**replica.primary.RESOURCES, 'node': replica.NODE}


@pytest.mark.parametrize('field,value', [('logical_training_rounds', 2), ('maximum_physical_training_copies', 3),
    ('additional_AL_rounds', 1), ('automatic_failure_retry', True), ('allowed_hosts', ['MZ73', 'FOREIGN'])])
def test_replica_cannot_expand_authorized_budget(prepared, field, value):
    auth = json.loads(prepared.args.authorization.read_text())
    auth[field] = value
    prepared.args.authorization.write_text(json.dumps(auth))
    with pytest.raises(ValueError, match='authorization'):
        replica.verify_authorization(prepared.args.authorization, prepared.case,
            replica.ref(prepared.args.primary_manifest), replica.ref(prepared.case / 'training_submission_record.json'))


@pytest.mark.parametrize('change', ['RUNNING', 'FAILED', 'TIMEOUT', 'Reason=Dependency', 'Reason=JobHeldUser', 'foreign_dir'])
def test_only_native_resource_queued_primary_can_trigger_replica(prepared, monkeypatch, change):
    native = prepared.native
    if change in ('RUNNING', 'FAILED', 'TIMEOUT'):
        native = native.replace('JobState=PENDING', 'JobState=' + change)
    elif change == 'foreign_dir':
        native = native.replace('WorkDir=' + prepared.checked['remote_dir'], 'WorkDir=/foreign')
    else:
        native = native.replace('Reason=Resources', change)
    monkeypatch.setattr(replica.primary, 'run', lambda *_: SimpleNamespace(stdout=native))
    with pytest.raises(ValueError):
        replica.queued_primary(prepared.checked, replica.ref(prepared.case / 'training_submission_record.json'))


def test_changed_payload_cannot_reach_submission(prepared, monkeypatch):
    (prepared.path.parent / 'request.json').write_text('changed mock label')
    monkeypatch.setattr(replica, 'run', lambda *_: pytest.fail('invalid payload must not reach SSH'))
    with pytest.raises(ValueError, match='bytes changed'):
        replica.submit(prepared.path, prepared.digest)
    assert not (prepared.case / 'training_replica_submission_attempt.json').exists()


def test_transport_failure_retains_unknown_reservation_and_forbids_repeat(prepared, monkeypatch):
    calls = []

    def failed(argv):
        calls.append(argv)
        raise RuntimeError('MOCK transport failure')

    monkeypatch.setattr(replica, 'run', failed)
    with pytest.raises(RuntimeError, match='MOCK'):
        replica.submit(prepared.path, prepared.digest)
    assert len(calls) == 1
    assert json.loads((prepared.case / 'training_replica_submission_record.json').read_text())['status'] == 'UNKNOWN'
    with pytest.raises(ValueError, match='receipt already exists'):
        replica.submit(prepared.path, prepared.digest)
    assert len(calls) == 1


def test_exactly_one_mock_sbatch_with_existing_request(prepared, monkeypatch):
    calls = []

    def transport(argv):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='54321\n' if 'sbatch' in argv[-1] else '{}', stderr='')

    monkeypatch.setattr(replica, 'run', transport)
    record = replica.submit(prepared.path, prepared.digest)
    assert record['job_id'] == '54321' and record['additional_AL_rounds'] == 0
    submits = [call[-1] for call in calls if 'sbatch --parsable' in call[-1]]
    assert len(submits) == 1
    assert '--mem=16G' in submits[0] and '--time=00:10:00' in submits[0] and '--no-requeue' in submits[0]
    assert 'base.open(\'xb\')' in replica.remote_preflight(json.loads(prepared.path.read_text()), prepared.checked['request'], 'mock')
