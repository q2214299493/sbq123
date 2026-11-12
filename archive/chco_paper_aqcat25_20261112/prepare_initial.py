"""Prepare the reviewed first ML-search bundle; never submit work."""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]

CASE = ROOT / 'calculations/fe110_ch_co_to_chco_ts_20261109/paper_aqcat25_ft512_20261112_v1'
DEST = CASE / 'initial_search'
REMOTE = '/home/sbq/sbq/chco_paper_aqcat25_ft512_20261112_v1/initial_search'


def main():
    sys.path.insert(0, str(ROOT))
    from ase.io import read
    from scripts.artifact_io import sha256_file, write_json
    from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff

    if (DEST / 'request.json').exists():
        raise FileExistsError('request already exists; inspect rather than repeat preparation')
    frozen_sources = Path(__file__).parent / 'runtime_sources'
    sources = {
        'initial_candidate.py': ROOT / 'archive/chco_paper_aqcat25_20261112/initial_candidate.py',
        'aqcat_ts_pilot.py': frozen_sources / 'aqcat_ts_pilot.py',
        'mlip_same_structure_benchmark.py': frozen_sources / 'mlip_same_structure_benchmark.py',
        'artifact_io.py': frozen_sources / 'artifact_io.py',
    }
    for name, source in sources.items():
        target = DEST / name
        if target.exists():
            if sha256_file(target) != sha256_file(source):
                raise FileExistsError('conflicting staged source: ' + name)
        else:
            shutil.copyfile(source, target)
    contract = json.loads((CASE / 'reference_checks/reaction_contract.json').read_bytes())
    model = json.loads((CASE / 'frozen_model.json').read_bytes())
    old = ROOT / 'calculations/fe110_ch_co_to_chco_ts_20261109/gpu_20261110_v1/package/request.json'
    guards = json.loads(old.read_bytes())['geometry_guards']
    request = {
        'schema_version': 1,
        'document_kind': 'paper_sequential_initial_ML_search',
        'initial': {'path': REMOTE + '/IS.vasp', 'sha256': sha256_file(DEST / 'IS.vasp')},
        'final': {'path': REMOTE + '/FS_symmetry_mapped.vasp', 'sha256': sha256_file(DEST / 'FS_symmetry_mapped.vasp')},
        'checkpoint': {'path': model['checkpoint_path'], 'sha256': model['checkpoint_sha256']},
        'source_files': [{'path': REMOTE + '/' + name, 'sha256': sha256_file(DEST / name)} for name in sources],
        'reaction': {
            'bonds': [[45, 46, 'form']], 'adsorbate_indices': [45, 46, 47, 48],
            'monitor_pairs': {'CC': [45, 46], 'CH': [45, 48], 'CO': [46, 47]},
            'contract_sha256': contract['contract_sha256'],
            'atom_map_sha256': contract['atom_map_sha256'],
            'compatibility_sha256': contract['compatibility_sha256'],
        },
        'fixed_indices_zero_based': list(range(18)),
        'geometry': {
            'minimum_pair_distance_A': guards['minimum_pair_distance_A'],
            'preserved_bonds': [{
                'name': row['name'], 'atoms': row['atoms_zero_based'],
                'minimum_A': row['hard_minimum_A'], 'maximum_A': row['hard_maximum_A'],
                'soft_minimum_A': row['minimum_A'], 'soft_maximum_A': row['maximum_A'],
            } for row in guards['preserved_bonds']],
        },
        'geometry_guard_source': {'path': str(old), 'sha256': sha256_file(old)},
        'algorithm': {'idpp_images': 10, 'idpp_optimizer': 'LBFGS', 'idpp_fmax_eV_per_A': 0.01,
                      'idpp_steps': 1000, 'candidate_selection': 'highest_energy_internal_image',
                      'ba_sella_fmax_eV_per_A': 0.01, 'ba_sella_minimum_steps': 10,
                      'ba_sella_maximum_steps': 1000},
        'resource_scope': {'partition': 'gpu', 'hostname': 'MZ73', 'gpus': 1, 'cpus': 4,
                           'memory': '16G', 'walltime': '00:10:00', 'no_requeue': True},
        'authorization_scope': 'user_requested_CH_CO_test_with_existing_AQCat25_initial_search_only',
        'restrictions': {'DFT_performed': False, 'training_performed': False, 'submit_vasp': False,
                         'production_model_promotion': False, 'automatic_retry': False},
    }
    request['source_files'].append({
        'path': '/home/sbq/sbq/ml_ts_acceleration/src/arkimede/arkimede/workflow/calculations.py',
        'sha256': 'dea0689cd58eb7726dac7fdc00206a5156fb8929a82f4d01bfd43fd950265139',
    })
    write_json(DEST / 'request.json', request)
    request_sha = sha256_file(DEST / 'request.json')
    atoms = read(DEST / 'IS.vasp', format='vasp')
    order = atom_order_sha256(atoms.get_chemical_symbols())

    def reference(name):
        return {'path': name, 'sha256': sha256_file(DEST / name), 'format': 'vasp_poscar',
                'atom_count': 49, 'atom_order_sha256': order}

    handoff = {
        'schema_version': 2, 'direction': 'work_to_gpu',
        'handoff_id': 'chco-paper-aqcat25-ft512-initial-20261112', 'workflow_kind': 'transition_state',
        'source_workflow_sha256': request_sha, 'candidate_structure': reference('IS.vasp'),
        'compatibility': {'branch': 'true_fe110_5layer_5x5x1', 'sha256': contract['compatibility_sha256'],
                          'slab_model': 'fe45_bottom18_fixed', 'facet': 'Fe(110)'},
        'model': {'identifier': model['identifier'], 'checkpoint_sha256': model['checkpoint_sha256'],
                  'fmax_eV_per_A': 0.01, 'max_steps': 1000},
        'selective_dynamics': {'fixed_atom_indices_1based': list(range(1, 19)), 'free_atom_count': 31},
        'transition_state': {
            'normalized_reaction_contract_sha256': contract['contract_sha256'],
            'atom_map_sha256': contract['atom_map_sha256'], 'initial_structure': reference('IS.vasp'),
            'waypoint_structures': [], 'final_structure': reference('FS_symmetry_mapped.vasp'),
            'indexed_bond_changes': [{'atoms_1based': [46, 47], 'change': 'form'}],
        },
        'restrictions': {'predicted_candidate_only': True, 'submit_vasp': False,
                         'scientific_acceptance': False, 'direct_gpu_to_vasp_handoff': False},
    }
    write_json(DEST / 'work_to_gpu.handoff.json', handoff)
    validate_handoff(DEST / 'work_to_gpu.handoff.json')
    template = (Path(__file__).parent / 'initial_job.template.sh').read_text(encoding='utf-8')
    (DEST / 'job.sh').write_text(template.replace('__REQUEST_SHA__', request_sha), encoding='utf-8', newline='\n')
    manifest = {path.name: sha256_file(path) for path in DEST.iterdir() if path.is_file()}
    write_json(DEST / 'input_manifest.json', manifest)
    state = json.loads((CASE / 'preparation_state.json').read_bytes())
    state.update(status='initial_search_prepared_not_submitted',
                 initial_search_request_sha256=request_sha, remote_initial_search_root=REMOTE)
    write_json(CASE / 'preparation_state.json', state)
    print(json.dumps({'local_root': str(DEST), 'remote_root': REMOTE,
                      'request_sha256': request_sha, 'handoff_validator': 'passed',
                      'file_count': len(manifest), 'stage': 'initial_search_prepared_not_submitted'}))


if __name__ == '__main__':
    main()
