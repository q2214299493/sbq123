"""Project observed failure without changing earlier scientific acceptance."""
from copy import deepcopy
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.state_manager.models import validate_event


def main():
    now=datetime.now(timezone.utc).isoformat()
    report=ROOT/'docs/reviews/int06_mid_gpu1512_startup_failure_20260910.md'
    evidence=[{'locator':p.relative_to(ROOT).as_posix(),'sha256':sha256_file(p),
               'authority':'repository_document','observed_at':now} for p in
              [report,BASE/'checkpoint_job1512/checkpoint.json',BASE/'registry_1512_receipt.json']]
    fact=('GPU1512 submitted under explicit user authority, then Slurm FAILED with ExitCode=3:0 at startup. '
          'Allocated GPU0 had 7465 MiB free <12000 MiB; guard exited before model execution. '
          'No ML-NEB steps, predictions, automatic retry or VASP submission. Failed job/input/evidence records registered.')
    next_action=('Resolve the assigned-GPU free-memory condition (at least 12000 MiB), then obtain explicit '
                 'authority for one new attempt of the unchanged reviewed GPU request. Preserve job1512 failure; '
                 'do not rerun the existing submission driver or override scheduler-assigned devices.')
    for kind,previous in [('task','task-int06-mid-gpu-prepared-20260910-v2'),
                          ('state','state-int06-mid-gpu-prepared-20260910')]:
        event=deepcopy(load_json_object(ROOT/'modules/state_handoff/events'/(previous+'.json')))
        event.update(event_id=kind+'-gpu1512-startup-failed-20260910',supersedes=[previous],
                     occurred_at=now,recorded_at=now,summary='GPU1512 accepted by Slurm but exited before model execution; retain failure evidence.')
        event['evidence'].extend(evidence)
        payload=event['payload']
        facts=payload['current_evidence'] if kind=='task' else payload['facts']
        facts[-2]='No Hessian, complete migration barrier or new VASP result established; the GPU1512 attempt produced no model output.'
        facts[-1]=fact
        if kind=='task':
            payload['one_executable_step']=next_action
            payload['submission_boundary']='One submitted GPU attempt failed before model execution. Automatic retry and VASP submission remain unauthorized; another attempt requires explicit authority.'
            payload['authoritative_references'].append(report.relative_to(ROOT).as_posix())
        else:
            payload['next_action']=next_action
            payload['title']='Active Gate - 2026-09-10 GPU1512 Startup Failed; Assigned GPU Memory Blocker'
        write_json_exclusive(BASE/(kind+'_1512_event.json'),validate_event(event))
    error={'schema_version':1,'event_id':'error-gpu1512-startup-memory-20260910','event_type':'error_opened',
           'entity':{'kind':'error','id':'gpu1512-startup-memory','module':'transition_state_search'},
           'occurred_at':now,'recorded_at':now,'summary':'Allocated GPU memory below startup threshold; no model execution.',
           'payload':{'markdown':'### GPU1512 — 分配卡显存不足（2026-09-10）\n\n'
                      '- Slurm FAILED，ExitCode=3:0；GPU0 空闲 7465 MiB，小于启动门槛 12000 MiB。\n'
                      '- guard 在加载模型前退出，无 ML-NEB 步骤；不属于模型误差或训练证据。\n'
                      '- 输入及失败证据已登记；尚未重提。需实际分配卡显存满足门槛，并取得单次重提授权。\n'
                      '- 证据：docs/reviews/int06_mid_gpu1512_startup_failure_20260910.md。\n'},
           'evidence':evidence,'review':{'required':True,'reason_codes':['unresolved_runtime_failure_log_entry'],'status':'pending'},
           'supersedes':[]}
    write_json_exclusive(BASE/'error_1512_event.json',validate_event(error))
    print('Factual current-state updates and separate error-log review event prepared')


if __name__=='__main__':
    main()
