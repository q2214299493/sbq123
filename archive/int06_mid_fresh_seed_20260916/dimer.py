"""Prepare/review one GPU1635 image05 Dimer; submission is a separate CLI action."""
import argparse
from datetime import datetime, timezone
import json
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from ase.io import read
from ase.geometry import find_mic

from archive.int06_mid_fresh_seed_20260916.prepare import ROOT, BASE, DEST
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.prepare_gpu_path_dimer import prepare, bind
from scripts.neb_agent.submission import preflight
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity

PATH = DEST / 'review_job1635'
SOURCE = DEST / 'returned_job1635/production'
RUN = BASE / 'h_migration_int06_mid_dimer_gpu1635_20260916'
PARENT = BASE / 'h_migration_int06_mid_gpu1635_dimer_parent_20260916'
REMOTE = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/' + RUN.name
POTCAR = '~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR'
POTCAR_HASH = 'e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85'
THRESHOLDS = ROOT / 'configs/neb_agent/default_thresholds.yaml'


def prepare_candidate():
    geometry = diagnose(PATH, ['49'], [], THRESHOLDS,
                        reaction_pairs=[[49, 38], [49, 39]], expected_interior=7)
    assert geometry['status'] == 'PASS', geometry['errors']
    manifest = SOURCE / 'dual_model_gpu_ml_neb_path_manifest.candidate.json'
    review = dict(schema_version=1, document_kind='gpu_dimer_path_review',
        status='accepted_for_direct_dimer_candidate', candidate_manifest_sha256=sha256_file(manifest),
        policy_sha256=sha256_file(ROOT / 'configs/dimer_gate.yaml'), candidate_image='05',
        reviewer='Codex numerical and actual 00-08 visual review; user selected highest point',
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        target_reaction_event='H50 surface migration INT06 to MID; C2HO skeleton retained',
        reaction_atom_indices_zero_based=[49],
        evidence=dict(geometry=bind(PATH / 'path_geometry_diagnosis.json'),
                      movie=bind(PATH / 'movie.xyz'), dist=bind(PATH / 'geometry_and_provenance.json')),
        notes='All nine final structures reviewed. 04-05 flat peak; MatRIS05 exceeds04 by0.000834eV, AQCat favors04. '
              'Same migration corridor as failed1517. Electronic recovery not proven. User explicitly authorized another Dimer.',
        vasp_triad_performed=False, scientific_status='predicted_starting_candidate_only')
    for key in ['geometry_continuity', 'periodic_mapping', 'reaction_coordinate_resolution',
                'elementary_step_assignment', 'candidate_selection']:
        review[key] = 'accepted'
    review_path = DEST / 'gpu1635_direct_dimer_review.json'
    write_json_exclusive(review_path, review)
    result = prepare(DEST / 'submission_20260916/payload/request.json', manifest,
                     review_path, DEST / 'contract.json', PARENT, RUN, cores=80)
    # Retain the prior execution-host exclusion, without changing scientific tags.
    script = RUN / 'script.lsf'
    value = script.read_text()
    script.write_text(value.replace('#!/bin/sh\n', "#!/bin/sh\n#BSUB -R 'select[hname!=gknew0440]'\n", 1),
                      encoding='ascii', newline='\n')
    a = read(RUN / 'POSCAR', format='vasp')
    mode = np.loadtxt(RUN / 'MODECAR')
    assert mode.shape == (50, 3) and np.isfinite(mode).all()
    assert np.max(np.abs(mode[:18])) == 0
    assert abs(np.linalg.norm(mode)-1) < 1e-8
    assert int(np.argmax(np.linalg.norm(mode, axis=1))) == 49
    anchor = a.positions[49]
    p = find_mic(a.positions-anchor, a.cell, pbc=(True, True, False))[0]
    for child, parent in [(46, 47), (45, 46), (48, 45)]:
        p[child] = p[parent] + find_mic(a.positions[child]-a.positions[parent], a.cell, pbc=(True, True, False))[0]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
    for ax, axis, label in [(axes[0], 1, 'Top'), (axes[1], 2, 'Side')]:
        for j in range(36, 50):
            color = '#b7c2cf' if j < 45 else ('#ee8924' if j == 49 else '#c04444' if j == 47 else '#38414b')
            ax.scatter(p[j, 0], p[j, axis], color=color, s=100 if j < 45 else 55)
            ax.annotate(f'{a[j].symbol}{j+1}', (p[j, 0], p[j, axis]), fontsize=7)
            if np.linalg.norm(mode[j]) > .008:
                ax.arrow(p[j, 0], p[j, axis], mode[j, 0], mode[j, axis], width=.012, color='#b34b9d')
        ax.set(title=label+' view; normalized MODECAR direction', xlabel='x / A', ylabel=('y' if axis == 1 else 'z')+' / A', aspect='equal')
    fig.savefig(RUN / 'mode_review.png', dpi=160)
    plt.close(fig)
    write_json_exclusive(RUN / 'mode_numeric_review.json', dict(norm=float(np.linalg.norm(mode)),
        H50_fraction=float(np.linalg.norm(mode[49])), fixed_max=0.0, H50_vector=mode[49].tolist()))
    print(json.dumps(result))


def seal_review():
    draft = load_json_object(RUN / 'mode_review.json')
    for key in ['status', 'reaction_center_continuity', 'periodic_mapping', 'adsorption_site_continuity',
                'reaction_mechanism_continuity', 'mode_assignment', 'candidate_between_is_and_fs',
                'single_target_process_without_stable_intermediate']:
        draft[key] = 'accepted'
    draft.update(reviewer='Codex numerical and top/side MODECAR inspection',
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        target_reaction_event='H50 surface migration INT06 to MID, not O-H formation',
        visual_evidence=bind(RUN / 'mode_review.png'),
        notes='User explicitly accepts another Dimer after old/new comparison. No TS or SCF-success claim.')
    (RUN / 'mode_review.draft.json').write_bytes((RUN / 'mode_review.json').read_bytes())
    from scripts.artifact_io import write_json
    write_json(RUN / 'mode_review.json', draft)
    report = preflight(RUN, 'dimer')
    assert report['passed'], report['errors']
    request = dict(geometry_file=str(PATH / 'path_geometry_diagnosis.json'),
        analysis_file=str(PARENT / 'analysis.json'), thresholds_file=str(THRESHOLDS),
        preflight_file=str(RUN / 'submission_preflight.json'), climb=False, path_reviewed=True)
    write_json_exclusive(RUN / 'gate_request.review.json', request)
    preliminary = build_decision(RUN / 'gate_request.review.json', RUN / 'execution_gate.review.json')
    source = RUN / 'user_authorization.md'
    source.write_text('# Explicit user authorization\n\n再次拿这个提交dimer吧\n\n'
        'One new VASP Dimer from GPU1635 image05, tangent04-06, 80 MPI ranks, project Dimer profile; '
        'exclude gknew0440. Fresh electronic initialization. No pilot, no old restart, no automatic retry. '
        'User was informed that new peak is close to failed old center and SCF success is unproven.\n', encoding='utf-8')
    authorization = dict(schema_version=1, document_kind='user_execution_authorization',
        calculation_kind='dimer', action='START_DIMER', authorized_at=datetime.now(timezone.utc).isoformat(),
        source=bind(source), target=dict(server_alias='sunboquan-codex', remote_dir=REMOTE),
        workdir_identity=workdir_identity(RUN), bundle_sha256=report['bundle_sha256'],
        evidence_sha256=execution_evidence_sha256(preliminary['EVIDENCE']),
        potcar=dict(source=POTCAR, sha256=POTCAR_HASH, spec_sha256=sha256_file(RUN / 'POTCAR.spec')))
    write_json_exclusive(RUN / 'user_execution_authorization.json', authorization)
    request['authorization_file'] = str(RUN / 'user_execution_authorization.json')
    write_json_exclusive(RUN / 'gate_request.json', request)
    gate = build_decision(RUN / 'gate_request.json', RUN / 'execution_gate_decision.json')
    assert 'START_DIMER' in gate['ALLOWED_ACTIONS'], gate['REASON_CODES']
    for name in ['WAVECAR', 'CHGCAR', 'CHG']:
        assert not (RUN / name).exists()
    subprocess.run(['C:/Program Files/Git/bin/bash.exe', '-n', str(RUN / 'script.lsf')], check=True)
    print(json.dumps(dict(decision=gate['DECISION'], actions=gate['ALLOWED_ACTIONS'],
        bundle_sha256=report['bundle_sha256'], submitted=False)))


def record_submission():
    from scripts.state_manager.models import validate_event
    receipt = load_json_object(RUN / 'submission_record.json')
    assert receipt['status'] == 'SUBMITTED' and receipt['job_id'] == '9781734'
    now = datetime.now(timezone.utc).isoformat()
    event = load_json_object(DEST / 'submission_20260916/submitted_task_state_event.json')
    event.update(event_id='task-int06-mid-dimer9781734-submitted-20260916',
        occurred_at=now, recorded_at=now,
        supersedes=['task-int06-mid-fresh-gpu1635-submitted-20260916'],
        summary='User authorized new Dimer from GPU1635 image05; LSF9781734 submitted, initial PEND.')
    refs = [ROOT / 'docs/reviews/int06_mid_dimer_gpu1635_20260916.md', RUN / 'submission_record.json',
            RUN / 'execution_gate_decision.json', RUN / 'submission_preflight.json',
            RUN / 'user_execution_authorization.json', RUN / 'mode_review.json']
    event['evidence'] = [dict(locator=p.relative_to(ROOT).as_posix(), sha256=sha256_file(p),
        authority='repository_document', observed_at=now) for p in refs]
    event['payload'].update(current_evidence=[
        'GPU1635 completed normally: ordinary ML-NEB 19 steps, maximum NEB force0.088104eV/A, nine images, same-path AQCat audit complete.',
        'Full path reviewed; image05 selected with neighbors04/06. Flat04-05 peak and similarity to failed old center explicitly disclosed.',
        'Canonical parent, mode and submission gates passed; START_DIMER authorized by current user request.',
        'VASP Dimer9781734 submitted on sunboquan-codex; first live scheduler observation PEND. 80ranks, excluding gknew0440.',
        'Project default Dimer profile, SIGMA0.20, EDIFF1e-7, EDIFFG-0.02, NSW300; no old electronic restart files.',
        'Old SCF failure is not proven resolved; no TS or final barrier accepted. No automatic retry.'
    ], one_executable_step='Check9781734 scheduler and actual VASP startup, electronic stability and Dimer force/curvature progress.',
        submission_boundary='One explicit Dimer authorization consumed by9781734. Do not submit another job or restart old SCF branches.',
        authoritative_references=[p.relative_to(ROOT).as_posix() for p in refs])
    validate_event(event)
    target = RUN / 'submitted_task_state_event.json'
    write_json_exclusive(target, event)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'seal', 'record'])
    args = parser.parse_args()
    {'prepare': prepare_candidate, 'seal': seal_review, 'record': record_submission}[args.stage]()
