"""Export GPU1512 authorization, failure and registry receipts only."""
import re
import shutil
import subprocess
from pathlib import Path

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

RELEASE=Path('C:/Users/86177/AppData/Local/Temp/sbq123-int06-review-state-20260910')


def main():
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=RELEASE,text=True).strip()
    assert subprocess.check_output(['git','branch','--show-current'],cwd=RELEASE,text=True).strip()=='codex/int06-review-state-20260910'
    for name,block in [('tasks/current_task.md','current_task'),
                       ('docs/02_CURRENT_STATE.md','active-fe-110-co-dissociation-test-current-gate')]:
        pattern='<!-- state-handoff:start '+block+' -->.*?<!-- state-handoff:end '+block+' -->'
        assert re.sub(pattern,'BLOCK',(ROOT/name).read_text(encoding='utf-8'),flags=re.S)==re.sub(
            pattern,'BLOCK',(RELEASE/name).read_text(encoding='utf-8'),flags=re.S)
    write_json_exclusive(BASE/'submission_verification.json',{
        'submission_dry_run':'READY','scheduler_job_id':'1512','scheduler_terminal_state':'FAILED',
        'scheduler_exit_code':'3:0','model_steps_performed':0,
        'root_cause':'assigned_GPU0_free_memory_7465_MiB_below_guard_12000_MiB',
        'automatic_retry_performed':False,'vasp_submission_performed':False,
        'registry':{'inserted':37,'updated':0,'files':33,'history':['SUBMITTED','FAILED'],
                    'quick_check':'ok','foreign_key_violations':0},
        'python_syntax':'PASS','ruff':'PASS','shell_guard_syntax':'PASS',
        'state_projections':'task and current state updated',
        'pending_error_log_proposal':'proposal-ecda1736d78b9c6e1744f752',
        'global_sync_blocker':'unrelated PKG-INFO classification hash changed',
    })
    previous=load_json_object(BASE/'release_manifest.json')['files']
    paths=[p for p in BASE.rglob('*') if p.is_file() and p.suffix not in {'.tar','.pyc'}
           and '__pycache__' not in p.parts and p.name!='release_manifest.json'
           and p.relative_to(ROOT).as_posix() not in previous]
    paths += [p for p in (ROOT/'archive/int06_mid_gpu_20260910').glob('*.py')
              if p.relative_to(ROOT).as_posix() not in previous]
    paths += [ROOT/name for name in ['tasks/current_task.md','docs/02_CURRENT_STATE.md',
        'data/state_handoff/projection_manifest.json','docs/reviews/int06_mid_gpu1512_startup_failure_20260910.md',
        'modules/state_handoff/events/task-gpu1512-startup-failed-20260910.json',
        'modules/state_handoff/events/state-gpu1512-startup-failed-20260910.json',
        'modules/state_handoff/events/error-gpu1512-startup-memory-20260910.json']]
    assert all(p.stat().st_size<1_000_000 for p in paths)
    write_json_exclusive(BASE/'submission_release_manifest.json',{
        'files':{p.relative_to(ROOT).as_posix():sha256_file(p) for p in paths}})
    paths.append(BASE/'submission_release_manifest.json')
    for source in paths:
        target=RELEASE/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        assert sha256_file(target)==sha256_file(source)
    print(f'{len(paths)} task-owned submission/failure files exported')


if __name__=='__main__':
    main()
