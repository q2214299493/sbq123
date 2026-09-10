"""Prepare a new local INT06-to-MID path from verified records; no job submission."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.ts_strategy_engine.contract import load_contract, normalize_contract

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822'
DEST = BASE/'h_migration_int06_to_mid_path_20260910'


def main() -> None:
    DEST.mkdir(exist_ok=False)
    parent_path = BASE/'gpu_split_paths_dual_model_20260901/segment_01_IS_A_to_MID/contract.normalized.json'
    parent = load_contract(parent_path)
    gpu = BASE/'gpu_split_paths_dual_model_20260901/gpu_return_job1357'
    manifest_path = gpu/'dual_model_gpu_ml_neb_path_manifest.candidate.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    connection = sqlite3.connect((ROOT/'data/project_registry.sqlite3').as_uri()+'?mode=ro',uri=True)
    connection.row_factory = sqlite3.Row
    endpoint_refs = {
        'initial':{'calculation_id':'fe110_h_migration1357_valley06_relax_9748648',
                   'structure_file_id':'fe110_h_migration1357_valley06_relax_9748648_CONTCAR_final',
                   'static_result_id':'fe110_h_migration1357_valley06_relax_9748648_final_toten'},
        'final':parent['endpoints']['final'],
    }
    sources = []
    for side,ref in endpoint_refs.items():
        row = connection.execute('SELECT local_path,sha256 FROM files WHERE file_id=?',(ref['structure_file_id'],)).fetchone()
        source = Path(row['local_path'])
        assert sha256_file(source)==row['sha256']
        filename = 'IS.vasp' if side=='initial' else 'FS.vasp'
        shutil.copyfile(source,DEST/filename)
        sources.append({'role':side,'path':str(source),'sha256':row['sha256'],'registry':ref})
    triad = []
    for image in ('06','07','08'):
        row = next(r for r in manifest['images'] if r['image']==image)
        source = gpu/row['structure_path']
        assert sha256_file(source)==row['structure_sha256']
        matches = [dict(r) for r in connection.execute(
            'SELECT file_id,calculation_id,role,filename FROM files WHERE sha256=?',(row['structure_sha256'],))]
        triad.append({'image':image,'structure_sha256':row['structure_sha256'],'registry_hash_matches':matches})
        if image=='07':
            shutil.copyfile(source,DEST/'waypoint07.vasp')
            sources.append({'role':'reviewed_ML_waypoint_only','path':str(source),'sha256':row['structure_sha256']})
    connection.close()
    first, middle, last = [read(DEST/name,format='vasp') for name in ('IS.vasp','waypoint07.vasp','FS.vasp')]
    for atoms in (first,middle,last):
        atoms.pbc=(True,True,False)
        assert atoms.get_chemical_symbols()==first.get_chemical_symbols()
        assert np.allclose(atoms.cell,first.cell,atol=1e-8,rtol=0)
    end_distances = [a.get_distance(49,38,mic=True) for a in (first,last)]
    contract = {k:v for k,v in parent.items() if k not in ('atom_map_sha256','compatibility_sha256','contract_sha256')}
    contract.update(reaction_id='fe110_c2ho_h_migration_INT06_9748648_to_MID9737143',
                    reactant_id='c2ho_plus_h_int06_job9748648',product_id='c2ho_plus_h_mid_job9737143',
                    endpoints=endpoint_refs,site_changes=['h49:fe39_to_fe38_via_fe37_fe40'],
                    waypoint_files=[str(DEST/'waypoint07.vasp')],
                    reaction_coordinates=[{'name':'H50_to_arriving_Fe39','kind':'distance','atoms':[49,38],
                                           'important_interval_A':[float(min(end_distances)),float(max(end_distances))],
                                           'role':'primary'}],
                    retrieval_constraints={'accepted_local_inputs_only':True,'source_gate':str(BASE/'retrieval/transferability_review.json'),
                                           'decision':'REUSE_VERIFIED_LOCAL_ENDPOINTS_AND_EXISTING_ML_WAYPOINT',
                                           'reason':'Same mapped H migration subinterval; no new external coordinates, parameters or energies.'})
    write_json_exclusive(DEST/'contract.json',normalize_contract(contract))
    write_json_exclusive(DEST/'source_review.json',{
        'status':'reviewed_for_initial_path_preparation_only','reviewer':'Codex',
        'sources':sources,'parent_contract_sha256':sha256_file(parent_path),'gpu_manifest_sha256':sha256_file(manifest_path),
        'retrieval_review_sha256':sha256_file(BASE/'retrieval/transferability_review.json'),
        'triad_registry_lookup':triad,'interior_images':3,'waypoint_role':'ML07 locates the Fe38/Fe41 bridge crossing; not a TS.',
        'site_change_one_based':'H50 leaves Fe40 support and approaches Fe39 while passing between Fe38 and Fe41.',
        'method_rationale':'New short ordinary no-climb NEB seed with one reviewed waypoint; direct Dimer lacks exact VASP peak-triad validation.',
        'limits':['No new calculation authorized or submitted.','First IS-A-to-INT06 interval and image02 remain open.'],
    })
    print(json.dumps({'directory':str(DEST),'H50_Fe39_endpoint_distances_A':end_distances,'triad_matches':triad},indent=2))


if __name__=='__main__':
    main()
