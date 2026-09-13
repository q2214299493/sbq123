"""One authorized SCF handoff; uses canonical gates/executors, no direct bsub/bkill."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pymatgen.io.vasp.inputs import Incar

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight, stop_job, submit
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_strategy_engine.execution_evidence import (
    execution_evidence_sha256, load_bound_evidence, workdir_identity,
)
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822'
OLD = BASE / 'h_migration_int06_mid_scf_no0440_v2_20260913'
NEW = BASE / 'h_migration_int06_mid_scf_mixing_control_20260913'
REVIEW = ROOT / 'docs/reviews/scf_mixing_control_20260913'
CONTROL = Path(__file__).resolve().parent
THRESHOLDS = ROOT / 'configs/neb_agent/default_thresholds.yaml'
REQUEST = CONTROL / 'user_request.md'
REMOTE = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/' + NEW.name


def make_gate(folder, paths, auth, *, path_reviewed):
    bindings = {}
    request = {name + '_file': str(path) for name, path in paths.items()}
    data = {name: load_bound_evidence(folder / 'gate_request.json', request, name, bindings)
            for name in paths}
    core = {name: data.pop(name, {}) for name in ('geometry', 'analysis', 'thresholds')}
    kwargs = dict(climb=False, path_reviewed=path_reviewed, **data, source_bindings=bindings)
    initial = decide_execution(**core, **kwargs)
    auth.update({
        'schema_version': 1, 'document_kind': 'user_execution_authorization',
        'authorized_at': datetime.now(timezone.utc).isoformat(),
        'source': {'path': str(REQUEST), 'sha256': sha256_file(REQUEST)},
        'evidence_sha256': execution_evidence_sha256(initial['EVIDENCE']),
    })
    auth_path = folder / 'user_execution_authorization.json'
    write_json(auth_path, auth)
    bindings['authorization'] = {'path': str(auth_path), 'sha256': sha256_file(auth_path)}
    decision = decide_execution(**core, **kwargs, authorization=auth)
    path = folder / 'execution_gate_decision.json'
    write_json(path, decision)
    require_action(path, auth['action'], decision['state_sha256'])
    return path, decision


def stop_existing():
    folder = CONTROL / 'stop9753825'
    if (folder / 'stop_receipt.json').exists():
        raise RuntimeError('Stop receipt already exists; inspect live state, do not repeat.')
    folder.mkdir(exist_ok=True)
    scheduler = query_lsf_job('9753825', stage='diagnostic_static')
    write_json(folder / 'scheduler_before.json', scheduler)
    if scheduler['status'] not in {'RUN', 'PEND'}:
        print(json.dumps({'job_id': '9753825', 'status': scheduler['status'], 'stop_sent': False}))
        return
    old_record = load_json_object(OLD / 'submission_record.json')
    auth = {
        'action': 'STOP_JOB', 'job_id': '9753825',
        'allowed_scheduler_statuses': ['RUN', 'PEND'],
        'target': {'server_alias': 'sunboquan-codex', 'remote_dir': old_record['remote_dir'], 'job_id': '9753825'},
        'workdir_identity': workdir_identity(OLD), 'bundle_sha256': old_record['bundle_sha256'],
    }
    gate, _ = make_gate(folder, {'thresholds': THRESHOLDS, 'scheduler': folder/'scheduler_before.json'},
                        auth, path_reviewed=False)
    result = stop_job(gate, 'sunboquan-codex', '9753825', folder/'stop_receipt.json')
    print(json.dumps({'stop_receipt': str(folder/'stop_receipt.json'), 'message': result['stop_stdout']}))
    after = query_lsf_job('9753825', stage='diagnostic_static')
    write_json(folder/'scheduler_after.json', after)
    print(json.dumps({'job_id': '9753825', 'status': after['status']}))


def prepare():
    review = load_json_object(REVIEW/'review_request.json')
    for name, digest in review['source_sha256'].items():
        assert sha256_file(OLD/name) == digest, name
    assert sha256_file(REVIEW/'INCAR.recommended') == review['candidate_sha256']
    NEW.mkdir(exist_ok=False)
    for name in ('POSCAR', 'KPOINTS', 'POTCAR.spec', 'script.lsf'):
        shutil.copyfile(OLD/name, NEW/name)
    shutil.copyfile(REVIEW/'INCAR.recommended', NEW/'INCAR')
    before, after = Incar.from_file(OLD/'INCAR'), Incar.from_file(NEW/'INCAR')
    delta = [k for k in sorted(set(before)|set(after)) if before.get(k) != after.get(k)]
    assert delta == ['AMIX', 'AMIX_MAG'], delta
    assert after['AMIX'] == 0.2 and after['AMIX_MAG'] == 0.8
    old_gate = load_json_object(OLD/'execution_gate_decision.json')
    geometry = old_gate['EVIDENCE']['source_bindings']['geometry']
    assert sha256_file(Path(geometry['path'])) == geometry['sha256']
    assert sha256_file(NEW/'POSCAR') == review['source_sha256']['POSCAR']
    analysis = analyze(NEW, THRESHOLDS, reaction_indices=[49])
    assert analysis['status'] == 'NO_OUTPUT'
    report = preflight(NEW, 'diagnostic_static')
    assert report['passed'], report['errors']
    prior = load_json_object(OLD/'user_execution_authorization.json')
    auth = {'action': 'SUBMIT_DIAGNOSTIC_VASP', 'calculation_kind': 'diagnostic_static',
            'target': {'server_alias': 'sunboquan-codex', 'remote_dir': REMOTE},
            'workdir_identity': workdir_identity(NEW), 'bundle_sha256': report['bundle_sha256'],
            'potcar': prior['potcar']}
    write_json(NEW/'mixing_control_identity.json', {
        'source_job': '9753825', 'source_review': str(REVIEW/'review_request.json'),
        'source_review_sha256': sha256_file(REVIEW/'review_request.json'),
        'only_changed_incar_keys': delta, 'source_structure_identical': True,
        'candidate_sha256': sha256_file(NEW/'INCAR'), 'user_request_sha256': sha256_file(REQUEST),
    })
    _, decision = make_gate(NEW, {'geometry': Path(geometry['path']),
        'analysis': NEW/'neb_analysis.json', 'thresholds': THRESHOLDS,
        'preflight': NEW/'submission_preflight.json'}, auth, path_reviewed=True)
    print(json.dumps({'workdir':str(NEW),'preflight':report['passed'],'decision':decision['DECISION'],
                      'allowed':decision['ALLOWED_ACTIONS'],'bundle_sha256':report['bundle_sha256']}))


def submit_new():
    auth = load_json_object(NEW/'user_execution_authorization.json')
    result = submit(NEW, NEW/'execution_gate_decision.json', 'sunboquan-codex', REMOTE,
                    auth['potcar']['source'], auth['potcar']['sha256'], 'SUBMIT_DIAGNOSTIC_VASP')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['stop', 'prepare', 'submit'])
    args = parser.parse_args()
    {'stop': stop_existing, 'prepare': prepare, 'submit': submit_new}[args.stage]()
