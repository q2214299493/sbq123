"""Publish this GPU preparation only, preserving unrelated workspace edits."""
import re
import shutil
import subprocess
from pathlib import Path

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

RELEASE = Path('C:/Users/86177/AppData/Local/Temp/sbq123-int06-review-state-20260910')


def main():
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=RELEASE,text=True).strip()
    assert subprocess.check_output(['git','branch','--show-current'],cwd=RELEASE,text=True).strip()=='codex/int06-review-state-20260910'
    for name, block in [('tasks/current_task.md','current_task'),
                        ('docs/02_CURRENT_STATE.md','active-fe-110-co-dissociation-test-current-gate')]:
        expression = '<!-- state-handoff:start '+block+' -->.*?<!-- state-handoff:end '+block+' -->'
        def strip(text):
            return re.sub(expression,'BLOCK',text,flags=re.S)
        assert strip((ROOT/name).read_text(encoding='utf-8')) == strip((RELEASE/name).read_text(encoding='utf-8'))
    projection = 'data/state_handoff/projection_manifest.json'
    before = load_json_object(RELEASE/projection)['projections']
    after = load_json_object(ROOT/projection)['projections']
    assert {key for key in set(before)|set(after) if before.get(key)!=after.get(key)} == {
        'tasks/current_task.md#current_task',
        'docs/02_CURRENT_STATE.md#active-fe-110-co-dissociation-test-current-gate',
    }
    package = BASE/'payload'
    manifest = load_json_object(package/'payload_manifest.json')
    for name, digest in manifest['files'].items():
        assert sha256_file(package/name)==digest
    remote = load_json_object(BASE/'remote_preflight.json')
    assert remote['status']=='PASS' and remote['payload_manifest_sha256']==sha256_file(package/'payload_manifest.json')
    write_json_exclusive(BASE/'verification.json',{
        'local_payload_preflight':'PASS','remote_no_model_preflight':'PASS',
        'payload_files_byte_verified':len(manifest['files']),
        'tests':{'tests/test_dual_model_ml_neb.py':{'passed':17,'exit_code':0}},
        'python_syntax':'PASS','ruff':'PASS','new_gpu_jobs_submitted':0,'new_vasp_jobs_submitted':0,
        'state_task_and_current_gate':'safe-only projections applied',
        'repository_audit':{'errors':0,'warnings':13},
        'global_sync_blocker':'unrelated PKG-INFO classification hash changed',
    })
    files = [p for p in BASE.rglob('*') if p.is_file() and p.suffix not in {'.tar','.pyc'} and '__pycache__' not in p.parts]
    files += list((ROOT/'archive/int06_mid_gpu_20260910').glob('*.py'))
    files += [ROOT/name for name in [
        'tasks/current_task.md','docs/02_CURRENT_STATE.md',projection,
        'docs/reviews/int06_mid_gpu_prepared_20260910.md',
        'modules/state_handoff/events/task-int06-mid-gpu-prepared-20260910.json',
        'modules/state_handoff/events/task-int06-mid-gpu-prepared-20260910-v2.json',
        'modules/state_handoff/events/state-int06-mid-gpu-prepared-20260910.json',
    ]]
    assert all(p.stat().st_size<1_000_000 for p in files)
    hashes = {p.relative_to(ROOT).as_posix():sha256_file(p) for p in files}
    write_json_exclusive(BASE/'release_manifest.json',{'files':hashes})
    files.append(BASE/'release_manifest.json')
    for source in files:
        target = RELEASE/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        assert sha256_file(target)==sha256_file(source)
    print(f'{len(files)} task-owned files exported and byte-verified')


if __name__=='__main__':
    main()
