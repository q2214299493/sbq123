from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file
from scripts.dual_model_ml_neb import run_dual_model_request, seal_successful_run
from scripts.prepare_gpu_path_dimer import bind
from scripts.ts_strategy_engine.dimer_gate import evaluate_candidate_triad
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.gpu_dimer_parent import PARENT_METHOD, validate_reviewed_gpu_parent
from tests.test_dual_model_ml_neb import _fixture, PathCalculator
from tests.test_ts_strategy_engine import contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def reviewed(tmp_path):
    request_path, primary, secondary = _fixture(tmp_path)
    c = contract(atom_map=[[i, i] for i in range(6)], reaction_atoms=[5],
                 atom_symbols=['Fe', 'C', 'C', 'O', 'H', 'H'],
                 broken_bonds=[], formed_bonds=[[3, 5]])
    contract_path = tmp_path / 'contract.json'
    contract_path.write_text(json.dumps(c))
    request = json.loads(request_path.read_text())
    fields = ('contract_sha256', 'atom_map_sha256', 'compatibility_sha256')
    request['reaction'].update({key: c[key] for key in fields})
    request_path.write_text(json.dumps(request))
    output = tmp_path / 'output'
    candidate = run_dual_model_request(request_path, primary, secondary, output, device='cpu',
                                      calculator_loader=lambda *args: PathCalculator(0))
    seal_successful_run(output, candidate)
    manifest_path = output / 'dual_model_gpu_ml_neb_path_manifest.candidate.json'
    policy = ROOT / 'configs/dimer_gate.yaml'
    artifact = tmp_path / 'review_evidence.json'
    artifact.write_text('{}')
    review = {'document_kind': 'gpu_dimer_path_review', 'status': 'accepted_for_direct_dimer_candidate',
              'candidate_manifest_sha256': sha256_file(manifest_path), 'policy_sha256': sha256_file(policy),
              'candidate_image': '02', 'reviewer': 'Test reviewer', 'reviewed_at': '2026-09-10T00:00:00Z',
              'target_reaction_event': 'H approaches O', 'reaction_atom_indices_zero_based': [5],
              'evidence': {key: bind(artifact) for key in ('geometry', 'dist', 'movie')}}
    review.update({key: 'accepted' for key in ('geometry_continuity', 'periodic_mapping',
                  'reaction_coordinate_resolution', 'elementary_step_assignment', 'candidate_selection')})
    review_path = tmp_path / 'review.json'
    review_path.write_text(json.dumps(review))
    analysis = {'parent_neb_method': PARENT_METHOD, 'status': 'ML_CANDIDATE_REVIEWED',
                'maximum_image': '02', 'path_binding_valid': True, 'image_sequence_complete': True,
                'dimer_gate_policy_file': str(policy), 'dimer_gate_policy_sha256': sha256_file(policy),
                **{key: c[key] for key in fields},
                'gpu_reviewed_path_evidence': {key: bind(path) for key, path in (
                    ('request', request_path), ('manifest', manifest_path), ('review', review_path),
                    ('contract', contract_path))}}
    paths = [output / 'images' / name / 'POSCAR' for name in ('01', '02', '03')]
    return analysis, paths


def test_reviewed_gpu_path_needs_no_vasp_outputs(reviewed):
    analysis, paths = reviewed
    gate = evaluate_candidate_triad(*paths, analysis, [5])
    assert gate['hard_gate_passed'], gate
    assert 'triad_outputs_complete' not in gate['hard_checks']
    decision = decide_execution({'status': 'PASS'}, analysis, {}, climb=False, path_reviewed=True)
    assert decision['ALLOWED_ACTIONS'] == ['PREPARE_DIMER_HANDOFF']
    assert not decision['DIMER_ALLOWED']
    assert not decision['TS_CLAIM_ALLOWED']


@pytest.mark.parametrize('source', ['request', 'manifest', 'review', 'contract'])
def test_changed_source_revokes_gpu_entry(reviewed, source):
    analysis, _ = reviewed
    path = Path(analysis['gpu_reviewed_path_evidence'][source]['path'])
    path.write_bytes(path.read_bytes() + b'\n')
    assert not validate_reviewed_gpu_parent(analysis)['passed']
    decision = decide_execution({'status': 'PASS'}, analysis, {}, climb=False, path_reviewed=True)
    assert decision['ALLOWED_ACTIONS'] == []


def test_changed_structure_and_missing_review_rejected(reviewed):
    analysis, paths = reviewed
    paths[1].write_bytes(paths[1].read_bytes() + b'\n')
    assert not evaluate_candidate_triad(*paths, analysis, [5])['hard_gate_passed']


def test_ordinary_parent_still_needs_electronic_outputs(reviewed):
    analysis, paths = reviewed
    analysis['parent_neb_method'] = 'ordinary_neb'
    gate = evaluate_candidate_triad(*paths, analysis, [5])
    assert not gate['hard_gate_passed']
    assert 'triad_outputs_complete' in gate['hard_gate_errors']


def test_missing_semantic_review_cannot_be_replaced_by_rehash(reviewed):
    analysis, _ = reviewed
    path = Path(analysis['gpu_reviewed_path_evidence']['review']['path'])
    value = json.loads(path.read_text())
    value['elementary_step_assignment'] = 'needs_review'
    path.write_text(json.dumps(value))
    analysis['gpu_reviewed_path_evidence']['review'] = bind(path)
    assert not validate_reviewed_gpu_parent(analysis)['passed']
