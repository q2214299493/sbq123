"""Prepare local review inputs for ten REICO labels and the two CHCO predictions."""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
from pathlib import Path

from ase.io import read
import yaml

from archive.fe110_c2_c4_joint_candidates_20261114.geometry import (
    distance_metrics, geometry_report, iron_maps, packed_pose,
)
from archive.fe110_joint_priority_20261117.analyze import BASE, MODEL, ROOT, SLAB, guard_hashes, load, save, sha, table
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.adsorption.reico_sampling import geometry_audit
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import DEFAULT_PROFILE, build_fe110_active_learning_force_label
from scripts.vasp_result_gate import read_incar_values
from . import run_pair


SOURCE = BASE / 'c2_c3_path_label_audit_20261118_v1/reviewed_v2'
AUDIT_SHA = '8b8796e051804f6dd9cf260d83d9d4eab05c1c7698dad09982f332d483b4e885'
PAIR_PREFLIGHT_SHA = '77eccabfb00f31d23eb0e9fe310c68a77e7eef670a225b323fcee74fe6824b56'
RUNTIME_REQUEST = BASE / 'force_diagnosis536_gpu_20261117_v4/packet/request.json'


def checked(path: Path, expected: str):
    if sha(path) != expected:
        raise ValueError(f'Reviewed source changed: {path}')


def copy_bound(source: Path, target: Path, expected: str):
    content = source.read_bytes()
    with target.open('xb') as stream:
        stream.write(content)
    checked(target, expected)


def prepare_pair(destination: Path):
    source = SOURCE / 'two_frame_local_preflight.json'
    checked(source, PAIR_PREFLIGHT_SHA)
    preflight = load(source)
    found = {row['id']: row['source_sha256'] for row in preflight['samples']}
    if found != run_pair.SAMPLES or preflight['frozen_checkpoint']['sha256'] != run_pair.MODEL_SHA256:
        raise ValueError('Two-frame scope changed')
    pair = destination / 'pair_inference'
    (pair / 'structures').mkdir(parents=True)
    for row in preflight['samples']:
        checked(Path(row['source_POSCAR']), row['source_sha256'])
        checked(Path(row['DFT']['source']), row['DFT']['sha256'])
        copy_bound(Path(row['source_POSCAR']), pair / 'structures' / (row['id'] + '.vasp'), row['source_sha256'])
    runner = Path(run_pair.__file__)
    runner_sha = sha(runner)
    copy_bound(runner, pair / 'run_pair.py', runner_sha)
    native_sources = {Path(item['path']).name: item['sha256'] for item in load(RUNTIME_REQUEST)['native_source_files']}
    request = pair / 'request.json'
    save(request, {'action': run_pair.ACTION, 'samples': run_pair.SAMPLES,
                   'checkpoint_sha256': run_pair.MODEL_SHA256, 'runner_sha256': runner_sha,
                   'native_source_sha256': native_sources, 'reference_614_request_sha256': sha(RUNTIME_REQUEST),
                   'local_DFT_reference_sha256': PAIR_PREFLIGHT_SHA, 'automatic_submission': False})
    return {'request_path': str(request), 'request_sha256': sha(request), 'runner_sha256': runner_sha,
            'model_path': str(MODEL), 'model_sha256': run_pair.MODEL_SHA256, 'host_bound_authorization_present': False}


def inspect_candidates(audit):
    joint = load(BASE / 'joint_priority614_20261117_v1/results_v2/joint_priority.json')
    rules_path = ROOT / 'configs/adsmind_lite/analysis_rules.yaml'
    rules = yaml.safe_load(rules_path.read_text(encoding='utf8'))
    floors = load(ROOT / 'configs/fe110_reico_pilot/geometry_v1.json')['pair_minimum_A']
    sampling = BASE / 'sampling93_v1'
    limits = load(sampling / 'validation_request.json')['limits']
    original = load(sampling / 'dft_inputs_v1/batch_request.json')['samples']
    previous_ids = {row['sample_id'] for row in original}
    previous_sha = {row['structure_sha256'] for row in original}
    prior_sources = {row['candidate_id']: row for row in joint['candidate_audit']}
    prior_frames = {row['sample_id']: row for row in joint['frames']}
    known_hashes = ({row['structure_sha256'] for row in joint['frames'] + joint['backup_labels']}
                   | {row['coordinate_file_sha256'] for row in audit['path_labels']})
    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    maps = iron_maps(slab, operations)
    rows = []
    for row in audit['selected'][:10]:
        sid = row['id']
        source = Path(row['coordinate_path'])
        checked(source, row['coordinate_sha256'])
        meta = prior_sources[sid]
        frame_info = Path(meta['frame_metadata_path'])
        checked(frame_info, meta['frame_metadata_sha256'])
        if load(frame_info)['structure_sha256'] != row['coordinate_sha256']:
            raise ValueError(f'Frame metadata mismatch for {sid}')
        atoms = read(source, format='vasp')
        source_seed = read(source.with_name('step_000.vasp'), format='vasp')
        geometry_check = geometry_audit(atoms, source_seed, floors, limits)
        pose = read_poscar(source)
        geometry = geometry_report(pose, slab, rules, floors)
        signatures = {scale: chemical_environment(atoms,rules['connectivity'],scale=float(scale))['joint_signature']
                      for scale in ('1.2', '1.25', '1.3')}
        if (geometry_check['failures'] or geometry['pair_guard_failures'] or not geometry['bottom18_only_fixed']
                or not geometry['same_clean_cell_within1e-6A'] or signatures != row['joint_by_scale']
                or row['protected_min_ads_RMSD_A'] <= .20 or not row['robust_gap_three_contact_scales']):
            raise ValueError(f'Candidate did not pass fresh geometry or protected-source checks: {sid}')
        nearest = row['closest_existing_catalog_label']
        known = prior_frames.get(nearest['reference_id'])
        if (sid in previous_ids or row['coordinate_sha256'] in previous_sha | known_hashes
                or row['possible_exact_label_match'] or nearest['full_RMSD_A'] <= 1e-7):
            raise ValueError(f'Existing input or force label must be reviewed before preparing {sid}')
        rows.append(({**row, 'geometry_check': geometry_check, 'fresh_geometry': geometry,
                      'validated_source_seed_sha256': sha(source.with_name('step_000.vasp')),
                      'old_280_input_match': False, 'exact_catalog_label_match': False,
                      'nearest_label_environment': known['coordination_by_element'] if known else None,
                      'nearest_label_signatures': known['joint_by_scale'] if known else None,
                      'contact_cutoff_sensitive': len(set(signatures.values())) > 1,
                      'fmax_DFT_eV_per_A': None}, pose))
    if len(rows) != 10 or len({row['family_id'] for row, _ in rows}) != 10:
        raise ValueError('A fresh review of the exact first ten is required')
    for (_, pose), (row, other) in combinations(rows, 2):
        if distance_metrics(pose, packed_pose(other, operations, maps))['full_RMSD_A'] <= .10:
            raise ValueError(f'Candidate near-duplicate detected: {row["id"]}')
    return [row for row, _ in rows]


def prepare_static(root: Path, row):
    folder = root / row['id']
    folder.mkdir(parents=True)
    copy_bound(Path(row['coordinate_path']), folder / 'POSCAR', row['coordinate_sha256'])
    profile = build_fe110_active_learning_force_label(folder)
    values = read_incar_values(folder / 'INCAR')
    if (any(float(values[key]) != expected for key, expected in
            {'ENCUT':400, 'ISPIN':2, 'ISMEAR':1, 'SIGMA':.20, 'NSW':0, 'IBRION':-1, 'LORBIT':11}.items())
            or profile['gamma_mesh'] != [5,5,1] or profile['cores'] != 32):
        raise ValueError(f'Generated force-label branch differs from the reviewed budget and protocol: {row["id"]}')
    evidence = preflight(folder, 'diagnostic_static', write_report=False)
    save(folder / 'local_preflight.json', evidence)
    if not evidence['passed']:
        raise ValueError(f'Canonical local preflight failed for {row["id"]}: {evidence["errors"]}')
    return {**row, 'local_input_directory': str(folder), 'input_hashes': evidence['files'],
            'bundle_sha256': evidence['bundle_sha256'], 'local_preflight_pass': True,
            'POTCAR.spec': (folder / 'POTCAR.spec').read_text(encoding='ascii').strip(),
            'budget_MPI_ranks': profile['cores'], 'proposed_wall_minutes': int(row['conditional_core_h_cap']/profile['cores']*60),
            'wall_limit_enforced_in_local_launcher': False, 'execution_authorized': False}


def prepare(destination: Path):
    frozen = guard_hashes()
    path = SOURCE / 'path_audit.json'
    checked(path, AUDIT_SHA)
    audit = load(path)
    for name, expected in audit['source_sha256'].items():
        checked(Path(name), expected)
    rows = inspect_candidates(audit)
    destination.mkdir(parents=True, exist_ok=False)
    first = [prepare_static(destination / 'vasp_review_inputs', row) for row in rows]
    pair = prepare_pair(destination)
    if guard_hashes() != frozen:
        raise ValueError('Frozen input guard changed')
    budget = {'recommended_points': 10, 'median_reference_core_hours': sum(r['historical_median_core_h'] for r in first),
              'proposed_cap_core_hours': sum(r['conditional_core_h_cap'] for r in first),
              'composition_counts': dict(Counter(r['composition'] for r in first)), 'scheduler_wall_limit_bound': False,
              'calculation_submitted': 0}
    result = {'source_audit_sha256': AUDIT_SHA, 'DFT_first_ten': first,
              'reserve_ids_only': [r['id'] for r in audit['selected'][10:]], 'budget': budget, 'pair': pair,
              'profile_sha256': sha(DEFAULT_PROFILE), 'frozen_hashes': frozen,
              'POTCAR_contents_prepared': False, 'execution_authorized': False}
    save(destination / 'review.json', result)
    table(destination / '首批10个补标预检.csv', first, [
        ('rank','优先级'),('id','结构ID'),('composition','组成'),('environment','成键与Fe配位'),('binding_sites','原子和Fe接触位点'),
        ('nearest_label_environment','最近标签Fe配位'),('closest_existing_catalog_label','最近已有标签及距离_A'),
        ('exact_catalog_label_match','同坐标标签命中'),('old_280_input_match','历史280静态输入命中'),('local_preflight_pass','本地预检'),
        ('historical_median_core_h','历史中位核时'),('conditional_core_h_cap','建议上限核时'),('proposed_wall_minutes','建议单点分钟数'),
        ('local_input_directory','审阅用输入目录'),('execution_authorized','执行授权')])
    print(budget)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    prepare(parser.parse_args().output.resolve())
