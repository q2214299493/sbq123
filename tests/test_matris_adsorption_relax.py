from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file
from scripts.adsorption import matris_adsorption_relax as trial


@pytest.fixture
def source(tmp_path, monkeypatch):
    checkpoint = tmp_path / 'weights.pth'
    checkpoint.write_bytes(b'unit test checkpoint, not model weights')
    document = dict(direction='work_to_gpu', workflow_kind='adsorption',
                    model=dict(identifier='MatRIS provider baseline', checkpoint_sha256=sha256_file(checkpoint)))
    monkeypatch.setattr(trial, 'validate_handoff', lambda *_a, **_k: document)
    return document, checkpoint


def test_preflight_only_checks_files_not_model(source):
    document, checkpoint = source
    assert trial.preflight(Path('input.json'), checkpoint, Path('schema.json')) is document


def test_preflight_rejects_missing_checkpoint(source):
    _, checkpoint = source
    with pytest.raises(FileNotFoundError, match='checkpoint missing'):
        trial.preflight(Path('input.json'), checkpoint.with_name('missing.pth'), Path('schema.json'))


def test_preflight_rejects_changed_checkpoint(source):
    _, checkpoint = source
    checkpoint.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        trial.preflight(Path('input.json'), checkpoint, Path('schema.json'))


@pytest.mark.parametrize('field,value', [('direction', 'gpu_to_work'), ('workflow_kind', 'transition_state')])
def test_preflight_rejects_wrong_handoff(source, field, value):
    document, checkpoint = source
    document[field] = value
    with pytest.raises(ValueError, match='work-to-GPU'):
        trial.preflight(Path('input.json'), checkpoint, Path('schema.json'))


def test_preflight_rejects_aqcat_model(source):
    document, checkpoint = source
    document['model']['identifier'] = 'AQCat25 baseline'
    with pytest.raises(ValueError, match='not a MatRIS'):
        trial.preflight(Path('input.json'), checkpoint, Path('schema.json'))
