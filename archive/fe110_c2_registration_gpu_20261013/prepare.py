"""Task-scoped preparation only: three reviewed exceptions and fifteen GPU candidates."""
from __future__ import annotations

import argparse
import itertools
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.build_fe110_care_isomers import review
from scripts.adsorption.prepare_completion_registration import checked_receipt, result_evidence
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_atomic
from scripts.registry_connection import open_registry

OLD = Path('calculations/fe110_five_c2_adsorption_20261006')
NEW = Path('calculations/fe110_c2_adsorption_06_10_20261012')
NAMES = ('02_extra2', '04_cfg2', '05_cfg1')
AUTHORITY = '都录入吧 然后把那15个也提交gpu'
REVIEWER = 'User-authorized Codex scientific review'


def registry():
    output = OLD / 'final_review_20261012/registration_exception_20261013'
    if output.exists():
        raise FileExistsError(output)
    analysis_path = OLD / 'final_review_20261012/final_analysis.json'
    previous_path = OLD / 'final_review_20261012/registration_v2/registry_batch.json'
    analysis, previous = load_json_object(analysis_path), load_json_object(previous_path)
    now = datetime.now(timezone.utc).isoformat()
    exception = {'scope': 'three named completed adsorption calculations only',
                 'authorizing_user_request': AUTHORITY, 'authorized_at': now,
                 'names': list(NAMES), 'requirement_waived': 'original_scheduler_DONE_evidence',
                 'scheduler_status': 'UNKNOWN', 'infer_DONE': False,
                 'scientific_checks_waived': [], 'production_policy_changed': False}
    write_json_atomic(output / 'user_authorization.json', exception, ensure_ascii=True)
    rows = {k: [] for k in ('files', 'results', 'reviews', 'job_status_history')}
    changes, provenance = [], {}
    with open_registry(Path('data/project_registry.sqlite3')) as connection:
        event = connection.execute('SELECT coalesce(max(status_event_id),0) FROM job_status_history').fetchone()[0]
        for index, name in enumerate(NAMES):
            record = next(r for r in analysis['records'] if r['name'] == name)
            assert record['eligible_for_review'] and not record['duplicate_of']
            directory, receipt = checked_receipt(record)
            cid = 'fe110_five_c2_adsorption_20261006_' + name
            calc = connection.execute('SELECT workflow_status FROM calculations WHERE calculation_id=?', (cid,)).fetchone()
            assert calc['workflow_status'] == 'needs_review', (cid, dict(calc))
            comp_row = connection.execute('SELECT * FROM calculation_compatibility WHERE calculation_id=?', (cid,)).fetchone()
            comp = json.loads(comp_row['compatibility_json'])
            old_comp = next(r for r in previous['rows']['calculation_compatibility'] if r['calculation_id'] == cid)
            assert comp == json.loads(old_comp['compatibility_json'])
            assert sha256_json(comp) == comp_row['compatibility_fingerprint']
            prefix = cid + '_scheduler_exception_20261013'
            review_path = output / (name + '_review.json')
            decision = {'decision': 'accept', 'reason': 'Convergence, intended graph, geometry, branch and source hashes pass; user explicitly accepts missing scheduler terminal evidence for this result only.'}
            write_json_atomic(review_path, {'record': record, 'decision': decision, 'scheduler_exception': exception,
                'analysis_sha256': sha256_file(analysis_path), 'previous_batch_sha256': sha256_file(previous_path),
                'reviewer': REVIEWER, 'reviewed_at': now}, ensure_ascii=True)
            rows['files'].append({'file_id': prefix + '_review', 'calculation_id': cid,
                'job_record_id': 'lsf_' + record['job_id'], 'role': 'scientific_review',
                'filename': review_path.name, 'local_path': str(review_path.resolve()), 'storage_mode': 'local_only',
                'byte_size': review_path.stat().st_size, 'sha256': sha256_file(review_path), 'existence_status': 'confirmed'})
            rows['reviews'].append({'review_id': prefix + '_review', 'calculation_id': cid,
                'review_type': 'adsorption_completion_task_scoped_scheduler_exception', 'decision': 'accept',
                'reviewer': REVIEWER, 'reviewed_at': now,
                'evidence': str(review_path.resolve()) + '#sha256=' + sha256_file(review_path), 'reason': decision['reason']})
            rows['job_status_history'].append({'status_event_id': event + index + 1,
                'job_record_id': 'lsf_' + record['job_id'], 'scheduler_status': 'UNKNOWN',
                'scientific_status': 'converged_accept', 'checked_at': now,
                'source_command': 'bjobs -a -w; bhist -l; bacct -l (same three jobs, live check 2026-10-13 Asia/Shanghai)',
                'source_text': 'bjobs: Job is not found; bhist: No matching job found; bacct: No job was found satisfying your specification.',
                'reviewer': REVIEWER, 'notes': 'Terminal queue status unavailable; never inferred from VASP. Explicit task-scoped user exception.'})
            changes.append({'status_change_id': prefix + '_accepted', 'calculation_id': cid,
                'expected_workflow_status': 'needs_review', 'new_workflow_status': 'accepted',
                'changed_at': now, 'reviewer': REVIEWER, 'reason': decision['reason']})
            validation = {'owner': 'vasp_relaxation', 'directory': str(directory),
                'source_files': {f: receipt['remote']['files'][f]['sha256'] for f in ('INCAR','POSCAR','CONTCAR','OUTCAR','OSZICAR')},
                'completion_review_sha256': sha256_file(review_path), 'scheduler_exception': exception}
            for kind, value, unit, accepted in [('final_toten', record['final_toten_eV'], 'eV', True),
                    ('final_max_movable_force', record['fmax_movable_eV_A'], 'eV/angstrom', False)]:
                result = {'result_id': prefix + '_' + kind, 'calculation_id': cid, 'result_name': kind,
                    'numeric_value': value, 'unit': unit, 'source_file_id': cid + '_completion_20261012_OUTCAR',
                    'reference_convention': comp['final_energy_convention'] if accepted else 'movable_atoms_vector_norm',
                    'source_locator': 'final free energy TOTEN' if accepted else 'final TOTAL-FORCE block; Fe0-17 excluded',
                    'extraction_method': 'scripts.aqcat25_calibration.parse_final_outcar with reviewed VASP relaxation evidence',
                    'validation_status': 'accepted_compatible_final_energy' if accepted else 'reviewed', 'created_at': now,
                    'notes': 'Explicit scheduler-evidence exception; scheduler UNKNOWN. No inferred adsorption energy or thermal corrections.'}
                assert not connection.execute('SELECT 1 FROM results WHERE calculation_id=? AND result_name=?', (cid, kind)).fetchone()
                rows['results'].append(result)
                provenance[result['result_id']] = result_evidence(result, validation, comp, review_path, REVIEWER, now)
    write_json_atomic(output / 'registry_batch.json', {'schema_version': 1,
        'document_kind': 'calculation_registry_batch', 'batch_id': 'fe110_c2_three_scheduler_exceptions_20261013',
        'created_at': now, 'reviewer': REVIEWER, 'reason': AUTHORITY,
        'rows': rows, 'workflow_status_changes': changes, 'result_provenance': provenance}, ensure_ascii=True)
    print(json.dumps({'prepared': str(output), 'accepted_results': 3, 'registry_written': False}))


def gpu():
    output = NEW / 'gpu_batch_v1'
    assert output.is_dir() and not (output / 'batch_manifest.json').exists()
    candidates_path = NEW / 'candidates_v2/candidate_review.json'
    candidates = load_json_object(candidates_path)
    request = load_json_object(Path('configs/adsmind_lite/fe110_c2_06_10_exploratory_20261012.json'))
    assert candidates['request_sha256'] == sha256_file(Path('configs/adsmind_lite/fe110_c2_06_10_exploratory_20261012.json'))
    slab = read_poscar(Path(candidates['source_slab']))
    assert sha256_file(Path(candidates['source_slab'])) == candidates['source_slab_sha256']
    assert len(candidates['candidates']) == 15
    now = datetime.now(timezone.utc).isoformat()
    plan = {'authorizing_user_request': AUTHORITY, 'reviewer': REVIEWER, 'reviewed_at': now,
        'candidate_review_sha256': sha256_file(candidates_path), 'candidates': candidates['candidates'],
        'scope': '15 exploratory AQCat25 adsorption pre-relaxations only',
        'source_status': '11 CARE predicted poses and 4 constructed hypotheses; not literature-stable minima',
        'soft_warnings_accepted_for_screening': ['06_A', '07_A', '09_B'],
        'scientific_acceptance': False, 'submit_vasp': False, 'promote_checkpoint': False}
    write_json_atomic(output / 'reviewed_plan.json', plan, ensure_ascii=True)
    comp = {'branch': candidates['surface_branch'], 'slab_model': 'true_fe110_fe45_5layer', 'facet': '110',
        'method_protocol_sha256': sha256_file(Path('docs/01_METHOD_PROTOCOL.md')),
        'clean_slab_sha256': candidates['source_slab_sha256'], 'sigma_eV': 0.2, 'gpu_energy_is_not_DFT': True}
    write_json_atomic(output / 'compatibility.json', comp, ensure_ascii=True)
    handoffs = []
    for candidate in candidates['candidates']:
        name = candidate['name']; source = NEW / 'candidates_v2' / candidate['structure']
        assert sha256_file(source) == candidate['structure_sha256']
        structure = read_poscar(source); symbols = expanded_symbols(structure)
        target = next(t for t in request['targets'] if t['id'] == candidate['species_id'])
        assert molecular_signature(structure) == target['signature']
        assert np.allclose(structure.cell, slab.cell, atol=1e-10, rtol=0)
        assert np.allclose(structure.frac[:45], slab.frac, atol=1e-10, rtol=0)
        assert structure.flags[:45] == slab.flags
        geometry = review(structure, structure, list(range(45, len(symbols))))
        assert geometry['verdict'] == 'pass'
        directory = output / name; directory.mkdir()
        shutil.copyfile(source, directory / 'POSCAR')
        handoff = {'schema_version': 2, 'direction': 'work_to_gpu', 'workflow_kind': 'adsorption',
            'handoff_id': 'fe110_c2_06_10_20261013_' + name, 'source_workflow_sha256': sha256_file(output / 'reviewed_plan.json'),
            'candidate_structure': {'path': 'POSCAR', 'sha256': sha256_file(source), 'format': 'vasp_poscar',
                'atom_count': len(symbols), 'atom_order_sha256': atom_order_sha256(symbols)},
            'compatibility': {**{k: comp[k] for k in ('branch','slab_model','facet')}, 'sha256': sha256_file(output / 'compatibility.json')},
            'model': {'identifier': 'AQCat25 demo_single model.pt',
                'checkpoint_sha256': 'e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50',
                'fmax_eV_per_A': 0.1, 'max_steps': 80},
            'selective_dynamics': {'fixed_atom_indices_1based': list(range(1,19)), 'free_atom_count': len(symbols)-18},
            'adsorption': {'evidence_gated_plan_sha256': sha256_file(output / 'reviewed_plan.json'),
                'clean_slab_sha256': candidates['source_slab_sha256'],
                'identity_and_connectivity': candidate['care_code'] + ' ' + candidate['connectivity'],
                'intended_motif': candidate['origin'] + ': ' + candidate['geometry_review']['site_label'],
                'surface_elements': ['Fe'], 'adsorbate_atoms': [{'index_1based': i+1, 'symbol': symbols[i],
                    'role': 'non_anchor' if symbols[i]=='H' else 'anchor'} for i in range(45,len(symbols))],
                'connectivity_constraints': [], 'monitored_pairs': [{'label': str(a+1)+'_'+str(b+1),
                    'atoms_1based': [a+1,b+1]} for a,b in itertools.combinations(range(45,len(symbols)),2)]},
            'restrictions': {'predicted_candidate_only': True, 'submit_vasp': False,
                'scientific_acceptance': False, 'direct_gpu_to_vasp_handoff': False}}
        write_json_atomic(directory / 'handoff.json', handoff, ensure_ascii=True)
        validate_handoff(directory / 'handoff.json', root=directory)
        handoffs.append({'name': name, 'handoff_sha256': sha256_file(directory / 'handoff.json')})
    runtime = output / 'runtime'; runtime.mkdir()
    template = OLD / 'gpu_supplement_v1/runtime'
    for p in template.iterdir():
        if p.is_file(): shutil.copyfile(p, runtime / p.name)
    files = [{'path': p.relative_to(output).as_posix(), 'sha256': sha256_file(p)}
        for p in sorted(output.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    batch = {'remote_root': '/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_06_10_20261013_gpu_v1',
        'handoffs': handoffs, 'checkpoint_sha256': handoff['model']['checkpoint_sha256'], 'files': files}
    write_json_atomic(output / 'batch_manifest.json', batch, ensure_ascii=True)
    print(json.dumps({'prepared': str(output), 'candidates': 15, 'submitted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=('registry','gpu'))
    {'registry': registry, 'gpu': gpu}[parser.parse_args().action]()
