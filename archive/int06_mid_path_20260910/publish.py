"""Export only reviewed task artifacts to the existing independent release branch."""
import shutil
import subprocess
from pathlib import Path

from archive.int06_mid_path_20260910.review_path import BASE, PATH, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.submission import InputBundle
from scripts.ts_strategy_engine.execution_gate import validate_decision

RELEASE = Path('C:/Users/86177/AppData/Local/Temp/sbq123-int06-review-state-20260910')


def main() -> None:
    assert subprocess.check_output(['git','status','--porcelain'],cwd=RELEASE,text=True).strip() == ''
    assert subprocess.check_output(['git','branch','--show-current'],cwd=RELEASE,text=True).strip() == 'codex/int06-review-state-20260910'
    InputBundle.from_preflight(load_json_object(PATH/'submission_preflight.json')).verify(PATH)
    gate = load_json_object(PATH/'execution_gate.json')
    validate_decision(gate)
    assert gate['ALLOWED_ACTIONS'] == [] and not gate['SUBMISSION_ALLOWED']
    assert load_json_object(PATH/'incar_validation.json')['status'] == 'PASS'
    assert not (PATH/'submission_attempt.json').exists()
    write_json_exclusive(BASE/'verification.json', {
        'input_bundle_current':True,'canonical_execution_gate_valid':True,
        'incar_validation':'PASS','submission_reserved':False,
        'python_compileall':'PASS','ruff':'PASS',
        'state_projection':'approved prior science and safe-only procedural projections applied',
        'repo_state_end_audit':{'errors':0,'warnings':13},
        'repo_state_global_sync':'blocked: unrelated classified sbq_catalyst_agent_workflow.egg-info/PKG-INFO changed',
    })
    inputs = sorted(p for p in BASE.rglob('*') if p.is_file())
    assert all(p.stat().st_size < 2_000_000 and p.name not in {'POTCAR','OUTCAR','WAVECAR','CHGCAR'} for p in inputs)
    # The species specification contains no potential; preserve it under a nonignored name.
    spec = PATH/'POTCAR.spec'
    (PATH/'potcar_species.txt').write_bytes(spec.read_bytes())
    inputs = [p for p in inputs if p != spec] + [PATH/'potcar_species.txt']
    inputs += sorted((ROOT/'archive/int06_mid_path_20260910').glob('*.py'))
    inputs += [ROOT/p for p in [
        'tasks/current_task.md','docs/02_CURRENT_STATE.md','data/state_handoff/projection_manifest.json',
        'docs/reviews/int06_mid_path_prepared_20260910.md',
        'modules/state_handoff/events/review-1bc6b891b7379151655f5764.json',
        'modules/state_handoff/events/review-0da66ca672427e51cc0f505a.json',
        'modules/state_handoff/events/task-int06-mid-inputs-prepared-20260910.json',
        'modules/state_handoff/events/state-int06-mid-inputs-prepared-20260910.json',
    ]]
    files = {p.relative_to(ROOT).as_posix():sha256_file(p) for p in inputs}
    write_json_exclusive(BASE/'release_manifest.json', {'files':files,'potcar_spec_export':'plan/path_candidate/potcar_species.txt'})
    inputs.append(BASE/'release_manifest.json')
    for source in inputs:
        destination = RELEASE/source.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        assert sha256_file(source) == sha256_file(destination)
    print(f'{len(inputs)} task files copied and byte-verified')


if __name__ == '__main__':
    main()
