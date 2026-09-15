"""Bind and submit the explicitly approved, immutable SCF chain exactly once."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from archive.scf_mixing_control_20260913 import execute as gate_helper
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.submission import preflight, submit

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'docs/reviews/scf_chain_input_review_20260915'
WORK = ROOT / 'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_scf_chain_20260915'
REMOTE = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/' + WORK.name
MANIFEST_SHA = 'c7b3adc5590257d966c81124a22f9dc5ccfed582588f311ce0cb1081f3468796'
BUNDLE_SHA = '58cd3fde093f83b58beea427c7f30e9347227d044638cab4604b5fc805fe32ba'


def check_unsubmitted():
    for name in ('submission_attempt.json', 'submission_record.json'):
        if (WORK / name).exists():
            raise RuntimeError(f'{name} exists; inspect evidence, never repeat submission')
    assert sha256_file(WORK / 'scf_chain.json') == MANIFEST_SHA
    report = preflight(WORK, 'scf_repair_chain', write_report=False)
    assert report['passed'], report['errors']
    assert report['bundle_sha256'] == BUNDLE_SHA
    assert report == load_json_object(WORK / 'submission_preflight.json')
    return report


def bind(repair_missing_spec=False):
    report = check_unsubmitted()
    if repair_missing_spec:
        rejected = load_json_object(WORK / 'execution_gate_decision.json')
        assert rejected['execution_authorization_error'] == "'spec_sha256'"
        assert rejected['ALLOWED_ACTIONS'] == []
    for name in ('user_execution_authorization.json', 'execution_gate_decision.json'):
        if (WORK / name).exists():
            if not repair_missing_spec:
                raise RuntimeError(f'{name} exists; inspect instead of overwriting')
            saved = WORK / ('rejected_missing_spec_' + name)
            if saved.exists():
                raise RuntimeError('Repair already attempted; inspect existing evidence')
            shutil.copyfile(WORK / name, saved)
    geometry = load_json_object(REVIEW / 'input_review.json')['source_bindings']['geometry']
    assert sha256_file(Path(geometry['path'])) == geometry['sha256']
    analysis = gate_helper.analyze(WORK, gate_helper.THRESHOLDS, reaction_indices=[49])
    assert analysis['status'] == 'NO_OUTPUT'
    auth = {
        'action': 'SUBMIT_DIAGNOSTIC_VASP', 'calculation_kind': 'scf_repair_chain',
        'target': {'server_alias': 'sunboquan-codex', 'remote_dir': REMOTE},
        'workdir_identity': gate_helper.workdir_identity(WORK),
        'bundle_sha256': report['bundle_sha256'],
        'potcar': {'source': '~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR',
                   'spec_sha256': report['files']['POTCAR.spec'],
                   'sha256': 'e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85'},
        'scf_chain_scope': {'manifest_sha256': MANIFEST_SHA,
                            'stages': ['A_fixed_density', 'B_self_consistent', 'C_restart'],
                            'max_allocations': 1, 'retry': False},
    }
    gate_helper.REQUEST = REVIEW / 'user_submission_authorization.md'
    _, decision = gate_helper.make_gate(WORK, {
        'geometry': Path(geometry['path']), 'analysis': WORK / 'neb_analysis.json',
        'thresholds': gate_helper.THRESHOLDS, 'preflight': WORK / 'submission_preflight.json',
    }, auth, path_reviewed=True)
    print(json.dumps({'decision': decision['DECISION'], 'allowed': decision['ALLOWED_ACTIONS'],
                      'bundle_sha256': BUNDLE_SHA}))


def submit_once():
    check_unsubmitted()
    auth = load_json_object(WORK / 'user_execution_authorization.json')
    result = submit(WORK, WORK / 'execution_gate_decision.json',
                    host='sunboquan-codex', remote_dir=REMOTE,
                    potcar_source=auth['potcar']['source'], potcar_sha256=auth['potcar']['sha256'],
                    action='SUBMIT_DIAGNOSTIC_VASP')
    print(json.dumps(result))


def record():
    receipt = load_json_object(WORK / 'submission_record.json')
    scheduler = load_json_object(WORK / 'scheduler_after_submission.json')
    assert receipt['status'] == 'SUBMITTED'
    assert receipt['job_id'] == scheduler['job_id'] == '9757725'
    for name in ('submission_record.json', 'scheduler_after_submission.json',
                 'user_execution_authorization.json', 'execution_gate_decision.json'):
        if (REVIEW / name).exists():
            raise RuntimeError('Review copy exists; inspect before repeating')
        shutil.copyfile(WORK / name, REVIEW / name)
    event = load_json_object(REVIEW / 'task_state_event.json')
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    event.update(event_id='task-scf-chain-submitted-20260915', occurred_at=now, recorded_at=now,
                 supersedes=['task-scf-chain-inputs-prepared-20260915'],
                 summary='Authorized frozen three-stage SCF job 9757725 submitted once; scheduler PEND.')
    references = [
        'docs/reviews/scf_chain_input_review_20260915/' + name for name in (
            'user_submission_authorization.md', 'submission_record.json',
            'scheduler_after_submission.json', 'user_execution_authorization.json',
            'execution_gate_decision.json', 'input_review.json')]
    event['evidence'] = [dict(locator=name, sha256=sha256_file(ROOT / name),
                              authority='repository_document', observed_at=now)
                         for name in references]
    event['payload'].update(
        current_evidence=[
            'User explicitly authorized the frozen three-stage scope and positive warning/stop policy.',
            'Canonical current hash-bound gate allowed SUBMIT_DIAGNOSTIC_VASP; immutable bundle verified unchanged.',
            'Exactly one LSF allocation submitted: job 9757725, Gkn_normal, scheduler PEND at ' + scheduler['checked_at'] + '.',
            '80 ranks; A_fixed_density then B_self_consistent then C_restart, conditional on each prior stage passing.',
            'Maximum 10800 seconds per stage, 9 hours total; no automatic retry.',
            'Same 50-atom geometry and SIGMA=0.20 physical branch; candidate NCORE=8 and NBANDS=320.',
            'Not yet evidence of electronic convergence, saved-state reproducibility, numerical repair, or TS validity.',
        ],
        one_executable_step='Inspect job 9757725 stage progress and immutable stage evidence; if terminal, validate A/B/C outcomes and report without retry or Dimer submission.',
        submission_boundary='One authorized submission consumed. No further allocation, resubmission, Dimer, or scientific acceptance authorized.',
        authoritative_references=references)
    target = REVIEW / 'submitted_task_state_event.json'
    write_json_exclusive(target, event)
    print(json.dumps({'event': str(target), 'job_id': receipt['job_id'], 'scheduler': scheduler['status']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['bind', 'repair-spec-binding', 'submit', 'record'])
    args = parser.parse_args()
    {'bind': bind, 'repair-spec-binding': lambda: bind(True), 'submit': submit_once,
     'record': record}[args.stage]()
