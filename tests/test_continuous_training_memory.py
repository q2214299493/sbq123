from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('tested_continuous_memory', Path(__file__).resolve().parents[1] /
                                            'archive/chco_paper_aqcat25_20261112/continuous_training_memory.py')
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


def report(peak=1024**3):
    return {'document_kind': 'readonly_host_memory_preflight', 'training_performed': False,
            'GPU_model_constructed': False, 'peak_RSS_bytes': peak, 'inspection': {'status': 'passed_candidate_only'}}


def test_full_checkpoint_CPU_preflight_qualifies_without_claiming_training_peak():
    assert memory.validate_preflight(report()) == 1024**3


@pytest.mark.parametrize('peak', [0, -1, 2 * 1024**3, float('nan'), True])
def test_large_or_invalid_CPU_peak_does_not_qualify(peak):
    with pytest.raises(ValueError):
        memory.validate_preflight(report(peak))


def test_incomplete_checkpoint_inspection_does_not_qualify():
    value = report()
    value['inspection']['status'] = 'failed'
    with pytest.raises(ValueError, match='inspection'):
        memory.validate_preflight(value)
