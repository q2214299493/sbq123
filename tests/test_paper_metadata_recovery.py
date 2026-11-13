"""Synthetic recovery records with mocked owner context/transport, no jobs."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/paper_training_metadata_recovery.py'
spec = importlib.util.spec_from_file_location('paper_metadata_recovery_tests', SOURCE)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    case = tmp_path / 'MOCK_CASE'
    original_dir = case / 'training_r000'
    original_dir.mkdir(parents=True)
    target = recovery.primary.REMOTE_CASE + '/training_r000'
    request = {'MOCK_REQUEST': True, 'base_checkpoint': {'path': recovery.primary.REMOTE_CASE + '/MOCK_BASE.pt',
                                                       'sha256': recovery.primary.BASE}}
    for name in ('POSCAR', 'force_only_config.yml', 'train_latest_label.py', 'job.sh'):
        (original_dir / name).write_text('MOCK source only: ' + name)
    (original_dir / 'request.json').write_text(json.dumps(request))
    state = case / 'state.json'
    state.write_text('MOCK owner state')
    inputs = {'state': recovery.ref(state), 'worker': recovery.ref(original_dir / 'train_latest_label.py'),
              'template': recovery.ref(original_dir / 'force_only_config.yml'),
              'structure': recovery.ref(original_dir / 'POSCAR'), 'config': recovery.ref(recovery.primary.remote.DEFAULT_CONFIG)}
    original = {'inputs': inputs, 'dependencies': {}, 'training_request_sha256': sha256_json(request),
        'training_request_artifact_sha256': sha256_file(original_dir / 'request.json'),
        'files': {p.name: sha256_file(p) for p in original_dir.iterdir()}}
    manifest = original_dir / 'manifest.json'
    write_json_exclusive(manifest, original)
    write_json_exclusive(case / 'training_submission_record.json', {'status': 'SUBMITTED', 'job_id': '14279',
        'manifest_sha256': sha256_file(manifest), 'remote_dir': target})
    write_json_exclusive(case / 'training_replica_submission_record.json', {'status': 'SUBMITTED', 'job_id': '2280',
        'server_alias': 'buct2-gpu', 'observed_hostname': 'pc-G7466-M6', 'remote_dir': target})
    failure = {'type': 'UnsupportedDatasetError', 'message': 'MOCK metadata attributed with number of atoms',
               'training_request_artifact_sha256': original['training_request_artifact_sha256']}
    raw = json.dumps(failure).encode()
    capture = case / 'capture'
    capture.mkdir()
    packet = capture / 'remote_packet.json'
    native = f'JobId=14279 JobState=FAILED ExitCode=1:0 WorkDir={target} Command={target}/job.sh\n'
    import hashlib

    write_json_exclusive(packet, {'hostname': 'MZ73', 'remote_dir': target, 'native_scontrol': {'returncode': 0, 'stdout': native},
        'files': {'output/training_failure.json': {'raw_base64': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest()}}})
    write_json_exclusive(capture / 'capture_receipt.json', {'stdout_sha256': sha256_file(packet)})
    preflight = case / 'mock_preflight.json'
    write_json_exclusive(preflight, {'status': 'passed', 'training_performed': False, 'GPU_model_constructed': False,
        'trainer_constructed': False, 'worker_sha256': recovery.primary.WORKER,
        'raw_request_sha256': original['training_request_artifact_sha256'], 'dataset_length': 1,
        'metadata': {'sample_count': 1, 'natoms': [49]}, 'movable_atom_count': 31, 'sampler_batches': [[0]],
        'configured_targets_present': ['energy', 'forces'], 'batch_tensor_shapes': {'forces': [49, 3]},
        'preflight_source_sha256': sha256_file(SOURCE.with_name('preflight_single_label_dataset.py'))})
    backend = recovery.primary.remote.load_mz73_static_backend(recovery.primary.budget_owner.TIMEOUT_LEAF)
    checked = {'case': case, 'request': request, 'remote_dir': target, 'backend': backend, 'dependencies': {}}
    monkeypatch.setattr(recovery.primary, 'context', lambda *_: checked)
    args = SimpleNamespace(original_manifest=manifest, failure_packet=packet, preflight=preflight)
    generated = recovery.prepare(args)
    return SimpleNamespace(case=case, path=Path(generated['path']), digest=generated['sha256'], args=args, checked=checked)


def approval(prepared):
    source = prepared.case / 'MOCK_USER_REPLY.txt'
    source.write_text('TEST FIXTURE ONLY, not actual user authorization')
    result = {'document_kind': 'user_metadata_training_recovery_authorization', 'decision': 'approved_one_exact_recovery_job',
        'manifest': recovery.ref(prepared.path), 'maximum_recovery_jobs': 1, 'resources': copy.deepcopy(recovery.RESOURCES),
        'retire_pending_broken_BUCT2_copy': True, 'additional_DFT_jobs': 0, 'automatic_retries': 0, 'source': recovery.ref(source)}
    path = prepared.case / 'approval.json'
    write_json_exclusive(path, result)
    return path, result


def test_prepare_has_no_execution_permission_and_preserves_original_raw_request(prepared):
    manifest, _ = recovery.verify(prepared.path, prepared.digest)
    assert manifest['submission_allowed'] is False and manifest['additional_logical_AL_rounds'] == 0
    assert manifest['resources']['memory'] == '15G' and manifest['resources']['time_limit'] == '00:10:00'
    assert (prepared.path.parent / 'request.json').read_bytes() == (prepared.args.original_manifest.parent / 'request.json').read_bytes()
    assert not (prepared.case / (recovery.LEAF + '_submission_attempt.json')).exists()


@pytest.mark.parametrize('change', ['not_passed', 'trained', 'wrong_worker', 'two_samples', 'wrong_atoms', 'missing_target'])
def test_wrong_real_preflight_cannot_verify_recovery(prepared, change):
    value = json.loads(prepared.args.preflight.read_text())
    if change == 'not_passed':
        value['status'] = 'failed'
    elif change == 'trained':
        value['training_performed'] = True
    elif change == 'wrong_worker':
        value['worker_sha256'] = 'a' * 64
    elif change == 'two_samples':
        value['metadata']['sample_count'] = 2
    elif change == 'wrong_atoms':
        value['metadata']['natoms'] = [50]
    else:
        value['configured_targets_present'] = ['forces']
    prepared.args.preflight.write_text(json.dumps(value))
    manifest = json.loads(prepared.path.read_text())
    manifest['sources']['preflight'] = recovery.ref(prepared.args.preflight)
    with pytest.raises(ValueError, match='preflight'):
        recovery.sources(manifest['sources'])


@pytest.mark.parametrize('key,value', [('decision', 'not_approved'), ('maximum_recovery_jobs', 2),
    ('maximum_recovery_jobs', True), ('automatic_retries', 1), ('additional_DFT_jobs', 1),
    ('retire_pending_broken_BUCT2_copy', False)])
def test_missing_or_expanded_approval_cannot_reach_any_remote_operation(prepared, monkeypatch, key, value):
    path, payload = approval(prepared)
    payload[key] = value
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(recovery.primary, 'run', lambda *_: pytest.fail('unapproved recovery reached transport'))
    monkeypatch.setattr(recovery, 'retire_old_copy', lambda *_: pytest.fail('unapproved recovery reached cancellation'))
    with pytest.raises(ValueError, match='explicit user approval'):
        recovery.submit(prepared.path, prepared.digest, recovery.ref(path))
    assert not (prepared.case / (recovery.LEAF + '_submission_attempt.json')).exists()


def test_one_authorized_mock_submission_and_no_repeat(prepared, monkeypatch):
    approval_path, _ = approval(prepared)
    calls = []
    monkeypatch.setattr(recovery, 'retire_old_copy', lambda *_: None)

    def transport(argv):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='54321\n' if 'sbatch --parsable' in argv[-1] else '', stderr='')

    monkeypatch.setattr(recovery.primary, 'run', transport)
    record = recovery.submit(prepared.path, prepared.digest, recovery.ref(approval_path))
    assert record['job_id'] == '54321' and record['training_completed'] is False
    assert sum('sbatch --parsable' in call[-1] for call in calls) == 1
    assert '--mem=15G' in calls[-1][-1] and '--time=00:10:00' in calls[-1][-1]
    with pytest.raises(ValueError, match='already has'):
        recovery.submit(prepared.path, prepared.digest, recovery.ref(approval_path))


def test_transport_failure_preserves_unknown_and_does_not_repeat(prepared, monkeypatch):
    path, _ = approval(prepared)
    monkeypatch.setattr(recovery, 'retire_old_copy', lambda *_: None)
    calls = []

    def failed(argv):
        calls.append(argv)
        raise RuntimeError('MOCK transport failed')

    monkeypatch.setattr(recovery.primary, 'run', failed)
    with pytest.raises(RuntimeError, match='MOCK'):
        recovery.submit(prepared.path, prepared.digest, recovery.ref(path))
    assert json.loads((prepared.case / (recovery.LEAF + '_submission_record.json')).read_text())['status'] == 'UNKNOWN'
    with pytest.raises(ValueError, match='already has'):
        recovery.submit(prepared.path, prepared.digest, recovery.ref(path))
    assert len(calls) == 1


def test_retire_only_the_exact_pending_broken_copy(prepared, monkeypatch):
    manifest = json.loads(prepared.path.read_text())
    target = prepared.checked['remote_dir']
    before = f'JobId=2280 JobState=PENDING ExitCode=0:0 WorkDir={target} Command={target}/job.sh\n'
    after = before.replace('PENDING', 'CANCELLED')
    calls = []

    def run(argv):
        calls.append(argv)
        stdout = '' if argv[-1] == 'scancel 2280' else (after if len(calls) == 3 else before)
        return SimpleNamespace(stdout=stdout, stderr='', returncode=0)

    monkeypatch.setattr(recovery.primary, 'run', run)
    recovery.retire_old_copy(manifest, prepared.case)
    assert [argv[-1] for argv in calls] == ['scontrol -o show job 2280', 'scancel 2280', 'scontrol -o show job 2280']
    recovery.retire_old_copy(manifest, prepared.case)
    assert len(calls) == 3


@pytest.mark.parametrize('state', ['RUNNING', 'COMPLETED'])
def test_do_not_cancel_a_running_or_unexpectedly_successful_copy(prepared, monkeypatch, state):
    manifest = json.loads(prepared.path.read_text())
    target = prepared.checked['remote_dir']
    native = f'JobId=2280 JobState={state} ExitCode=0:0 WorkDir={target} Command={target}/job.sh\n'
    calls = []

    def run(argv):
        calls.append(argv)
        return SimpleNamespace(stdout=native)

    monkeypatch.setattr(recovery.primary, 'run', run)
    with pytest.raises(ValueError, match='do not retire'):
        recovery.retire_old_copy(manifest, prepared.case)
    assert len(calls) == 1
