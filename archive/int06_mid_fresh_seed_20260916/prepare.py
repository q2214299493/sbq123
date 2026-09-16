"""Fresh endpoint-only seed and review; never submit or mutate the old path."""
from copy import deepcopy
from pathlib import Path
import json
import os
import shutil
import subprocess

import numpy as np
from ase.geometry import find_mic
from ase.io import read
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.ts_strategy_engine.contract import normalize_contract
from scripts.ts_strategy_engine.workflow import PlanRequest, plan
from scripts.neb_agent.generate_path import generate_path
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.path_evidence import write_path_review_draft
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.dual_model_ml_neb import _load_request, _load_images, _geometry_guard_evidence

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822'
OLD = BASE / 'h_migration_int06_to_mid_path_20260910'
DEST = BASE / 'h_migration_int06_mid_fresh_seed_20260916'
PATH = DEST / 'endpoint_idpp_plan/path_candidate'


def reserve_destination():
    if DEST.exists():
        rejected = load_json_object(DEST/'plan/ts_strategy.json')
        assert rejected['path_generation']['errors'] == ['reviewed executable waypoint or accepted retrieval constraint is required']
        assert not (DEST/'endpoint_idpp_plan').exists()
    else:
        DEST.mkdir()


def main():
    reserve_destination()
    source = load_json_object(OLD / 'source_review.json')
    endpoints = [row for row in source['sources'] if row['role'] in ('initial', 'final')]
    for row in endpoints:
        original = Path(row['path'])
        assert sha256_file(original) == row['sha256']
        target = DEST / ('IS.vasp' if row['role'] == 'initial' else 'FS.vasp')
        if target.exists():
            assert sha256_file(target) == row['sha256']
        else:
            shutil.copyfile(original, target)
    contract = load_json_object(OLD / 'contract.json')
    for key in ('contract_sha256', 'atom_map_sha256', 'compatibility_sha256'):
        contract.pop(key, None)
    contract['waypoint_files'] = []
    contract['retrieval_constraints'] = {
        'accepted_local_inputs_only': True,
        'source_gate': str(BASE / 'retrieval/transferability_review.json'),
        'decision': 'REUSE_VERIFIED_LOCAL_ENDPOINTS_ONLY',
        'reason': 'Independent initial-path proposal, no old ML interior or external coordinates reused.'}
    normalized = normalize_contract(contract)
    if (DEST/'contract.json').exists():
        assert load_json_object(DEST/'contract.json') == normalized
    else:
        write_json_exclusive(DEST / 'contract.json', normalized)
    result = plan(PlanRequest(
        initial=DEST/'IS.vasp', final=DEST/'FS.vasp', contract=DEST/'contract.json',
        workdir=DEST/'endpoint_idpp_plan', database=ROOT/'data/project_registry.sqlite3',
        families=ROOT/'configs/ts_strategy_engine/families.yaml',
        thresholds=ROOT/'configs/neb_agent/default_thresholds.yaml', initialize_path=False, images=7))
    assert not result['status'].startswith('STOP'), result['status']
    generated = generate_path(DEST/'IS.vasp',DEST/'FS.vasp',PATH,7,'idpp',None,[])
    assert generated['status'] == 'READY_FOR_GEOMETRY_REVIEW', generated
    # Bind the explicitly selected endpoint-only initializer, not the generic family's waypoint default.
    generated.update({key:normalized[key] for key in ('contract_sha256','atom_map_sha256','compatibility_sha256')})
    generated['fingerprint_id'] = build_fingerprint(normalized)['fingerprint_id']
    generated['initialization_override'] = 'Endpoint-only full-atom IDPP for this short H site hop; pending geometry review'
    from scripts.artifact_io import write_json
    write_json(PATH/'path_generation_report.json',generated)
    frames = [read(PATH/f'{i:02d}/POSCAR', format='vasp') for i in range(9)]
    rows = []
    for i, atoms in enumerate(frames):
        atoms.pbc = (True, True, False)
        assert atoms.get_chemical_symbols() == frames[0].get_chemical_symbols()
        assert np.allclose(atoms.cell, frames[0].cell, atol=1e-8, rtol=0)
        assert np.max(np.abs(atoms.positions[:18]-frames[0].positions[:18])) < 1e-8
        d = atoms.get_all_distances(mic=True)
        edges = connectivity_edges(atoms, list(range(45,50)), 1.25, 0.35)
        assert edges == [(0,1),(0,3),(1,2)], (i, edges)
        raw = atoms.positions-frames[max(0,i-1)].positions
        mic, lengths = find_mic(raw, atoms.cell, pbc=atoms.pbc)
        assert np.max(np.abs(raw-mic)) < 1e-7, 'periodic jump'
        distances = sorted((float(d[49,j]),j+1) for j in range(45))[:3]
        rows.append(dict(image=f'{i:02d}', minimum_pair_A=float(d[np.triu_indices(50,1)].min()),
            CC_A=float(d[45,46]), CO_A=float(d[46,47]), CH_A=float(d[45,48]), OH_A=float(d[47,49]),
            H50_Fe39_A=float(d[49,38]), H50_Fe40_A=float(d[49,39]),
            nearest_H50_Fe=distances, max_adjacent_atom_step_A=float(max(lengths)),
            H50_height_above_top_mean_A=float(atoms.positions[49,2]-np.mean(atoms.positions[36:45,2])),
            structure_sha256=sha256_file(PATH/f'{i:02d}/POSCAR')))
    for idx, name in ((0,'IS.vasp'),(8,'FS.vasp')):
        original = read(DEST/name)
        _, displacement = find_mic(frames[idx].positions-original.positions, original.cell, pbc=(True,True,False))
        assert max(displacement) < 1e-8
    assert min(r['minimum_pair_A'] for r in rows) > 1.0
    assert max(r['max_adjacent_atom_step_A'] for r in rows) < 0.5
    perl = Path('C:/Program Files/Git/usr/bin/perl.exe')
    vtst = ROOT/'archive/vtst_review_job9745217'
    script_root = '/c'+vtst.as_posix()[2:]
    env = {**os.environ,'PATH':str(perl.parent)+os.pathsep+os.environ['PATH']}
    commands, lines = [], []
    for i in range(8):
        command=[str(perl),script_root+'/dist.pl',f'{i:02d}/POSCAR',f'{i+1:02d}/POSCAR']
        run=subprocess.run(command,cwd=PATH,env=env,text=True,capture_output=True,check=True)
        lines.append(f'{i:02d} {i+1:02d} {float(run.stdout.strip()):.12f}')
        commands.append(dict(argv=command,exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr))
    (PATH/'dist.dat').write_text('\n'.join(lines)+'\n',encoding='ascii')
    command=[str(perl),script_root+'/nebmovie.pl','0']
    run=subprocess.run(command,cwd=PATH,env=env,text=True,capture_output=True,check=True)
    commands.append(dict(argv=command,exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr))
    with (PATH/'movie.xyz').open('xb') as handle:
        for i in range(9):
            handle.write((PATH/f'{i:02d}/POSCAR.xyz').read_bytes())
    movie=read(PATH/'movie.xyz',index=':',format='xyz')
    assert len(movie)==9
    for a,b in zip(frames,movie):
        assert a.get_chemical_symbols()==b.get_chemical_symbols()
        assert np.max(np.abs(a.positions-b.positions)) < 2e-5
    write_json_exclusive(PATH/'vtst_checks.json',dict(commands=commands))
    write_json_exclusive(PATH/'exact_mic_geometry.json',dict(rows=rows,fixed_drift_A=0,
        source_endpoints=endpoints,old_interior_reused=False,model_run=False,submitted=False))
    write_path_review_draft(PATH,PATH/'dist.dat',PATH/'movie.xyz',PATH/'path_review.draft.json')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
    anchor=frames[0].positions[49]
    positions=[find_mic(a.positions-anchor,a.cell,pbc=a.pbc)[0] for a in frames]
    old_mid=read(OLD/'waypoint07.vasp')
    old_h=find_mic(old_mid.positions[49]-anchor,old_mid.cell,pbc=(True,True,False))[0]
    for ax,v,title in ((axes[0],1,'Top view'),(axes[1],2,'Side view')):
        for j in range(36,45):
            ax.scatter(positions[0][j,0],positions[0][j,v],s=210,c='#bbc4cc')
            ax.annotate(f'Fe{j+1}',(positions[0][j,0],positions[0][j,v]),fontsize=8)
        for j,col in ((45,'black'),(46,'black'),(47,'red'),(48,'grey')):
            ax.scatter(positions[0][j,0],positions[0][j,v],s=65,c=col)
        h=np.array([p[49] for p in positions])
        ax.plot(h[:,0],h[:,v],'-o',color='#ee8822',label='Fresh endpoint IDPP')
        ax.scatter(old_h[0],old_h[v],marker='x',s=100,color='#7851a9',label='Old waypoint (not reused)')
        for i,p in enumerate(h):
            ax.annotate(f'{i:02d}',(p[0],p[v]),xytext=(3,7),textcoords='offset points',fontsize=8)
        ax.set(title=title,xlabel='x relative to initial H50 (A)',ylabel=('y' if v==1 else 'z')+' (A)')
        ax.set_aspect('equal',adjustable='datalim')
        ax.grid(alpha=.2)
    axes[1].legend(fontsize=8)
    fig.suptitle('INT06 to MID | 9-frame fresh seed | no model energies, not a TS')
    fig.savefig(DEST/'path_review.png',dpi=180)
    plt.close(fig)
    request=deepcopy(load_json_object(BASE/'h_migration_int06_to_mid_gpu_20260910/payload/request.json'))
    package=DEST/'gpu_request'
    package.mkdir()
    (package/'structures').mkdir()
    request['request_id']='int06_mid_fresh_endpoint_idpp_20260916'
    request['source_plan']={'method':'fresh all-atom endpoint-only IDPP; no old ML waypoint',
        'source_review_sha256':sha256_file(PATH/'exact_mic_geometry.json')}
    request['source_seed_review']={'status':'needs_user_geometry_review','path':str(PATH/'path_review.draft.json'),
        'sha256':sha256_file(PATH/'path_review.draft.json')}
    contract=load_json_object(DEST/'contract.json')
    request['reaction']={**request['reaction'],**{k:contract[k] for k in (
        'reaction_id','contract_sha256','atom_map_sha256','compatibility_sha256')}}
    request['images']=[]
    for i in range(9):
        target=package/f'structures/{i:02d}.vasp'
        shutil.copyfile(PATH/f'{i:02d}/POSCAR',target)
        request['images'].append(dict(image=f'{i:02d}',path=f'structures/{i:02d}.vasp',sha256=sha256_file(target)))
    request['source_evidence_files']={}
    request['runtime_bindings']={}
    request['preconditioning']['purpose']='No artificial coordinate restraints; fresh endpoint-only seed'
    request['production_limits']['image_count']=9
    request['production_limits']['production_submission_authorized']=False
    request['preparation_status']='DRAFT_NOT_DEPLOYED; runtime and review bindings required before submission'
    request['fallback_policy']={'gpu_attempts_before_vasp_path_review':1,
        'on_unusable_gpu_path':'prepare VASP ordinary coarse NEB from geometry-valid full endpoints path',
        'reuse_failed_geometry':False,'automatic_submission':False,'mandatory_pilot':False,
        'note':'Fatal VASP electronic errors remain unresolved; never bypass electronic validity.'}
    write_json_exclusive(package/'request.draft.json',request)
    parsed=_load_request(package/'request.draft.json')
    guards=_geometry_guard_evidence(_load_images(parsed,package),parsed)
    assert guards['passed'],guards
    write_json_exclusive(DEST/'local_preflight.json',dict(geometry=guards,
        endpoint_registry_validation=load_json_object(DEST/'endpoint_idpp_plan/endpoint_evidence.json'),
        request_sha256=sha256_file(package/'request.draft.json'),model_executed=False,
        remote_preflight=False,submission_authorized=False))
    print(json.dumps(dict(status='PREPARED_FOR_REVIEW',rows=rows),indent=2))


if __name__=='__main__':
    main()
