from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import load_json_object, sha256_file
from scripts.neb_agent import mz73_static


spec = importlib.util.spec_from_file_location('tested_continuous_training', Path(__file__).resolve().parents[1] /
                                            'archive/chco_paper_aqcat25_20261112/continuous_training.py')
training = importlib.util.module_from_spec(spec)
spec.loader.exec_module(training)


def setup_transport(tmp_path, monkeypatch):
    leaf = 'training_r001_force003'
    directory = tmp_path / leaf
    directory.mkdir()
    path = directory / 'manifest.json'
    path.write_text('{}')
    target = training.primary.REMOTE_CASE + '/' + leaf
    manifest = {'authorization': {'path': '/test-only/approval', 'sha256': 'a' * 64},
                'files': {'request.json': 'b' * 64, 'job.sh': 'c' * 64}}
    checked = {'case': tmp_path, 'leaf': leaf, 'target': target,
               'backend': mz73_static.load_mz73_static_backend(training.continuation.NAMES[0]),
               'request': {'base_checkpoint': {'path': '/home/sbq/sbq/test-only-frozen.pt', 'sha256': training.primary.BASE}}}
    monkeypatch.setattr(training, 'verify', lambda *args: (manifest, checked))
    return path, leaf


def test_transport_failure_preserves_unknown_receipt_and_blocks_second_submission(tmp_path, monkeypatch):
    path, leaf = setup_transport(tmp_path, monkeypatch)
    calls = []

    def fail(argv):
        calls.append(argv)
        raise RuntimeError('test-only SSH failure; no remote job was submitted')

    monkeypatch.setattr(training.primary, 'run', fail)
    with pytest.raises(RuntimeError, match='test-only'):
        training.submit(path, sha256_file(path))
    receipt = load_json_object(tmp_path / (leaf + '_submission_record.json'))
    assert receipt['status'] == 'UNKNOWN' and receipt['automatic_retries'] == 0
    assert (tmp_path / (leaf + '_submission_attempt.json')).is_file()
    with pytest.raises(ValueError, match='receipt'):
        training.submit(path, sha256_file(path))
    assert len(calls) == 1


def test_native_submit_keeps_exact_GPU_CPU_memory_time_and_no_requeue(tmp_path, monkeypatch):
    path, leaf = setup_transport(tmp_path, monkeypatch)
    calls = []

    def run(argv):
        calls.append(argv)
        return SimpleNamespace(stdout='12345\n' if 'sbatch' in argv[-1] else '', stderr='')

    monkeypatch.setattr(training.primary, 'run', run)
    result = training.submit(path, sha256_file(path))
    assert result['status'] == 'SUBMITTED' and result['job_id'] == '12345'
    command = calls[-1][-1]
    for value in ['--no-requeue', '--ntasks=1', '--gres=gpu:1', '--cpus-per-task=4', '--mem=15G', '--time=00:10:00']:
        assert value in command
    assert not result['training_completed']
    assert load_json_object(tmp_path / (leaf + '_submission_record.json')) == result


def test_invalid_manifest_never_reserves_or_contacts_server(tmp_path, monkeypatch):
    def refuse(*args):
        raise ValueError('test-only stale manifest')

    monkeypatch.setattr(training, 'verify', refuse)
    monkeypatch.setattr(training.primary, 'run', lambda *args: pytest.fail('no network before manifest verification'))
    with pytest.raises(ValueError, match='stale'):
        training.submit(tmp_path / 'nonexistent.json', 'a' * 64)
    assert not list(tmp_path.iterdir())
