"""One authorized near-linear SCF control, reusing canonical gate and executor."""
import argparse
import json
import shutil
from pathlib import Path

from pymatgen.io.vasp.inputs import Incar

from archive.scf_mixing_control_20260913 import execute as prior

ROOT = prior.ROOT
OLD = prior.NEW
NEW = prior.BASE / 'h_migration_int06_mid_scf_near_linear_20260913'
REVIEW = ROOT / 'docs/reviews/scf_near_linear_20260913'
REMOTE = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/' + NEW.name


def prepare():
    if NEW.exists():
        raise RuntimeError('Existing package: inspect receipts; never repeat preparation.')
    terminal = prior.query_lsf_job('9754110', stage='diagnostic_static')
    assert terminal['status'] == 'EXIT', terminal['status']
    before = Incar.from_file(OLD / 'INCAR')
    after = Incar.from_file(REVIEW / 'INCAR.recommended')
    delta = [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    assert delta == ['BMIX', 'BMIX_MAG'], delta
    assert after['BMIX'] == after['BMIX_MAG'] == 0.0001
    gate_old = prior.load_json_object(OLD / 'execution_gate_decision.json')
    geometry = gate_old['EVIDENCE']['source_bindings']['geometry']
    assert prior.sha256_file(Path(geometry['path'])) == geometry['sha256']
    old_identity = prior.load_json_object(OLD / 'mixing_control_identity.json')
    assert prior.sha256_file(OLD / 'INCAR') == old_identity['candidate_sha256']
    old_preflight = prior.load_json_object(OLD / 'submission_preflight.json')
    for name in ('POSCAR', 'KPOINTS', 'POTCAR.spec', 'script.lsf'):
        assert prior.sha256_file(OLD / name) == old_preflight['files'][name], name
    NEW.mkdir()
    for name in ('POSCAR', 'KPOINTS', 'POTCAR.spec', 'script.lsf'):
        shutil.copyfile(OLD / name, NEW / name)
    shutil.copyfile(REVIEW / 'INCAR.recommended', NEW / 'INCAR')
    prior.write_json(NEW / 'old_scheduler_terminal.json', terminal)
    analysis = prior.analyze(NEW, prior.THRESHOLDS, reaction_indices=[49])
    assert analysis['status'] == 'NO_OUTPUT'
    report = prior.preflight(NEW, 'diagnostic_static')
    assert report['passed'], report['errors']
    previous_auth = prior.load_json_object(OLD / 'user_execution_authorization.json')
    auth = {'action': 'SUBMIT_DIAGNOSTIC_VASP', 'calculation_kind': 'diagnostic_static',
            'target': {'server_alias': 'sunboquan-codex', 'remote_dir': REMOTE},
            'workdir_identity': prior.workdir_identity(NEW),
            'bundle_sha256': report['bundle_sha256'], 'potcar': previous_auth['potcar']}
    prior.REQUEST = REVIEW / 'user_request.md'
    prior.write_json(NEW / 'mixing_control_identity.json', {
        'source_job': '9754110', 'only_changed_incar_keys': delta,
        'source_sha256': {n: prior.sha256_file(OLD / n) for n in
                          ('INCAR', 'POSCAR', 'KPOINTS', 'POTCAR.spec', 'script.lsf')},
        'candidate_sha256': prior.sha256_file(NEW / 'INCAR'),
        'user_request_sha256': prior.sha256_file(prior.REQUEST)})
    _, decision = prior.make_gate(NEW, {'geometry': Path(geometry['path']),
        'analysis': NEW / 'neb_analysis.json', 'thresholds': prior.THRESHOLDS,
        'preflight': NEW / 'submission_preflight.json'}, auth, path_reviewed=True)
    print(json.dumps({'preflight': report['passed'], 'allowed': decision['ALLOWED_ACTIONS']}))


def submit():
    if (NEW / 'submission_record.json').exists() or (NEW / 'submission_attempt.json').exists():
        raise RuntimeError('Submission evidence exists; inspect before any retry.')
    auth = prior.load_json_object(NEW / 'user_execution_authorization.json')
    result = prior.submit(NEW, NEW / 'execution_gate_decision.json', 'sunboquan-codex',
                          REMOTE, auth['potcar']['source'], auth['potcar']['sha256'],
                          'SUBMIT_DIAGNOSTIC_VASP')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'submit'])
    args = parser.parse_args()
    {'prepare': prepare, 'submit': submit}[args.stage]()
