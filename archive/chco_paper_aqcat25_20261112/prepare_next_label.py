"""Reuse verified Fe(110) static parameters for the reviewed next exact point.

Only the POSCAR and paper request change. No scientific parameter tuning,
submission, result overwriting, model promotion or TS acceptance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic, write_json_exclusive
from scripts.matris_training_exclusions import geometry_fingerprint
from scripts.neb_agent.mz73_static import load_mz73_static_backend
from scripts.neb_agent.mz73_timebudget import NEXT_LEAF, TIMEOUT_LEAF, validate_budget_authorization
from scripts.neb_agent.mz73_continuation import NAMES, validate_request as validate_continuation_request
from scripts.neb_agent.utils_structure import read_poscar
from scripts.ts_strategy_engine import paper_sequential as paper


def ref(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256_file(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, required=True)
    for name in ('state', 'candidate', 'review-directory'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    case = args.case_root.resolve(strict=True)
    state_path = args.state or case / 'paper_state.v2.after_training14292.json'
    state = load_json_object(state_path)
    paper.validate_state(state)
    index = state['completed_label_count']
    current = case / ('paper_state.v2.json' if index == 1 else 'paper_state.v3.json')
    if sha256_file(current) != sha256_file(state_path):
        raise ValueError('current state changed after verified training')
    candidate = args.candidate or case / 'return_14304/output/predicted_candidate.vasp'
    review_dir = args.review_directory or case / f'candidate_r{index:03d}_work_review'
    review = load_json_object(review_dir / 'candidate_work_review.json')
    if (review['decision'] != 'accepted_for_exact_structure_DFT_force_diagnosis_only'
            or review['candidate_structure_sha256'] != sha256_file(candidate)
            or review['geometry_evidence_sha256'] != sha256_file(review_dir / 'geometry_evidence.json')
            or review['image_sha256'] != sha256_file(review_dir / 'candidate_geometry_review.png')):
        raise ValueError('missing actual bound geometry/image review')
    if geometry_fingerprint(read_poscar(candidate)) in state['protocol']['held_out_geometry_sha256']:
        raise ValueError('protected geometry cannot enter the next DFT label')
    updated = paper.prepare_dft_evaluation(state, candidate_structure_sha256=sha256_file(candidate),
                                           search_checkpoint_sha256=state['search_checkpoint']['sha256'])
    old = case / 'labels' / TIMEOUT_LEAF
    source_label = load_json_object(old / 'force_label_review_v2/paper_force_label.json')
    original_sources = source_label['scheduler_evidence']['source_files']
    names = ('INCAR', 'KPOINTS', 'POTCAR.spec', 'POTCAR')
    for name in names:
        if sha256_file(old / name) != original_sources[name]['sha256']:
            raise ValueError('verified original DFT input changed: ' + name)
    leaf = NEXT_LEAF if index == 1 else f'paper_chco_aqcat25_ft512_20261112_r{index:03d}_label'
    if index != 1 and leaf not in NAMES:
        raise ValueError('next point is outside the authorized sequential ceiling')
    target = case / 'labels' / leaf
    target.mkdir(exist_ok=False)
    (target / 'POSCAR').write_bytes(candidate.read_bytes())
    for name in names:
        with (target / name).open('xb') as stream:
            stream.write((old / name).read_bytes())
    snapshot = (case / 'paper_state.v2.after_r001_preparation.json' if index == 1 else
                case / f'continuation_force003_20261113/state.after_r{index:03d}_preparation.json')
    write_json_exclusive(snapshot, updated)
    request = {**updated['evaluations'][-1]['request'], 'execution_budget_authorization':
               ref(case / ('execution_budget_authorization_60min.json' if index == 1 else 'continuation_force003_20261113/authorization.json'))}
    if index != 1:
        request['continuation_state'] = ref(snapshot)
    write_json_exclusive(target / 'paper_DFT_request.json', request)
    backend = load_mz73_static_backend(leaf)
    if index == 1:
        validate_budget_authorization(target, request, backend)
    else:
        validate_continuation_request(target, request, backend)
    write_json_exclusive(target / 'parameter_reuse_provenance.json', {
        'document_kind': 'verified_static_force_label_parameter_reuse', 'source_label': ref(old / 'force_label_review_v2/paper_force_label.json'),
        'source_inputs': {name: ref(old / name) for name in names},
        'target_inputs': {name: ref(target / name) for name in names},
        'new_candidate': ref(candidate), 'work_review': ref(review_dir / 'candidate_work_review.json'),
        'initial_state': ref(state_path), 'prepared_state': ref(snapshot),
        'scientific_parameters_changed': False, 'submitted': False})
    if sha256_file(current) != sha256_file(state_path):
        raise ValueError('active state changed during preparation')
    write_json_atomic(current, updated)
    print({'prepared_label': str(target), 'state': ref(snapshot), 'status': updated['status'],
           'reserved_DFT_slots': updated['reserved_dft_slots'], 'submitted': False})


if __name__ == '__main__':
    main()
