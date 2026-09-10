"""Bounded, read-only scientific collection for job 9748648; no submission or acceptance."""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from ase.geometry import find_mic
from ase.io import read

from scripts.adsorption.analyze_fe110_ch_h_relaxation import parse_oszicar, parse_outcar
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges, connectivity_change
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.ts_endpoint.validator import EndpointValidationRequest, TSEndpointValidator
from scripts.vasp_result_gate import read_incar_values, validate_vasp_relaxation

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration1357_valley06_relax_20260909'
DEST = PACKAGE / 'completed_review_20260910'
CACHE = Path('C:/Users/86177/AppData/Local/Temp/fe110-9748648-check-31c3cfc77dbb41678b9cf02de78a0eaf')
CID = 'fe110_h_migration1357_valley06_relax_9748648'
NAMES = ('INCAR', 'POSCAR', 'CONTCAR', 'OSZICAR', 'OUTCAR', 'KPOINTS')


def main() -> None:
    DEST.mkdir(exist_ok=True)
    record = json.loads((PACKAGE / 'submission_record.json').read_text())
    remote = record['remote_dir']
    command = f"bjobs -a 9748648; cd {remote} && sha256sum {' '.join(NAMES)} POTCAR"
    observed = datetime.now(timezone.utc).isoformat()
    response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                               'sunboquan-codex', command], capture_output=True, text=True, check=True)
    lines = response.stdout.splitlines()
    job_line = next(line for line in lines if line.split()[:1] == ['9748648'])
    assert job_line.split()[2] == 'DONE', job_line
    hashes = {line.split()[1]: line.split()[0] for line in lines
              if len(line.split()) == 2 and len(line.split()[0]) == 64}
    assert set(hashes) == {*NAMES, 'POTCAR'}
    assert hashes['POTCAR'] == record['potcar_sha256']
    for name in NAMES:
        source = CACHE / name if name in ('CONTCAR', 'OUTCAR', 'OSZICAR') else PACKAGE / name
        assert sha256_file(source) == hashes[name], name
        target = DEST / name
        if target.exists():
            assert sha256_file(target) == hashes[name], f'existing target differs: {name}'
        else:
            shutil.copyfile(source, target)
    scheduler = {'job_id': '9748648', 'status': 'DONE', 'server_alias': 'sunboquan-codex',
                 'scheduler': 'LSF', 'observed_at': observed, 'source_command': command,
                 'raw_stdout': response.stdout, 'raw_stderr': response.stderr,
                 'exit_code': response.returncode, 'remote_sha256': hashes}
    write_json_exclusive(DEST / 'scheduler_and_hashes.json', scheduler)
    connection = sqlite3.connect((ROOT/'data/project_registry.sqlite3').as_uri()+'?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    refs = [dict(row) for row in connection.execute(
        "SELECT file_id,calculation_id,local_path,sha256 FROM files WHERE filename='CONTCAR' "
        "AND calculation_id LIKE 'fe110_ads_c2ho_h_c2h2o_%'")]
    parent = 'fe110_ads_c2ho_h_c2h2o_9725473'
    compatibility = dict(connection.execute('SELECT * FROM calculation_compatibility WHERE calculation_id=?', (parent,)).fetchone())
    snapshot = {'references': refs, 'parent_compatibility': compatibility,
                'calculation': dict(connection.execute('SELECT * FROM calculations WHERE calculation_id=?',(CID,)).fetchone())}
    write_json_exclusive(DEST/'registry_sources.json', snapshot)
    connection.close()
    initial, final = read_poscar(DEST/'POSCAR'), read_poscar(DEST/'CONTCAR')
    assert initial.symbols == final.symbols == ['Fe','C','O','H']
    assert initial.counts == final.counts == [45,2,1,2]
    assert np.array_equal(initial.cell, final.cell)
    assert initial.flags == final.flags
    fixed = [i for i,flags in enumerate(final.flags) if all(x.upper()=='F' for x in flags)]
    assert fixed == list(range(18))
    inputs = read_incar_values(DEST/'INCAR')
    expected = {'GGA':'PE','ENCUT':'400','ISPIN':'2','ISMEAR':'1','SIGMA':'0.2','LDIPOL':'.FALSE.',
                'MAGMOM':'45*2.2 2*0.0 1*0.0 2*0.0','IBRION':'2','EDIFFG':'-0.02'}
    assert all(inputs[k] == v for k,v in expected.items())
    assert (DEST/'KPOINTS').read_text().splitlines()[2:4] == ['Gamma','5 5 1']
    gate = validate_vasp_relaxation(DEST)
    forces = parse_outcar(DEST/'OUTCAR',list(range(18,50)))
    assert forces['max_movable_force_eV_per_A'] < abs(float(inputs['EDIFFG']))
    atoms = read(DEST/'CONTCAR', format='vasp')
    atoms.pbc = (True,True,False)
    start = read(DEST/'POSCAR', format='vasp')
    start.pbc = atoms.pbc
    rules = yaml.safe_load((ROOT/'configs/adsmind_lite/analysis_rules.yaml').read_text())
    config = rules['connectivity']
    edges = [connectivity_edges(a,list(range(45,50)),config['covalent_radius_scale'],config['minimum_bond_distance_angstrom']) for a in (start,atoms)]
    chemistry = connectivity_change(5,*edges)
    assert sorted(edges[0]) == sorted(edges[1]) == [(0,1),(0,3),(1,2)]
    distances = atoms.get_all_distances(mic=True)
    indices = np.triu_indices(50,k=1)
    minimum = float(distances[indices].min())
    assert minimum > 1.0
    _, displacement = find_mic(atoms.positions-start.positions,atoms.cell,pbc=atoms.pbc)
    assert max(displacement[:18]) < 1e-8
    comparisons = []
    validator_results = {}
    for ref in refs:
        path = Path(ref['local_path'])
        assert sha256_file(path) == ref['sha256'], ref['file_id']
        other = read(path,format='vasp')
        other.pbc = atoms.pbc
        assert other.get_chemical_symbols() == atoms.get_chemical_symbols()
        assert np.allclose(other.cell,atoms.cell,atol=1e-8,rtol=0)
        _, movement = find_mic(atoms.positions-other.positions,atoms.cell,pbc=atoms.pbc)
        comparisons.append({'calculation_id':ref['calculation_id'], 'structure_sha256':ref['sha256'],
                            'H50_displacement_A':float(movement[49]),
                            'adsorbate_rmsd_A':float(np.sqrt(np.mean(movement[45:]**2))),
                            'movable_rmsd_A':float(np.sqrt(np.mean(movement[18:]**2)))})
        if ref['calculation_id'] in (parent, 'fe110_ads_c2ho_h_c2h2o_9737143'):
            old_nearest = sorted(range(45),key=lambda i:other.get_distance(49,i,mic=True))[:3]
            new_nearest = sorted(range(45),key=lambda i:distances[49,i])[:3]
            site_event = f'H50 coordination {sorted(i+1 for i in old_nearest)} to {sorted(i+1 for i in new_nearest)}'
            request = EndpointValidationRequest(initial_structure=path,endpoint_structure=DEST/'CONTCAR',
                reactive_atoms=(49,),adsorbate_atoms=tuple(range(45,50)),bond_changes=(),surface_atoms=tuple(range(45)),
                expected_site_changes=(site_event,),observed_site_changes=(site_event,),surface='fe110',reaction_type='H surface migration')
            validator_results[ref['calculation_id']] = TSEndpointValidator(ROOT/'configs/structure_purpose_routing.yaml').validate(request).as_dict()
    result = {'job_id':'9748648','observed_at':observed,'source_files':hashes,'relaxation_gate':gate,
              'outcar':forces,'oszicar':parse_oszicar(DEST/'OSZICAR',200),
              'chemistry':chemistry,'adsorbate_bonds_local_zero_based':edges[1],
              'geometry':{'minimum_contact_A':minimum,'fixed_indices':fixed,'fixed_max_drift_A':float(max(displacement[:18])),
                          'H50_seed_displacement_A':float(displacement[49]),'surface_max_displacement_A':float(max(displacement[:45])),
                          'CC_A':float(distances[45,46]),'CO_A':float(distances[46,47]),'CH_A':float(distances[45,48]),
                          'OH50_A':float(distances[47,49]),
                          'H50_nearest_Fe':[(i+1,float(distances[49,i])) for i in sorted(range(45),key=lambda i:distances[49,i])[:3]],
                          'C46_nearest_Fe':[(i+1,float(distances[45,i])) for i in sorted(range(45),key=lambda i:distances[45,i])[:1]],
                          'C47_nearest_Fe':[(i+1,float(distances[46,i])) for i in sorted(range(45),key=lambda i:distances[46,i])[:1]],
                          'O48_nearest_Fe':[(i+1,float(distances[47,i])) for i in sorted(range(45),key=lambda i:distances[47,i])[:1]]},
              'compatibility_input_checks':expected,'comparisons':comparisons,'endpoint_validator':validator_results,
              'limits':['No Hessian stability claim.','Identity-preserving comparison, not exhaustive surface symmetry equivalence.',
                        'No TS, barrier or kinetics acceptance.','Image02 remains an unvalidated ML minimum.']}
    write_json_exclusive(DEST/'parsed_review_evidence.json',result)
    print(json.dumps({'directory':str(DEST),'geometry':result['geometry'],'comparisons':comparisons,
                      'endpoint_status':{k:{'status':v['status'],'errors':v['errors'],'warnings':v['warnings']} for k,v in validator_results.items()},
                      'energy_eV':forces['final_TOTEN_eV'],'force_eV_A':forces['max_movable_force_eV_per_A']},indent=2))


if __name__ == '__main__':
    main()
