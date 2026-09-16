"""Preserve bounded failure evidence and project the user-requested path change."""
from datetime import datetime, timezone
import json
import subprocess
from archive.int06_mid_fresh_seed_20260916.prepare import ROOT, DEST, PATH
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.scheduler_evidence import query_lsf_job
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.ts_strategy_engine.execution_gate_cli import build_decision


def main():
    failure = DEST/'retired_scf9757725'
    failure.mkdir(exist_ok=False)
    remote = '~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_scf_chain_20260915/'
    sources = ('output.9757725','A_fixed_density/receipt.json','A_fixed_density/OUTCAR',
               'A_fixed_density/OSZICAR','scf_allocation.json')
    for name in sources:
        target=failure/name.replace('/','_')
        subprocess.run(['scp','sunboquan-codex:'+remote+name,str(target)],check=True,capture_output=True,timeout=45)
    scheduler=query_lsf_job('9757725',stage='diagnostic_static')
    assert scheduler['status']=='EXIT'
    write_json_exclusive(failure/'scheduler.json',scheduler)
    write_json_exclusive(failure/'disposition.json',{
        'decision':'RETIRED_BY_USER_NO_MORE_SCF_RETRIES',
        'reason':'User requested a fresh endpoint-generated GPU seed and VASP coarse NEB fallback.',
        'source_hashes':{p.name:sha256_file(p) for p in failure.iterdir() if p.is_file()},
        'large_vasp_stdout_retained_remote_not_downloaded':True,'structural_root_cause_proven':False})
    thresholds=ROOT/'configs/neb_agent/default_thresholds.yaml'
    diagnose(PATH,['49'],[],thresholds,reaction_pairs=[],expected_interior=7)
    analyze(PATH,thresholds,reaction_indices=[49])
    gate_request={
        'geometry_file':str(PATH/'path_geometry_diagnosis.json'),
        'analysis_file':str(PATH/'neb_analysis.json'),'thresholds_file':str(thresholds),
        'climb':False,'path_reviewed':False}
    write_json_exclusive(PATH/'execution_gate_request.json',gate_request)
    gate=build_decision(PATH/'execution_gate_request.json',PATH/'execution_gate.json')
    assert not gate['SUBMISSION_ALLOWED'] and not gate['ALLOWED_ACTIONS']
    event=load_json_object(ROOT/'docs/reviews/scf_chain_input_review_20260915/submitted_task_state_event.json')
    now=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    event.update(event_id='task-int06-mid-fresh-seed-20260916',occurred_at=now,recorded_at=now,
        supersedes=['task-scf-chain-submitted-20260915'],
        summary='User retired failed SCF-centered path; fresh nine-frame endpoint IDPP seed prepared for GPU review.')
    refs=[ROOT/'docs/reviews/int06_mid_fresh_seed_20260916.md',DEST/'local_preflight.json',
          PATH/'exact_mic_geometry.json',PATH/'execution_gate.json',failure/'disposition.json',failure/'scheduler.json']
    event['evidence']=[dict(locator=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p),
        authority='repository_document',observed_at=now) for p in refs]
    event['payload'].update(current_evidence=[
        '9757725 EXIT; fixed-density stage A failed, no stages B/C; user retired further old-center SCF trials.',
        'Accepted endpoints INT06 9748648 and MID 9737143 retained; no change to accepted MID-to-FS O-H TS.',
        'Fresh endpoint-only full-atom IDPP: 7 internal images, 9 total; no old ML interior copied.',
        'Exact MIC, identity, fixed layer, molecular connectivity, eight dist.pl and nebmovie.pl 0 checks passed.',
        'Adjacent maximum atomic step 0.197171 A; seed remains same migration corridor, not proof of a new mechanism or SCF repair.',
        'MatRIS-primary/AQCat25 exact-path GPU request is draft only; no model, remote preflight or submission.',
        'User-selected fallback: if this GPU route is unusable, prepare VASP ordinary coarse NEB; no mandatory pilot or automatic old-input retry.'
    ],one_executable_step='Review fresh INT06-to-MID seed with user, then finalize runtime bindings and MZ73 no-model preflight for one concrete GPU request.',
        submission_boundary='No executable GPU package or VASP submission gate yet. Exact package review and authorization still required; do not restart retired SCF jobs.',
        authoritative_references=[p.relative_to(ROOT).as_posix() for p in refs])
    event['payload']['done_when']=['Obtain a validated INT06-to-MID migration TS from the reviewed new-path GPU or VASP coarse-NEB branch, then retain compatible barrier and strategy evidence.']
    write_json_exclusive(DEST/'task_state_event.json',event)
    print(json.dumps({'gate':gate['DECISION'],'event':str(DEST/'task_state_event.json')}))


if __name__=='__main__':
    main()
