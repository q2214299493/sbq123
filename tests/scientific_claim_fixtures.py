"""Synthetic files interpreted by the maintained scientific owners, not stubs."""
from pathlib import Path

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.utils_structure import write_poscar
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review
from scripts.ts_validation.analyze_vfa import analyze_vfa
from scripts.ts_validation.connectivity import analyze_bidirectional_connectivity
from scripts.ts_validation.prepare_vfa_from_ts_image import prepare_vfa_handoff
from test_ts_validation import _completed_relaxation, _connectivity_structure


def neb_vfa_case(root: Path, contract: dict, *, custom_review: bool = False) -> dict:
    root.mkdir(parents=True)
    thresholds = Path(__file__).resolve().parents[1] / 'configs/neb_agent/default_thresholds.yaml'
    contract_path = write_json(root / 'reaction.json', contract)
    neb = root / 'neb'
    neb.mkdir()
    (neb / 'INCAR').write_text('IMAGES=13; NELM=60; NSW=100; EDIFF=1e-5; EDIFFG=-0.02; LCLIMB=.TRUE.\n')
    for index, distance in enumerate(np.linspace(1.2, 3.5, 15)):
        image = neb / f'{index:02}'
        image.mkdir()
        for name in ('POSCAR', 'CONTCAR'):
            write_poscar(image / name, _connectivity_structure(distance))
        energy = -9 - abs(index - 7) / 7
        (image / 'OSZICAR').write_text(f'RMM: 5 {energy} -1e-7 -1e-7 100 1e-4\n1 F= {energy} E0= {energy} d E= -1e-7\n')
        (image / 'OUTCAR').write_text('NEB: forces: par spring, perp REAL, dneb 0 0.01 0\n'
                                    'reached required accuracy\nGeneral timing and accounting informations for this job\n')
    hashes = {key: contract[key] for key in ('contract_sha256', 'atom_map_sha256', 'compatibility_sha256')}
    generation = write_json(neb / 'path_generation_report.json', {
        **hashes, 'fingerprint_id': build_fingerprint(contract)['fingerprint_id']})
    dist, movie = neb / 'dist.dat', neb / 'movie.xyz'
    dist.write_text('synthetic reviewed distances\n')
    movie.write_text('synthetic reviewed movie\n')
    review = write_json(root / 'custom_path_review.json' if custom_review else neb / 'path_review.json', {
        'status': 'accepted', 'reviewer': 'test', 'reviewed_at': '2026-01-01',
        'dist_file': str(dist), 'dist_sha256': sha256_file(dist),
        'nebmovie_file': str(movie), 'nebmovie_sha256': sha256_file(movie),
        'path_generation_sha256': sha256_file(generation),
    })
    geometry = diagnose(neb, ['1', '2'], [], thresholds, reaction_pairs=contract['broken_bonds'])
    assert geometry['status'] == 'PASS', geometry
    analysis = analyze(neb, thresholds, contract['reaction_atoms'])
    assert analysis['technically_converged'] and analysis['internal_maximum']
    analysis.update(**hashes, geometry_validated=True, path_review_source=str(review),
                    path_binding_valid=validate_path_binding(neb, contract)['valid'],
                    path_reviewed=validate_path_review(review, generation)[0])
    saddle_analysis = write_json(neb / 'neb_analysis.json', analysis)
    vfa = root / 'vfa'
    prepare_vfa_handoff(neb / '07', vfa, [1, 2], contract, saddle_analysis, False)
    scope = load_json_object(vfa / 'vfa_scope_review.json')
    scope.update(status='accepted_for_partial_hessian', reviewer='test', reviewed_at='2026-01-01')
    write_json(vfa / 'vfa_scope_review.json', scope)
    (vfa / 'OUTCAR').write_text('1 f/i= 15 THz 500 cm-1\n'
                              '1 0 0 0 0 0 0\n2 0 0 0 0.7 0 0\n3 0 0 0 -0.7 0 0\n'
                              'General timing and accounting informations for this job\n')
    plus, minus = root / 'plus', root / 'minus'
    plus_displacement, minus_displacement = root / 'plus.POSCAR', root / 'minus.POSCAR'
    plus_scheduler = _completed_relaxation(plus, plus_displacement, _connectivity_structure(1.25), 'scheduler_connectivity_plus')
    minus_scheduler = _completed_relaxation(minus, minus_displacement, _connectivity_structure(3.45), 'scheduler_connectivity_minus')
    connectivity = vfa / 'connectivity.json'
    report = analyze_bidirectional_connectivity(
        contract_path=contract_path, initial_path=neb / '00/POSCAR', final_path=neb / '14/POSCAR',
        saddle_path=neb / '07/CONTCAR', frequency_outcar=vfa / 'OUTCAR',
        positive_run=plus, positive_displacement=plus_displacement, positive_scheduler=plus_scheduler,
        negative_run=minus, negative_displacement=minus_displacement, negative_scheduler=minus_scheduler,
        output=connectivity,
    )
    assert report['grade_a_connectivity_eligible'], report
    vfa_review = write_json(vfa / 'review.json', {
        **hashes, 'status': 'accepted', 'source_method': 'ci_neb',
        'validation_calculation_id': 'calc_vfa', 'source_saddle_calculation_id': 'calc_ts',
        'source_job_record_id': 'job_ts_source', 'frequency_output_file_id': 'vfa_outcar',
        'positive_displacement_file_id': 'mode_plus', 'negative_displacement_file_id': 'mode_minus',
        'connectivity_report_file_id': 'connectivity_report',
        'positive_connectivity_job_record_id': 'job_connectivity_plus',
        'negative_connectivity_job_record_id': 'job_connectivity_minus',
        'connectivity_report': str(connectivity), 'connectivity_report_sha256': sha256_file(connectivity),
        'vfa_handoff': str(vfa / 'vfa_handoff.json'), 'vfa_handoff_sha256': sha256_file(vfa / 'vfa_handoff.json'),
        'mode_assignment': 'accepted', 'geometry_status': 'pass',
        'reviewer': 'test', 'reviewed_at': '2026-01-01',
    })
    payload = analyze_vfa(vfa, contract, vfa_review, {
        'meaningful_imaginary_frequency_min_cm1': 50.0, 'additional_soft_mode_abs_max_cm1': 30.0})
    assert payload['grade'] == 'A', payload
    return {'vfa': vfa, 'neb': neb, 'plus': plus, 'minus': minus,
            'contract_path': contract_path, 'payload': payload, 'connectivity': connectivity}
