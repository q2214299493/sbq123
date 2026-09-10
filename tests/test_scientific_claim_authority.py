from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.scientific_claims import SCIENTIFIC_CLAIM_ACTIONS
from test_b21_scientific_acceptance import bound_case


def claim_gate(validation_path: Path, *, output: Path | None = None):
    root = validation_path.parent
    write_json(root / 'gate_geometry.json', {'status': 'PASS'})
    write_json(root / 'gate_analysis.json', {'path_binding_valid': True, 'image_sequence_complete': True})
    (root / 'gate_thresholds.yaml').write_text('{}\n')
    request = write_json(root / 'gate_request.json', {
        'geometry_file': 'gate_geometry.json', 'analysis_file': 'gate_analysis.json',
        'thresholds_file': 'gate_thresholds.yaml', 'validation_file': str(validation_path),
        'climb': False, 'path_reviewed': False,
    })
    output = output or root / 'claim_gate.json'
    return output, build_decision(request, output)


def assert_no_claim(decision):
    assert decision['DECISION'] != 'VALIDATED_TS'
    assert decision['TS_CLAIM_ALLOWED'] is False
    assert not SCIENTIFIC_CLAIM_ACTIONS.intersection(decision['ALLOWED_ACTIONS'])


def test_audit_boolean_reproduction_fails_at_python_and_cli_boundaries(tmp_path):
    fake = {'source_method': 'dimer', 'frequency_grade': 'A',
            'frequency_structure_hash_valid': True, 'dimer_technical_acceptance': True,
            'compatible_final_energy_barrier_valid': True}
    decision = decide_execution({'status': 'PASS'},
                                {'path_binding_valid': True, 'image_sequence_complete': True}, {},
                                climb=False, path_reviewed=False, validation=fake)
    assert_no_claim(decision)
    assert 'CURRENT_TS_VALIDATION_EVIDENCE_MISSING' in decision['REASON_CODES']
    path, decision = claim_gate(write_json(tmp_path / 'validation.json', fake))
    assert_no_claim(decision)
    assert 'CURRENT_TS_VALIDATION_EVIDENCE_INVALID' in decision['REASON_CODES']
    for action in SCIENTIFIC_CLAIM_ACTIONS:
        with pytest.raises((ValueError, PermissionError)):
            require_action(path, action, decision['state_sha256'])


def test_current_dimer_can_claim_without_execution_or_connectivity(tmp_path, monkeypatch):
    case = bound_case(tmp_path)
    from scripts.neb_agent import submission

    def external_forbidden(*args, **kwargs):
        pytest.fail('scientific claim attempted an external scientific action')

    monkeypatch.setattr(submission, '_run', external_forbidden)
    before = {p: sha256_file(p) for p in tmp_path.rglob('*') if p.is_file()}
    path, decision = claim_gate(case['vfa'] / 'vfa_analysis.json')
    assert decision['DECISION'] == 'VALIDATED_TS'
    assert decision['TS_CLAIM_ALLOWED'] is True
    assert decision['execution_authorization'] is None
    assert decision['ALLOWED_ACTIONS'] == ['APPROVE_TS_CANDIDATE']
    assert decision['SUBMISSION_ALLOWED'] is False
    require_action(path, 'APPROVE_TS_CANDIDATE', decision['state_sha256'])
    for action in ('REPORT_FINAL_BARRIER', 'SUBMIT_VASP', 'START_DIMER', 'START_VFA'):
        with pytest.raises(PermissionError):
            require_action(path, action, decision['state_sha256'])
    assert all(sha256_file(p) == digest for p, digest in before.items())


@pytest.mark.parametrize('damage', ['grade_c', 'missing'])
def test_stale_summary_revokes_old_gate(tmp_path, damage):
    case = bound_case(tmp_path)
    source = case['vfa'] / 'vfa_analysis.json'
    path, decision = claim_gate(source)
    require_action(path, 'APPROVE_TS_CANDIDATE', decision['state_sha256'])
    if damage == 'grade_c':
        write_json(source, {**load_json_object(source), 'grade': 'C', 'dimer_technical_acceptance': False})
    else:
        source.unlink()  # This test owns the temporary artifact.
    for action in SCIENTIFIC_CLAIM_ACTIONS:
        with pytest.raises(ValueError):
            require_action(path, action, decision['state_sha256'])


@pytest.mark.parametrize('owner,name', [
    ('vfa', 'OUTCAR'), ('vfa', 'POSCAR'), ('vfa', 'vfa_handoff.json'),
    ('vfa', 'vfa_scope_review.json'), ('vfa', 'vfa_review.json'),
    ('dimer', 'CONTCAR'), ('dimer', 'OUTCAR'), ('dimer', 'INCAR'),
    ('dimer', 'dimer_analysis.json'), ('dimer', 'dimer_handoff.json'),
    ('dimer', 'MODECAR'), ('dimer', 'final_mode_review.json'),
])
def test_identical_summary_cannot_hide_changed_scientific_source(tmp_path, owner, name):
    case = bound_case(tmp_path)
    summary = case['vfa'] / 'vfa_analysis.json'
    path, decision = claim_gate(summary)
    before = summary.read_bytes()
    changed = case[owner] / name
    changed.write_bytes(changed.read_bytes() + b'\n')
    assert summary.read_bytes() == before
    for action in SCIENTIFIC_CLAIM_ACTIONS:
        with pytest.raises(ValueError):
            require_action(path, action, decision['state_sha256'])


def test_cross_object_vfa_copy_cannot_claim(tmp_path):
    first, second = bound_case(tmp_path / 'first'), bound_case(tmp_path / 'second')
    source = first['vfa'] / 'vfa_analysis.json'
    source.write_bytes((second['vfa'] / 'vfa_analysis.json').read_bytes())
    _, decision = claim_gate(source)
    assert_no_claim(decision)


def test_current_summary_with_forged_technical_acceptance_cannot_claim(tmp_path):
    case = bound_case(tmp_path)
    source = case['vfa'] / 'vfa_analysis.json'
    write_json(source, {**load_json_object(source), 'dimer_technical_acceptance': False})
    _, decision = claim_gate(source)
    assert_no_claim(decision)


def test_scientific_claim_application_delegates_and_gate_remains_thin():
    root = Path(__file__).resolve().parents[1]
    gate = (root / 'scripts/ts_strategy_engine/execution_gate.py').read_text()
    assert len(gate.splitlines()) <= 160
    application = (root / 'scripts/ts_strategy_engine/scientific_claims.py').read_text()
    tree = ast.parse(application)
    assert 'validate_neb_vfa_binding' in application
    assert 'evaluate_validation_pipeline' in application
    assert 'source_bindings_valid' in application
    assert not any(isinstance(n, ast.Import) and any(a.name in {'sqlite3', 'subprocess'} for a in n.names)
                   for n in ast.walk(tree))
    assert 'require_execution_authorization' not in application


@pytest.mark.parametrize('method', ['neb', 'ci_neb'])
def test_neb_claim_keeps_current_connectivity_requirement(tmp_path, method):
    from tests.scientific_claim_fixtures import neb_vfa_case
    from test_ts_strategy_engine import contract
    from scripts.ts_validation.analyze_vfa import analyze_vfa

    case = neb_vfa_case(tmp_path / 'science', contract())
    review_path = case['vfa'] / 'review.json'
    write_json(review_path, {**load_json_object(review_path), 'source_method': method})
    analyze_vfa(case['vfa'], contract(), review_path, case['payload']['frequency_policy'])
    path, decision = claim_gate(case['vfa'] / 'vfa_analysis.json')
    require_action(path, 'APPROVE_TS_CANDIDATE', decision['state_sha256'])
    assert decision['ALLOWED_ACTIONS'] == ['APPROVE_TS_CANDIDATE']
    branch_outcar = case['plus'] / 'OUTCAR'
    branch_outcar.write_bytes(branch_outcar.read_bytes() + b'\n')
    with pytest.raises(ValueError):
        require_action(path, 'APPROVE_TS_CANDIDATE', decision['state_sha256'])


@pytest.mark.parametrize('source', ['contract', 'neb', 'review'])
def test_neb_claim_rejects_current_source_changes_with_identical_summary(tmp_path, source):
    from tests.scientific_claim_fixtures import neb_vfa_case
    from test_ts_strategy_engine import contract

    case = neb_vfa_case(tmp_path / 'science', contract())
    summary = case['vfa'] / 'vfa_analysis.json'
    path, decision = claim_gate(summary)
    before = summary.read_bytes()
    changed = {'contract': case['contract_path'], 'neb': case['neb'] / '07/OUTCAR',
               'review': case['neb'] / 'path_review.json'}[source]
    changed.write_bytes(changed.read_bytes() + b'\n')
    assert summary.read_bytes() == before
    with pytest.raises(ValueError):
        require_action(path, 'APPROVE_TS_CANDIDATE', decision['state_sha256'])


def test_registration_rejects_stale_gate_before_inserting_ts(tmp_path):
    from test_ts_strategy_engine import database
    from scripts.ts_strategy_engine.evidence import record_ts_validation
    from scripts.registry_connection import open_registry

    db = database(tmp_path / 'registry.sqlite3')  # Uses real VFA and registration owners.
    summary = tmp_path / 'registry_science/vfa/vfa_analysis.json'
    payload = load_json_object(summary)
    path, decision = claim_gate(summary)
    record_ts_validation(db, 'positive_current_ts', payload, gate_decision=path,
                         gate_state_sha256=decision['state_sha256'])
    with open_registry(db) as connection:
        assert connection.execute("SELECT grade FROM ts_validations WHERE ts_validation_id='positive_current_ts'").fetchone()['grade'] == 'A'
    write_json(summary, {**payload, 'grade': 'C'})
    with pytest.raises(ValueError):
        record_ts_validation(db, 'stale_ts', payload, gate_decision=path,
                             gate_state_sha256=decision['state_sha256'])
    with open_registry(db) as connection:
        assert connection.execute("SELECT 1 FROM ts_validations WHERE ts_validation_id='stale_ts'").fetchone() is None


@pytest.mark.parametrize('key', ['compatible_final_energy_barrier_valid', 'matched_static_barrier_valid'])
def test_barrier_boolean_addition_never_authorizes_reporting(tmp_path, key):
    case = bound_case(tmp_path)
    summary = case['vfa'] / 'vfa_analysis.json'
    write_json(summary, {**load_json_object(summary), key: True})
    path, decision = claim_gate(summary)
    assert_no_claim(decision)
    with pytest.raises((ValueError, PermissionError)):
        require_action(path, 'REPORT_FINAL_BARRIER', decision['state_sha256'])


def test_frequency_only_dimer_review_does_not_authorize_ts(tmp_path):
    case = bound_case(tmp_path, soft_decision='allow_frequency_handoff')
    _, decision = claim_gate(case['vfa'] / 'vfa_analysis.json')
    assert_no_claim(decision)


def test_nondefault_neb_review_location_still_works(tmp_path):
    from tests.scientific_claim_fixtures import neb_vfa_case
    from test_ts_strategy_engine import contract

    case = neb_vfa_case(tmp_path / 'science', contract(), custom_review=True)
    path, decision = claim_gate(case['vfa'] / 'vfa_analysis.json')
    require_action(path, 'APPROVE_TS_CANDIDATE', decision['state_sha256'])


def test_geometry_and_scope_compatibility_imports_have_one_owner():
    from scripts.ts_validation import analyze_vfa, prepare_vfa_from_ts_image

    for name in ('same_vfa_geometry', 'vfa_scope_checks'):
        assert getattr(prepare_vfa_from_ts_image, name) is getattr(analyze_vfa, name)


def test_matched_static_owner_rejects_stale_ts_before_insertion(tmp_path):
    from test_ts_strategy_engine import database, authoritative_gate, barrier_validation, successful_record
    from scripts.ts_strategy_engine.evidence import record_matched_static_barrier
    from scripts.registry_connection import open_registry

    db = database(tmp_path / 'registry.sqlite3')
    barrier = 'stale_barrier'
    gate, state = authoritative_gate(db, barrier_validation(barrier_set_id=barrier))
    source = tmp_path / 'registry_science/vfa/OUTCAR'
    source.write_bytes(source.read_bytes() + b'\n')
    with pytest.raises(ValueError):
        record_matched_static_barrier(
            db, gate_decision=gate, gate_state_sha256=state, barrier_set_id=barrier,
            reaction_id='co_split', source_calculation_id='calc_ts', ts_validation_id='validation_a',
            initial_result_id='is_energy', ts_result_id='ts_energy', final_result_id='fs_energy',
            learning_record=successful_record(template_id='stale_template', barrier_set_id=barrier),
        )
    with open_registry(db) as connection:
        assert connection.execute("SELECT 1 FROM ts_barriers WHERE barrier_set_id=?", (barrier,)).fetchone() is None
        assert connection.execute("SELECT 1 FROM ts_strategy_templates WHERE template_id='stale_template'").fetchone() is None
