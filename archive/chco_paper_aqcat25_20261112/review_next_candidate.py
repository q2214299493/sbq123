"""Build actual continuation provenance/geometry/image evidence; never approve.

An operator must inspect the saved image and numeric evidence before writing
the separate candidate review or preparing a DFT execution gate.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from ase.geometry import find_mic
from ase.io import read

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.matris_training_exclusions import geometry_fingerprint
from scripts.neb_agent import mz73_static
from scripts.neb_agent.paper_candidate_source import BINDING_KIND, resolve_continuation_source
from scripts.neb_agent.utils_structure import read_poscar


def ref(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha256_file(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, required=True)
    args = parser.parse_args()
    case = args.case_root.resolve(strict=True)
    state = load_json_object(case / 'paper_state.v2.after_training14292.json')
    candidate = case / 'return_14304/output/predicted_candidate.vasp'
    request = case / 'continuation_r001/request.json'
    report_path = case / 'return_14304/output/candidate_report.json'
    report = load_json_object(report_path)
    fingerprint = geometry_fingerprint(read_poscar(candidate))
    if sha256_file(candidate) in state['protocol']['held_out_structure_sha256'] or fingerprint in state['protocol']['held_out_geometry_sha256']:
        raise ValueError('candidate overlaps protected geometry/structure')
    destination = case / 'candidate_r001_work_review'
    destination.mkdir(exist_ok=False)
    binding = {'document_kind': BINDING_KIND, 'protocol_sha256': state['protocol_sha256'],
        'continuation_request': ref(request), 'continuation_report': ref(report_path), 'candidate': ref(candidate),
        'source_map': load_json_object(case / 'continuation_r001/source_map_seed.json')['source_map']}
    binding_path = destination / 'continuation_source_binding.json'
    write_json_exclusive(binding_path, binding)
    contract_path = case.parent / 'review_ready_v2/reaction_contract.json'
    contract = mz73_static.load_reviewed_case_contract(contract_path, workdir_name='paper_chco_aqcat25_ft512_20261112_r001_label')
    resolve_continuation_source(binding_path, binding_sha256=sha256_file(binding_path), candidate_path=candidate,
        initial_structure_path=case / 'initial_search/IS.vasp', expected_protocol_sha256=state['protocol_sha256'], contract=contract)
    names = {'IS': case / 'initial_search/IS.vasp', 'previous': case / 'return_13883/output/predicted_candidate.vasp',
             'r001 candidate': candidate, 'FS': case / 'initial_search/FS_symmetry_mapped.vasp'}
    atoms = {name: read(path, format='vasp') for name, path in names.items()}
    reference = atoms['IS']
    rows = []
    for name, frame in atoms.items():
        distances = frame.get_all_distances(mic=True)
        np.fill_diagonal(distances, np.inf)
        rows.append({'state': name, 'CC_A': float(distances[45, 46]), 'CH_A': float(distances[45, 48]),
            'CO_A': float(distances[46, 47]), 'minimum_pair_A': float(distances.min()),
            'fixed_shift_A': float(np.linalg.norm(frame.positions[:18] - reference.positions[:18], axis=1).max()),
            'same_cell': bool(np.array_equal(frame.cell.array, reference.cell.array)),
            'nearest_Fe': {str(i): {'index': int(np.argmin(distances[i, :45])), 'distance_A': float(np.min(distances[i, :45])),
                    'height_above_highest_Fe_A': float(frame.positions[i, 2] - frame.positions[:45, 2].max())} for i in range(45, 49)}})
    trajectory = read(case / 'return_14304/output/aqcat25_ba_sella.traj', index=':')
    last = trajectory[-1]
    if not np.allclose(last.positions, atoms['r001 candidate'].positions, atol=1e-12, rtol=0):
        raise ValueError('returned last frame differs from candidate POSCAR')
    residual = float(np.linalg.norm(last.get_forces(apply_constraint=False)[18:], axis=1).max())
    if abs(residual - report['predicted_movable_fmax_eV_per_A']) > 1e-10:
        raise ValueError('cached force residual differs from worker report')
    minimum, fixed_shift, adjacent_mic, adjacent_raw = float('inf'), 0.0, 0.0, 0.0
    for index, frame in enumerate(trajectory):
        distances = frame.get_all_distances(mic=True)
        np.fill_diagonal(distances, np.inf)
        minimum = min(minimum, float(distances.min()))
        fixed_shift = max(fixed_shift, float(np.linalg.norm(frame.positions[:18] - reference.positions[:18], axis=1).max()))
        if index:
            delta = frame.positions - trajectory[index-1].positions
            _, length = find_mic(delta, frame.cell, frame.pbc)
            adjacent_mic = max(adjacent_mic, float(length.max()))
            adjacent_raw = max(adjacent_raw, float(np.linalg.norm(delta, axis=1).max()))
    evidence = {'result_class': 'prediction_for_pending_work_geometry_review_only', 'source_candidate_sha256': sha256_file(candidate),
        'geometry_sha256': fingerprint, 'rows': rows, 'protected_structure_overlap': False, 'protected_geometry_overlap': False,
        'protected_geometry_count': len(state['protocol']['held_out_geometry_sha256']),
        'BA_trajectory': {'frames': len(trajectory), 'minimum_pair_A': minimum, 'maximum_fixed_shift_A': fixed_shift,
                         'maximum_adjacent_atom_step_MIC_A': adjacent_mic, 'maximum_adjacent_atom_step_raw_A': adjacent_raw},
        'cached_ML_movable_fmax_eV_per_A': residual, 'DFT_accuracy_verified': False, 'scientifically_accepted_TS': False}
    write_json_exclusive(destination / 'geometry_evidence.json', evidence)
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    colors = ['#b9bdc4'] * 45 + ['#222222', '#222222', '#d43831', '#ffffff']
    sizes = [70] * 45 + [110, 110, 110, 65]
    for col, name in enumerate(('previous', 'r001 candidate')):
        positions = atoms[name].positions
        for row, (u, v, view) in enumerate(((0, 1, 'top'), (0, 2, 'side'))):
            ax = axes[row, col]
            ax.scatter(positions[:, u], positions[:, v], s=sizes, c=colors, edgecolors='#333333', linewidths=.5)
            for i in range(45, 49):
                ax.annotate(atoms[name][i].symbol + str(i), (positions[i, u], positions[i, v]), xytext=(4, 6), textcoords='offset points')
            for a, b in ((45, 46), (45, 48), (46, 47)):
                ax.plot(positions[[a, b], u], positions[[a, b], v], color='#4676b6', linewidth=1)
            ax.set_aspect('equal')
            ax.set_title(name + ' / ' + view)
            ax.set_xlabel(('x','y','z')[u] + ' (angstrom)')
            ax.set_ylabel(('x','y','z')[v] + ' (angstrom)')
    fig.suptitle('AQCat25 continuation: predicted geometries for DFT force diagnosis only')
    image = destination / 'candidate_geometry_review.png'
    fig.savefig(image, dpi=160)
    plt.close(fig)
    print({'binding': ref(binding_path), 'geometry': ref(destination / 'geometry_evidence.json'),
           'image': ref(image), 'review_written': False, 'ML_fmax': residual, 'trajectory': evidence['BA_trajectory']})


if __name__ == '__main__':
    main()
