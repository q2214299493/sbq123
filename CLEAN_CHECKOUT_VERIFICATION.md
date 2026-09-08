# Clean Checkout Verification

Date: 2026-07-27

Run this only after the proposed logical commits have been manually created in
a separate clean clone. It performs no SSH, scheduler, migration, database
write, VASP, or NEB action.

## 1. Clone and select the reviewed commit

```powershell
git clone <REPOSITORY_URL> work-clean
Set-Location work-clean
git checkout <REVIEWED_COMMIT_OR_BRANCH>
git status --short
```

`git status --short` must be empty. Record the parent of the first logical
commit for scope comparison:

```powershell
$BASE_COMMIT = '<PRE_INTEGRATION_COMMIT>'
```

## 2. Verify prohibited paths were not integrated

```powershell
git diff --name-only "$BASE_COMMIT..HEAD" -- `
  calculations outputs reports data `
  tasks/current_task.md tasks/backlog.md `
  docs/02_CURRENT_STATE.md docs/03_DECISIONS_LOG.md docs/04_ERROR_LOG.md `
  docs/05_FILE_INDEX.md docs/06_MODULE_MAP.md docs/13_WORK_HANDOFF.md
```

Expected output: empty.

Also reject common runtime/generated patterns:

```powershell
$changed = git diff --name-only "$BASE_COMMIT..HEAD"
$forbidden = $changed | Select-String -Pattern `
  '(^|/)(__pycache__|\.pytest_cache|runtime|runs?|output|outputs|calculations|data)(/|$)|\.(sqlite3?|db|pyc|pkl|npz|out|log)$'
if ($forbidden) { $forbidden; throw 'Forbidden runtime/generated path in integration commits' }
```

The formal `artifacts/*baseline*` and audit reports are versioned review
evidence, not calculation output.

## 3. Verify final release manifests

```powershell
@'
from pathlib import Path
import hashlib

root = Path(".").resolve()
baseline = root / "artifacts" / "final_release_baseline"
inputs = [
    "parent_review_baseline_v2_sha256.txt",
    "production_source_manifest.txt",
    "test_manifest.txt",
    "config_manifest.txt",
    "governance_manifest.txt",
    "blocked_migration_manifest.txt",
    "documentation_manifest.txt",
]

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

errors = []
for name in inputs:
    manifest = baseline / name
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        expected_hash, expected_size, _git_status, relative = line.split("\t")
        target = root / relative
        if (
            not target.is_file()
            or target.stat().st_size != int(expected_size)
            or sha256(target) != expected_hash
        ):
            errors.append(f"{name}: {relative}")

for line in (baseline / "final_release_sha256.txt").read_text(
    encoding="utf-8"
).splitlines():
    if not line or line.startswith("#"):
        continue
    expected_hash, expected_size, _git_status, relative = line.split("\t")
    target = root / relative
    if target.stat().st_size != int(expected_size) or sha256(target) != expected_hash:
        errors.append(f"final_release_sha256.txt: {relative}")

if errors:
    raise SystemExit("\n".join(errors))
print("FINAL_RELEASE_BASELINE=VALID")
'@ | python -
```

Expected result: `FINAL_RELEASE_BASELINE=VALID`.

## 4. Confirm migration remains review-only

```powershell
Get-Content artifacts/final_release_baseline/blocked_migration_manifest.txt
Select-String -Path MIGRATION_REVISION_BACKLOG.md,FINAL_BACKLOG.md,FINAL_ARCHITECTURE.md `
  -Pattern 'REVISED|PROHIBITED|REQUIRES_EXPLICIT_AUTHORIZATION'
```

Do not run either SQL file. Confirm no code change implicitly enables it:

```powershell
rg -n "apply_ts_endpoint_migration|001_ts_endpoint_records" scripts modules tests
python -m pytest -q -ra tests/test_structure_purpose_manager.py tests/test_ts_endpoint_contracts.py
```

The expected references are the guarded API, temporary-database contract tests,
and review documentation. Adapter initialization and ordinary CRUD must not
call the migration.

## 5. Install and run static/full tests

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,adsmind,neb]"
python -m ruff check scripts modules tests
python -m pytest -q -ra
```

Acceptance:

- at least 274 tests;
- all pass;
- skip/xfail 0;
- Ruff passes.

## 6. Focused behavior suites

```powershell
python -m pytest -q -ra `
  tests/test_execution_gate_compatibility.py `
  tests/test_neb_execution_gate.py `
  tests/test_external_command_boundaries.py `
  tests/test_neb_submission.py `
  tests/test_alpha_fe_bulk_submission.py `
  tests/test_artifact_io.py

python -m pytest -q -ra `
  tests/test_neb_path_quality_control.py `
  tests/test_neb_path_quality_entrypoints.py `
  tests/test_neb_pilot_validation.py `
  tests/test_ts_strategy_engine.py

python -m pytest -q -ra `
  tests/test_structure_purpose_manager.py `
  tests/test_ts_endpoint_contracts.py
```

## 7. CLI help acceptance

```powershell
python -m scripts.ts_strategy_engine.cli --help
python -m scripts.ts_strategy_engine.cli active-learning --help
python -m scripts.ts_strategy_engine.execution_gate_cli --help
python -m scripts.neb_agent.path_quality_cli --help
python -m scripts.neb_agent.submission --help
python -m scripts.neb_agent.remote_monitor --help
python -m scripts.neb_agent.pilot_validation --help
python -m scripts.adsmind_lite.plan_adsorption_candidates --help
python -m scripts.aqcat25_handoff --help
```

Every command must return exit code 0 and must not contact an external system.

## 8. Final cleanliness

```powershell
git status --short
git fsck --no-dangling
```

`git status --short` must remain empty. `git fsck` must report no repository
integrity error.
