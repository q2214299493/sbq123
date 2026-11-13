"""Pure result-contract checks; no real checkpoint or training is fabricated."""
import copy
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/inspect_trained_checkpoint.py'
spec = importlib.util.spec_from_file_location('trained_checkpoint_inspection_tests', SOURCE)
inspection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspection)


def synthetic():
    request = {'protocol_sha256': 'a' * 64, 'base_checkpoint': {'sha256': 'b' * 64}}
    result = {'document_kind': 'aqcat25_paper_single_label_training_result', 'status': 'completed_candidate_only',
        'training_request_artifact_sha256': 'c' * 64, 'protocol_sha256': 'a' * 64, 'base_checkpoint_sha256': 'b' * 64,
        'checkpoint': {'sha256': 'd' * 64}, 'training_evidence': {'completed_epochs': 100, 'completed_steps': 100,
        'observed_optimizer_updates': 100, 'optimizer_update_events': [{'step': i, 'epoch': float(i)} for i in range(1, 101)],
        'execution_devices': {'visible_cuda_device_count': 1, 'model_parameter_devices': ['cuda:0']}},
        **{key: False for key in ('production_checkpoint_promotion', 'scientific_acceptance', 'reportable_final_energy', 'reportable_barrier')}}
    return result, request


def test_result_can_only_supply_candidate_training_evidence():
    result, request = synthetic()
    inspection.training_result_valid(result, request, 'c' * 64)


@pytest.mark.parametrize('change', ['partial', 'no_updates', 'CPU', 'changed_base', 'promotion', 'wrong_request', 'unchanged_model'])
def test_partial_foreign_or_non_GPU_training_is_rejected(change):
    result, request = synthetic()
    result = copy.deepcopy(result)
    if change == 'partial':
        result['training_evidence']['completed_epochs'] = 99
    elif change == 'no_updates':
        result['training_evidence']['optimizer_update_events'] = []
    elif change == 'CPU':
        result['training_evidence']['execution_devices']['model_parameter_devices'] = ['cpu']
    elif change == 'changed_base':
        result['base_checkpoint_sha256'] = 'e' * 64
    elif change == 'promotion':
        result['production_checkpoint_promotion'] = True
    elif change == 'wrong_request':
        result['training_request_artifact_sha256'] = 'e' * 64
    else:
        result['checkpoint']['sha256'] = result['base_checkpoint_sha256']
    with pytest.raises(ValueError):
        inspection.training_result_valid(result, request, 'c' * 64)
