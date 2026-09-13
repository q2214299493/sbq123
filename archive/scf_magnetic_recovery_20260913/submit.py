"""Prepare/submit one reviewed magnetic-seed diagnostic through canonical tools."""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from pymatgen.io.vasp.inputs import Incar
from pymatgen.io.vasp.outputs import Outcar

from archive.scf_near_linear_20260913 import execute as previous

prior = previous.prior
ROOT = prior.ROOT
OLD = previous.NEW
NEW = prior.BASE / 'h_migration_int06_mid_scf_magnetic_seed_20260913'
REVIEW = ROOT / 'docs/reviews/scf_magnetic_recovery_20260913'
REMOTE = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/' + NEW.name


def prepare():
    if NEW.exists():
        raise RuntimeError('Package exists; inspect state before retrying.')
    comparison = prior.load_json_object(REVIEW / 'comparison.json')
    for binding in comparison['source_bindings']:
        assert prior.sha256_file(Path(binding['path'])) == binding['sha256']
    a, b = Incar.from_file(OLD / 'INCAR'), Incar.from_file(REVIEW / 'INCAR.recommended')
    delta = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    assert delta == ['MAGMOM'], delta
    source = prior.BASE / 'h_migration_int06_mid_scf_normal_20260912/completed_20260912/OUTCAR'
    assert np.array_equal(b['MAGMOM'], [m['tot'] for m in Outcar(source).magnetization])
    scheduler = prior.query_lsf_job('9754301', stage='diagnostic_static')
    assert scheduler['status'] == 'DONE', scheduler['status']
    geometry = prior.load_json_object(OLD / 'execution_gate_decision.json')['EVIDENCE']['source_bindings']['geometry']
    assert prior.sha256_file(Path(geometry['path'])) == geometry['sha256']
    hashes = prior.load_json_object(OLD / 'submission_preflight.json')['files']
    for name, digest in hashes.items():
        assert prior.sha256_file(OLD / name) == digest, name
    NEW.mkdir()
    for name in ('POSCAR', 'KPOINTS', 'POTCAR.spec', 'script.lsf'):
        shutil.copyfile(OLD / name, NEW / name)
    shutil.copyfile(REVIEW / 'INCAR.recommended', NEW / 'INCAR')
    prior.write_json(NEW / 'source_scheduler_terminal.json', scheduler)
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
                      'only_changed': delta, 'bundle_sha256': report['bundle_sha256']}))


def submit():
    if (NEW / 'submission_record.json').exists() or (NEW / 'submission_attempt.json').exists():
        raise RuntimeError('Submission evidence exists; inspect without repeating.')
    auth = prior.load_json_object(NEW / 'user_execution_authorization.json')
    print(json.dumps(prior.submit(NEW, NEW / 'execution_gate_decision.json',
        'sunboquan-codex', REMOTE, auth['potcar']['source'], auth['potcar']['sha256'],
        'SUBMIT_DIAGNOSTIC_VASP')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'submit'])
    args = parser.parse_args()
    {'prepare': prepare, 'submit': submit}[args.stage]()
