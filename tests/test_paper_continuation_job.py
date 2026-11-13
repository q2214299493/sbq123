"""Synthetic continuation bundle/transport checks; no real model or job."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/paper_continuation_job.py'
spec = importlib.util.spec_from_file_location('paper_continuation_job_tests', SOURCE)
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


def test_real_local_remote_case_names_are_an_explicit_pair(tmp_path, monkeypatch):
    resolved = {'remote_root': job.primary.REMOTE_CASE + '/labels'}
    monkeypatch.setattr(job.primary.remote, 'load_mz73_static_backend', lambda *_: resolved)
    assert job.backend(tmp_path / 'paper_aqcat25_ft512_20261112_v1') == resolved
    with pytest.raises(ValueError, match='another case'):
        job.backend(tmp_path / 'foreign_case')


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    case = tmp_path / 'MOCK_CASE'
    initial = case / 'initial_search'
    initial.mkdir(parents=True)
    names = ('initial_candidate.py', 'aqcat_ts_pilot.py', 'mlip_same_structure_benchmark.py', 'artifact_io.py')
    for name in (*names, 'IS.vasp'):
        (initial / name).write_text('MOCK source: ' + name)
    author = case / 'author_runtime_sources/calculations.py'
    author.parent.mkdir()
    author.write_text('MOCK author source')
    guard = case / 'mock_guard.json'
    guard.write_text('{"MOCK": true}')
    original = {'source_files': [{'path': '/home/sbq/sbq/MOCK/initial_search/' + name, 'sha256': sha256_file(initial / name)} for name in names]
                + [{'path': '/home/sbq/sbq/MOCK/author/calculations.py', 'sha256': sha256_file(author)}],
                'initial': {'path': '/home/sbq/sbq/MOCK/initial_search/IS.vasp', 'sha256': sha256_file(initial / 'IS.vasp')},
                'geometry_guard_source': job.ref(guard), 'checkpoint': {'sha256': job.primary.BASE}}
    write_json_exclusive(initial / 'request.json', original)
    state_path = case / 'state.json'
    state_path.write_text('{"MOCK": true}')
    train = case / 'training_r000_metadata_recovery01'
    train.mkdir()
    (train / 'request.json').write_text('MOCK original raw training request')
    result = case / 'mock_training_result.json'
    result.write_text('MOCK training result: no scientific data')
    binding = {'training_result': job.ref(result)}
    write_json_exclusive(case / 'training14292_candidate_checkpoint_binding.json', binding)
    previous, trajectory = case / 'MOCK_previous.vasp', case / 'MOCK_previous.traj'
    previous.write_text('MOCK previous pose')
    trajectory.write_text('MOCK previous trajectory')
    state = {'protocol_sha256': 'a' * 64, 'search_checkpoint': {'path': '/home/sbq/sbq/MOCK/checkpoint.pt', 'sha256': 'b' * 64}}
    monkeypatch.setattr(job, 'context', lambda *_: (state, binding, original, previous, trajectory))
    backend = {'remote_root': '/home/sbq/sbq/MOCK_CASE/labels', 'remote_write_boundary': '/home/sbq/sbq',
               'canonical_write_boundary': '/home/ubuntu/hdd/sbq/sbq'}
    monkeypatch.setattr(job, 'backend', lambda *_: backend)
    monkeypatch.setattr(job.primary.remote, 'ssh_argv', lambda _b, command: ['MOCK_SSH', command])
    monkeypatch.setattr(job.primary.remote, 'scp_argv', lambda *_: ['MOCK_SCP', 'copy'])
    reply = case / 'MOCK_USER_REPLY.txt'
    reply.write_text('TEST FIXTURE ONLY: not a compute authorization')
    args = SimpleNamespace(case_root=case, state=state_path, state_sha256=sha256_file(state_path), execution_source=reply)
    generated = job.prepare(args)
    return SimpleNamespace(case=case, path=Path(generated['path']), digest=generated['sha256'], args=args)


def test_only_previous_geometry_and_new_registered_checkpoint_are_bound(prepared):
    manifest, _ = job.verify(prepared.path, prepared.digest)
    request = load_json_object(prepared.path.parent / 'request.json')
    assert manifest['DFT_submission_allowed'] is False and manifest['automatic_retries'] == 0
    assert request['document_kind'] == 'paper_sequential_candidate_continuation_request'
    assert request['checkpoint']['sha256'] != job.primary.BASE
    assert {'previous_candidate', 'previous_trajectory', 'training_request', 'training_result'} <= request.keys()
    assert 'final' not in request and 'idpp' not in request
    mapping = load_json_object(prepared.path.parent / 'source_map_seed.json')['source_map']
    mapped = {row['source_path'] for row in mapping}
    expected = {row['path'] for row in request['source_files']}
    expected.update(request[key]['path'] for key in ('initial_request', 'training_request', 'training_result', 'previous_candidate', 'previous_trajectory'))
    original = load_json_object(prepared.path.parent / 'original_request.json')
    expected.update((original['initial']['path'], original['geometry_guard_source']['path']))
    assert expected <= mapped and len(mapped) == len(mapping)


def test_changed_staged_worker_cannot_reach_transport(prepared, monkeypatch):
    (prepared.path.parent / 'next_candidate.py').write_text('CHANGED MOCK worker')
    monkeypatch.setattr(job.primary, 'run', lambda *_: pytest.fail('changed worker reached SSH'))
    with pytest.raises(ValueError, match='staged bytes changed'):
        job.submit(prepared.path, prepared.digest)


def test_one_mock_bounded_submission_and_no_repeat(prepared, monkeypatch):
    calls = []

    def run(argv):
        calls.append(argv)
        return SimpleNamespace(stdout='12345\n' if 'sbatch --parsable' in argv[-1] else '', stderr='', returncode=0)

    monkeypatch.setattr(job.primary, 'run', run)
    receipt = job.submit(prepared.path, prepared.digest)
    assert receipt['job_id'] == '12345' and receipt['DFT_submitted'] is False and receipt['training_performed'] is False
    assert sum('sbatch --parsable' in call[-1] for call in calls) == 1
    assert '--time=00:10:00' in calls[-1][-1] and '--mem=15G' in calls[-1][-1]
    with pytest.raises(ValueError, match='already has'):
        job.submit(prepared.path, prepared.digest)


def test_transport_failure_remains_unknown_and_forbids_retry(prepared, monkeypatch):
    calls = []

    def fail(argv):
        calls.append(argv)
        raise RuntimeError('MOCK SSH failure')

    monkeypatch.setattr(job.primary, 'run', fail)
    with pytest.raises(RuntimeError, match='MOCK'):
        job.submit(prepared.path, prepared.digest)
    assert load_json_object(prepared.case / (job.LEAF + '_submission_record.json'))['status'] == 'UNKNOWN'
    with pytest.raises(ValueError, match='already has'):
        job.submit(prepared.path, prepared.digest)
    assert len(calls) == 1
