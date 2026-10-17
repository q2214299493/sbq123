"""Review returned predicted structures; never accepts DFT results or submits jobs."""
import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa: E402
from scripts.aqcat25_handoff import validate_handoff  # noqa: E402
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar  # noqa: E402
from scripts.adsorption.build_fe110_care_isomers import connectivity  # noqa: E402
from scripts.workflow_geometry import minimum_image_delta_xy, pbc_xy_distance  # noqa: E402

PACKAGE = ROOT / 'calculations/fe110_c2_adsorption_06_10_20261012/matris_direct_v1'
NAMES = ['06_C', '07_B', '07_C', '08_A', '09_A', '10_A']


def main():
    receipt = load_json_object(PACKAGE / 'returned_v1/direct_batch_exit_record.json')
    if receipt['exit_code'] != 0 or receipt['completed_candidates'] != NAMES:
        raise ValueError('batch not fully completed')
    request = load_json_object(PACKAGE / 'direct_request.json')
    baseline = load_json_object(PACKAGE / 'trial_review.json')
    rows = []
    for name in NAMES:
        output = PACKAGE / 'returned_v1' / name / 'output' / ('job_' + request['run_id'])
        handoff = validate_handoff(output / 'gpu_result_manifest.json')
        if handoff['source_handoff']['sha256'] != sha256_file(PACKAGE / name / 'handoff.json'):
            raise ValueError('returned source differs from submitted input')
        if handoff['producer']['checkpoint_sha256'] != request['checkpoint_sha256']:
            raise ValueError('returned wrong model')
        binding = load_json_object(output / 'execution_device.json')
        if not binding['model_device'].startswith('cuda') or binding['physical_gpu_uuid'] != request['gpu_uuid']:
            raise ValueError('wrong execution device')
        initial = read_poscar(PACKAGE / name / 'POSCAR')
        final = read_poscar(output / 'POSCAR')
        symbols = expanded_symbols(final)
        if symbols != expanded_symbols(initial) or initial.flags != final.flags:
            raise ValueError('atom order or flags changed')
        if not np.allclose(initial.cell, final.cell, atol=1e-10, rtol=0):
            raise ValueError('cell changed')
        delta = minimum_image_delta_xy(final.frac - initial.frac) @ final.cell
        if max(np.linalg.norm(delta[:18], axis=1)) > 1e-8:
            raise ValueError('fixed layer changed')
        ads = list(range(45, len(symbols)))
        cart = final.frac @ final.cell
        initial_graph = connectivity(initial, ads)
        final_graph = connectivity(final, ads)
        nearest = {symbols[i] + str(i): min((pbc_xy_distance(final.cell, cart[i], cart[j]), j)
                                          for j in range(45)) for i in ads}
        bonds = {tuple(sorted((ads[a], ads[b]))) for a, b in final_graph}
        contacts = [(pbc_xy_distance(final.cell, cart[i], cart[j]), i, j) for i in ads
                    for j in range(len(symbols)) if i != j and not (j in ads and j < i)
                    and tuple(sorted((i, j))) not in bonds]
        carbon_oxygen = {f'{i}-{j}': pbc_xy_distance(final.cell, cart[i], cart[j])
                         for i in ads for j in ads if symbols[i] == 'C' and symbols[j] == 'O'}
        result = load_json_object(output / 'result.json')
        producer = load_json_object(output / 'producer_exit_record.json')
        elapsed = (datetime.fromisoformat(producer['finished_utc']) -
                   datetime.fromisoformat(producer['started_utc'])).total_seconds()
        original = next(r for r in baseline['samples'] if r['name'] == name)
        rows.append(dict(name=name, optimizer_converged=result['converged'],
            optimizer_steps=result['optimizer_steps'], ML_fmax_eV_A=result['movable_fmax_eV_per_A'],
            predicted_energy_eV=result['energy_eV'], producer_elapsed_seconds=elapsed,
            original_graph=initial_graph, predicted_graph=final_graph,
            graph_preserved=initial_graph == final_graph, carbon_oxygen_distances_A=carbon_oxygen,
            nearest_fe_A_and_zero_based_index=nearest, minimum_nonbonded_A_and_indices=min(contacts),
            fixed18_max_displacement_A=float(max(np.linalg.norm(delta[:18], axis=1))),
            all_invariants_pass=all(result['structure_invariants'].values()),
            geometry_verdict='original_graph_preserved_no_emergency_overlap'
                if initial_graph == final_graph and min(v[0] for v in nearest.values()) >= .8
                else 'predicted_chemistry_requires_review',
            source_structure_sha256=sha256_file(PACKAGE / name / 'POSCAR'),
            result_sha256=sha256_file(output / 'result.json'),
            structure_sha256=sha256_file(output / 'POSCAR'),
            gpu_handoff_sha256=sha256_file(output / 'gpu_result_manifest.json'),
            aqcat_same_seed_baseline=original['aqcat_baseline'],
            reportable_DFT=False, vasp_speedup_established=False))
    elapsed = (datetime.fromisoformat(receipt['finished_at']) -
               datetime.fromisoformat(receipt['started_at'])).total_seconds()
    review = dict(run_id=request['run_id'], execution_mode='direct_no_scheduler', scheduler_job_id=None,
        batch_exit_record_sha256=sha256_file(PACKAGE / 'returned_v1/direct_batch_exit_record.json'),
        collection_archive_sha256=sha256_file(PACKAGE / 'collected_outputs_v1.tar.gz'),
        request_sha256=sha256_file(PACKAGE / 'direct_request.json'), model_checkpoint_sha256=request['checkpoint_sha256'],
        actual_gpu_uuid=request['gpu_uuid'], batch_elapsed_seconds=elapsed,
        completed=6, model_force_converged=sum(r['optimizer_converged'] for r in rows),
        graph_preserved=sum(r['graph_preserved'] for r in rows),
        scientific_acceptance=False, new_VASP_submitted=False, model_promoted=False, samples=rows)
    write_json_exclusive(PACKAGE / 'returned_review.json', review)
    with (PACKAGE / 'returned_summary.csv').open('x', encoding='utf-8', newline='') as f:
        fields = ['name', 'optimizer_converged', 'optimizer_steps', 'ML_fmax_eV_A', 'producer_elapsed_seconds',
                  'graph_preserved', 'geometry_verdict', 'predicted_energy_eV', 'vasp_speedup_established']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print('REVIEW', 'elapsed', elapsed, 'ML_converged', review['model_force_converged'],
          'graph_preserved', review['graph_preserved'])
    for row in rows:
        print(row['name'],row['optimizer_steps'],round(row['ML_fmax_eV_A'],6),row['geometry_verdict'],
              'AQCat_steps',row['aqcat_same_seed_baseline']['optimizer_steps'])


if __name__ == '__main__':
    main()
