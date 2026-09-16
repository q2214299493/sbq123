"""Record one successful submission without changing or resubmitting it."""
from datetime import datetime, timezone
import json
import subprocess

from archive.int06_mid_fresh_seed_20260916.gpu_submit import LOCAL, REMOTE, SSH
from archive.int06_mid_fresh_seed_20260916.prepare import ROOT, DEST
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.state_manager.models import validate_event


def main():
    receipt = load_json_object(LOCAL / 'submit.result.json')
    assert str(receipt['job_id']) == '1635' and receipt['status'] == 'SUBMITTED'
    checkpoint = LOCAL / 'startup_checkpoint.json'
    command = ("squeue -h -j 1635 -o '%i|%T|%M|%R'; "
               f"cat {REMOTE}/gpu_binding.json")
    result = subprocess.run(SSH + [command], capture_output=True, text=True,
                            timeout=40, check=True)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    write_json_exclusive(checkpoint, {'observed_at': now,
        'source': 'MZ73 squeue and job-owned gpu_binding.json',
        'command': command, 'stdout': result.stdout, 'stderr': result.stderr,
        'returncode': result.returncode})
    event = load_json_object(DEST / 'task_state_event.json')
    event.update(event_id='task-int06-mid-fresh-gpu1635-submitted-20260916',
        occurred_at=now, recorded_at=now,
        supersedes=['task-int06-mid-fresh-seed-20260916'],
        summary='Reviewed fresh nine-frame seed submitted once as MZ73 GPU job 1635.')
    refs = [ROOT / 'docs/reviews/int06_mid_fresh_gpu1635_20260916.md',
            LOCAL / 'submit.result.json', LOCAL / 'remote_preflight.result.json',
            LOCAL / 'execution/authorization.json', checkpoint]
    event['evidence'] = [dict(locator=p.relative_to(ROOT).as_posix(),
        sha256=sha256_file(p), authority='repository_document', observed_at=now)
        for p in refs]
    event['payload'].update(current_evidence=[
        'User accepted the fresh INT06-to-MID seed and authorized one GPU submission.',
        'Local and remote payload/model/geometry preflights passed; 17 related tests passed.',
        'MZ73 submission 1635 succeeded; startup checkpoint records live scheduler state and assigned GPU.',
        'Nine frames, seven internal; MatRIS ordinary ML-NEB followed by AQCat25 same-path audit.',
        'One GPU, four CPUs, 40 GB RAM, six hours, maximum 400 optimization steps; no requeue.',
        'No convergence, TS acceptance or barrier claim; old SCF repair branch remains retired.',
        'If GPU path is unusable, prepare reviewed VASP ordinary coarse NEB, not another old-center SCF retry.'
    ], one_executable_step='Check job 1635 and collect its complete path and producer evidence for work-side review when finished.',
        submission_boundary='One authorized GPU submission consumed. No automatic GPU retry or VASP submission; no new monitoring automation.',
        authoritative_references=[p.relative_to(ROOT).as_posix() for p in refs])
    validate_event(event)
    target = LOCAL / 'submitted_task_state_event.json'
    write_json_exclusive(target, event)
    print(json.dumps({'event': str(target), 'checkpoint': result.stdout}))


if __name__ == '__main__':
    main()
