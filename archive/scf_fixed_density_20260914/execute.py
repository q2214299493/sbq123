"""One authorized non-selfconsistent diagnostic via existing gate/executor."""
import argparse
import json
import shutil
from pathlib import Path

from pymatgen.io.vasp.inputs import Incar

from archive.scf_magnetic_recovery_20260913 import submit as previous

prior = previous.prior
ROOT = prior.ROOT
OLD = previous.NEW
NEW = prior.BASE / 'h_migration_int06_mid_fixed_density_20260914'
REVIEW = ROOT / 'docs/reviews/scf_fixed_density_20260914'
REMOTE = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/' + NEW.name


def prepare():
    if NEW.exists():
        raise RuntimeError('Package exists: inspect rather than repeat.')
    review = prior.load_json_object(REVIEW / 'input_review.json')
    assert prior.sha256_file(REVIEW / 'INCAR.recommended') == review['candidate_sha256']
    for name, digest in review['source_hashes'].items():
        assert prior.sha256_file(OLD / name) == digest, name
    a, b = Incar.from_file(OLD / 'INCAR'), Incar.from_file(REVIEW / 'INCAR.recommended')
    delta = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    assert delta == ['ICHARG', 'ISTART', 'LMAXMIX'], delta
    assert (b['ICHARG'], b['ISTART'], b['LMAXMIX']) == (12, 0, 4)
    scheduler = prior.query_lsf_job('9754808', stage='diagnostic_static')
    assert scheduler['status'] == 'DONE', scheduler['status']
    geometry = prior.load_json_object(OLD / 'execution_gate_decision.json')['EVIDENCE']['source_bindings']['geometry']
    assert prior.sha256_file(Path(geometry['path'])) == geometry['sha256']
    NEW.mkdir()
    for name in ('POSCAR', 'KPOINTS', 'POTCAR.spec', 'script.lsf'):
        shutil.copyfile(OLD / name, NEW / name)
    shutil.copyfile(REVIEW / 'INCAR.recommended', NEW / 'INCAR')
    prior.write_json(NEW / 'source_scheduler_terminal.json', scheduler)
    prior.write_json(NEW / 'diagnostic_scope.json', {
        'purpose': 'fixed_atomic_density_orbital_diagnostic', 'ICHARG': 12,
        'self_consistent': False, 'allowed_as_training_label': False,
        'allowed_as_barrier_energy': False, 'allowed_as_dimer_restart': False,
        'source_review': str(REVIEW / 'input_review.json'),
        'source_review_sha256': prior.sha256_file(REVIEW / 'input_review.json')})
    assert prior.analyze(NEW, prior.THRESHOLDS, reaction_indices=[49])['status'] == 'NO_OUTPUT'
    report = prior.preflight(NEW, 'diagnostic_static')
    assert report['passed'], report['errors']
    old_auth = prior.load_json_object(OLD / 'user_execution_authorization.json')
    auth = {'action': 'SUBMIT_DIAGNOSTIC_VASP', 'calculation_kind': 'diagnostic_static',
            'target': {'server_alias': 'sunboquan-codex', 'remote_dir': REMOTE},
            'workdir_identity': prior.workdir_identity(NEW),
            'bundle_sha256': report['bundle_sha256'], 'potcar': old_auth['potcar']}
    prior.REQUEST = REVIEW / 'user_submission_authorization.md'
    _, gate = prior.make_gate(NEW, {'geometry': Path(geometry['path']),
        'analysis': NEW / 'neb_analysis.json', 'thresholds': prior.THRESHOLDS,
        'preflight': NEW / 'submission_preflight.json'}, auth, path_reviewed=True)
    print(json.dumps({'preflight': report['passed'], 'allowed': gate['ALLOWED_ACTIONS'],
                      'changed_tags': delta}))


def submit():
    previous.NEW = NEW
    previous.REMOTE = REMOTE
    previous.submit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'submit'])
    args = parser.parse_args()
    {'prepare': prepare, 'submit': submit}[args.stage]()
