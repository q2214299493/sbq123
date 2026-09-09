# B1-B7 Independent Acceptance Audit

- CODE_MERGE_READINESS: **NOT_READY_TO_MERGE**
- PRODUCTION_OPERATION_READINESS: **UNVERIFIED**
- Audit status: **STOPPED_ON_BLOCKING_FINDING**, following the explicit stop rule.
- Code finding: **AC-B2-001, P1**. No source repair was performed.

This is an early-stop acceptance report, not a completed whole-repository PASS.
Fresh full tests and exact-candidate remote CI pass, but the authoritative gate
accepts unverified and stale scientific claims. Unfinished independent checks
are listed below; prior completion reports do not substitute for those checks.
Machine-readable evidence, the full changed-file inventory and commit chain are
in [B1_B7_acceptance.json](B1_B7_acceptance.json).

## Candidate and isolation

| Item | Verified value |
| --- | --- |
| Repository | `https://github.com/q2214299493/sbq123.git` |
| Candidate branch | `codex/b7-release-environment` |
| Candidate commit | `7a0b745df96de2762a6f289e9eeda1a3c298fe9d` |
| Candidate tree | `68688cfdb85854deedd815d85690731a4f629ec7` |
| Audit branch | `codex/b1-b7-final-acceptance` |
| Audit inventory time | `2026-09-09T16:29:12.025667+00:00` (2026-09-10 Asia/Shanghai) |
| OS | Windows 11, 10.0.26200, AMD64 |
| Python | 3.13.9, Anaconda distribution |

Fetched into a separate bare clone, then created a disposable worktree from the
verified exact candidate SHA. This clone's `origin` is **sbq123**. The development
checkout's `origin` remains the different `sbq` repository. No developer changes
or remote configuration were touched; no reset, clean or stash was used.

- Candidate: `C:/Users/86177/AppData/Local/Temp/sbq123-final-acceptance`
- Separate clone: `C:/Users/86177/AppData/Local/Temp/sbq123-final-audit.git`
- Logs and audit helpers: `C:/Users/86177/AppData/Local/Temp/sbq123-final-audit-output`

Reproductions used external temporary directories. `PYTHONDONTWRITEBYTECODE=1`,
external `RUFF_CACHE_DIR`, and `PYTEST_ADDOPTS=-o cache_dir=<outside-directory>`
kept validation caches outside candidate source. Wheel/build/venv work was not
started after the blocker. The requested validation command text was unchanged.

## Cumulative history and changed files

All fetched B1-B6 final tips passed `git merge-base --is-ancestor <tip> HEAD`.

| Package branch | Actual final SHA | Ancestor |
| --- | --- | --- |
| B1 execution-lifecycle | `b1c59addbc7d7be64347db66a201dc5841404341` | Yes |
| B2 scientific-contract | `3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c` | Yes |
| B3 evidence-ml-governance | `9f4332f082d4e286ce43c5a137a62ac1e30fa441` | Yes |
| B4 registry-state-management | `fbbb7bb26d28867d9766cc7fca84077fa54cf3d6` | Yes |
| B5 architecture-boundaries | `3a1bb3f461147a7dc9b5df5efca89de621d27f38` | Yes |
| B6 documentation-data-governance | `93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a` | Yes |
| B7 release-environment | `7a0b745df96de2762a6f289e9eeda1a3c298fe9d` | Exact candidate |

`origin/main` and the merge base both resolve to
`5c5fed9b4a0691a893af3d03eaae10636999aa85`.
`origin/main...HEAD`: **60 added, 174 modified, 0 deleted, 0 renamed files**.
The JSON records all 234 paths and the 13-commit chain. No prior package is
missing by ancestry, and there are no deletions of maintained source, tests,
protocols, schemas or historical documents in this comparison. This inventory
does not certify the semantics of every modified file.

## AC-B2-001: scientific-claim gate accepts absent and stale evidence

**P1; B2 scientific acceptance / B3 evidence authority.**

Without DIMER, VFA, structure, contract or energy evidence files, boolean
summaries cause the authoritative gate to return `VALIDATED_TS`, set
`TS_CLAIM_ALLOWED=true`, and permit `APPROVE_TS_CANDIDATE` and
`REPORT_FINAL_BARRIER`. The real CLI application binds summary file hashes, but
changing its validation summary to Grade C / failed DIMER acceptance still
leaves both issued actions accepted by `require_action()`.

### Locations and cause

- `scripts/ts_strategy_engine/execution_evidence.py:211`, `validated_ts`:
  trusts `frequency_structure_hash_valid=True` and
  `dimer_technical_acceptance=True` without establishing current scientific
  structure/file evidence.
- `scripts/ts_strategy_engine/execution_path_rules.py:269`, `progress_decision`:
  turns that predicate into TS approval and another boolean into barrier-report
  permission.
- `scripts/ts_strategy_engine/execution_evidence.py:280`, `bind_execution`:
  catches invalid/missing authorization and retains actions outside
  `EXECUTION_ACTIONS`, including TS approval and barrier reporting. This failure
  path does not establish their current scientific source bindings.
- `scripts/ts_strategy_engine/execution_gate.py:82`, `require_action`:
  recomputes the same decision and checks its self-consistent state hash, without
  requiring current validation source evidence for those scientific actions.
- `scripts/ts_strategy_engine/execution_gate_cli.py:12`, `build_decision`:
  the actual CLI application producer used in the stale-summary reproduction.

The direct API returned this observed subset:

```json
{
  "DECISION": "VALIDATED_TS",
  "TS_CLAIM_ALLOWED": true,
  "ALLOWED_ACTIONS": ["APPROVE_TS_CANDIDATE", "REPORT_FINAL_BARRIER"],
  "execution_authorization": null,
  "execution_authorization_error": "explicit execution authorization is missing or invalid",
  "source_bindings": {},
  "evidence_binding": null
}
```

### Reproduction

Run from the isolated candidate; all created files are synthetic summaries in a
temporary directory. Production functions are not mocked. No database, real
scientific output or scheduler is involved.

```python
import tempfile
from pathlib import Path
from scripts.artifact_io import write_json
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.execution_gate import require_action

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write_json(root / "geometry.json", {"status": "PASS"})
    write_json(root / "analysis.json", {
        "path_binding_valid": True, "image_sequence_complete": True})
    (root / "thresholds.yaml").write_text("{}\n")
    write_json(root / "validation.json", {
        "source_method": "dimer", "frequency_grade": "A",
        "frequency_structure_hash_valid": True,
        "dimer_technical_acceptance": True,
        "compatible_final_energy_barrier_valid": True})
    request = write_json(root / "request.json", {
        "geometry_file": "geometry.json", "analysis_file": "analysis.json",
        "thresholds_file": "thresholds.yaml",
        "validation_file": "validation.json",
        "climb": False, "path_reviewed": False})
    gate = root / "gate.json"
    decision = build_decision(request, gate)
    print(decision["DECISION"], decision["TS_CLAIM_ALLOWED"],
          decision["ALLOWED_ACTIONS"])
    write_json(root / "validation.json", {
        "frequency_grade": "C", "dimer_technical_acceptance": False})
    for action in ("APPROVE_TS_CANDIDATE", "REPORT_FINAL_BARRIER"):
        print(action, require_action(
            gate, action, decision["state_sha256"])["DECISION"])
```

Observed output from the equivalent executed reproduction:

```text
VALIDATED_TS True ['APPROVE_TS_CANDIDATE', 'REPORT_FINAL_BARRIER']
APPROVE_TS_CANDIDATE VALIDATED_TS
REPORT_FINAL_BARRIER VALIDATED_TS
```

Both actions were also checked successfully before invalidating the summary.
The CLI decision had geometry, analysis, thresholds and validation source
bindings. Both reproduction processes exited 0: successful defect reproduction,
not a scientific PASS.

**Expected:** missing scientific evidence cannot authorize a validated TS or
barrier claim; changed/failing current validation evidence invalidates those
actions. Hash consistency establishes identity, not scientific validity.

**Why blocking:** the final audit expressly rejects false scientific PASS
states. The public authoritative gate issues scientific claims without current
evidence, regardless of whether a downstream persistence boundary might reject
them. Green tests cannot waive that requirement.

**Scope:** no database insertion/export bypass or production corruption was
demonstrated. `scripts/ts_strategy_engine/evidence.py:249`,
`record_ts_validation`, retains additional payload, file and saddle/job checks.
No submission permission or external scientific action was exercised. The
boolean predicate is already present in `origin/main`; this is an unresolved
acceptance gap, not a demonstrated new B1 duplicate-submission regression.

**Recommended repair package:** a separately authorized B2/B3 scientific-claim
authority closure, reusing existing scientific validators and current
structure/contract/source binding. Add regressions through `build_decision` and
`require_action` for absent and stale validation evidence. Preserve thresholds,
DIMER policy and B1 submission behavior. No such repair was made in this audit.

## Acceptance matrix

The permitted verdict vocabulary lacks NOT_ASSESSED. In an **incomplete** row,
FAIL means required independent acceptance was not established after the stop;
it does not allege another package defect. AC-B2-001 is the sole P1 code finding.
No package PASS is inferred from aggregate tests.

| Package | Verdict | Evidence / completion | Severity, location and blocker |
| --- | --- | --- | --- |
| B1 Execution | FAIL | Incomplete; reservation, binding, path and complete-manifest code read. No separate submission defect demonstrated. | Not separately rated; audit stop rule after AC-B2-001 leaves focused acceptance incomplete. |
| B2 Scientific Contract | FAIL | AC-B2-001 reproduced at real API and CLI boundaries. | P1, locations above; false scientific PASS. |
| B3 Evidence/ML | FAIL | Incomplete; claim-evidence weakness confirmed, full lifecycle/promotion/leakage audit not completed. | No separate ML persistence defect alleged; AC-B2-001 and stop rule leave acceptance incomplete. |
| B4 Registry/State | FAIL | Incomplete; TS persistence checks read, complete transaction/recovery review not performed. | Not separately rated; required independent registry acceptance incomplete after stop. |
| B5 Architecture | FAIL | Incomplete; gate/decision/evidence ownership inspected, whole graph/cycles/duplication audit not completed. | Not separately rated; required architecture acceptance incomplete after stop. |
| B6 Documentation/Data | FAIL | Incomplete; authority entry points read, independent readiness-twice/link commands not run. | Not separately rated; required documentation acceptance incomplete after stop. |
| B7 Release/Environment | FAIL | Incomplete locally; exact-candidate remote wheel CI succeeds, fresh local artifact audit not started. | Not separately rated; required independent artifact acceptance incomplete after stop. |

## Local validation and test quality

| Check | Actual result |
| --- | --- |
| `python -m ruff check scripts modules tests` | Exit 0; All checks passed! |
| `python -m pytest -o addopts= -q` | Exit 0; **1097 passed in 281.00s (0:04:40)** |
| `git diff --check` on candidate | Exit 0 |
| Direct authoritative gate reproduction | Defect reproduced; process exit 0 |
| CLI stale-summary reproduction | Defect reproduced; process exit 0 |
| Separate focused B1-B7 commands | NOT_RUN_STOPPED_ON_BLOCKER; no focused count claimed |
| Fresh wheel/clean venv/parity/member inspection | NOT_RUN_STOPPED_ON_BLOCKER |
| Readiness twice / document-governance/link commands | NOT_RUN_STOPPED_ON_BLOCKER |

The full suite began before the blocker and was allowed to finish. The observed
count is 1097; no audit filters, test edits, removals or skips were introduced.
It agrees with the prior B7 count, but this fresh run is the evidence. Package
tests included in the full suite are not claimed as separate focused runs.

`tests/test_b2_scientific_contract.py::test_ts_acceptance_requirements_preserved`
exercises the boolean predicate. `authoritative_gate` / `barrier_validation` in
`tests/test_ts_strategy_engine.py` produce successful gates from summary flags.
B2.1 pipeline tests independently exercise real bound DIMER/VFA chains, including
stale/cross-saddle evidence, but do not cover this scientific-claim gate route.
The audit reproductions exercise the real producer and action validator without
mocking their behavior. Live HPC tests are neither required nor performed.

## Independent remote CI

Queried GitHub Actions REST API using the exact candidate `head_sha`, then its
job endpoint. The candidate workflow specifies Python 3.11 for every job.
`REMOTE_CI_INDEPENDENT_CHECK=SUCCESS`; this is independent of B7 report text.

Run [34374926984](https://github.com/q2214299493/sbq123/actions/runs/34374926984):
exact candidate SHA, completed/success.

| Actual job | Python | Independent result |
| --- | --- | --- |
| validate (Ubuntu) | 3.11 | SUCCESS |
| engineering (ubuntu-latest) | 3.11 | SUCCESS |
| engineering (windows-latest) | 3.11 | SUCCESS |
| wheel (ubuntu-latest) | 3.11 | SUCCESS |
| wheel (windows-latest) | 3.11 | SUCCESS |

The JSON preserves run/job URLs. Remote success is separate from local results
and does not negate the independently reproduced defect.

## Remaining inspection scope

**Source integrity:** the complete tracked-path/size inventory covered 1297
files. No file exceeded 1 MB; no named POTCAR/WAVECAR/CHGCAR/private-key/database/
model-weight/build/egg-info/dist-info/pycache path was detected. Content-level
credential/binary inspection and release/public exclusion checks were not
completed after the blocker, so no complete sensitive-artifact PASS is claimed.
Existing published calculation snapshots were not classified as newly introduced
runtime data merely because of their directory names.

**Architecture:** no complete maintained import graph, cycle/duplicate-owner or
unreferenced-file verdict is issued. Actual gate, evidence and submission owners
were read; repeated trust-boundary validation was not labeled duplication.

**Scientific preservation:** the cumulative parameter/protocol comparison was
not completed. No conclusion is issued about every ENCUT, KPOINTS, smearing,
force, frequency, DIMER, reaction-family or energy-convention change. This audit
changed no scientific parameter, source, schema, historical evidence or output.

**Registry/state:** TS recording performs additional checks after `require_action`;
no complete registry acceptance or database mutation is claimed. The known live
task-current conflict was not re-queried in the dirty checkout or resolved.

**Documentation/data:** current/recorded-state governance entry points were read.
Independent generator determinism, document/link validation and full authority
review remain incomplete; no previous report supplies a substituted PASS.

## Operational state and production limitations

The corrected read-only startup command was:

```text
python -m scripts.state_manager.cli --root . audit --phase start
exit 1: errors=1 warnings=1 review_required=2
ERROR managed_projection_drift:
  docs/06_MODULE_MAP.md#module_row:transition_state_search
WARNING external_worktree_review:
  isolated bare clone requires ownership review
```

An initial command put global `--root` after the subcommand and returned an
argument error (exit 2); it was corrected before evaluating audit results.
The isolated source projection drift is an operational reconciliation item,
not the reason for the P1 code verdict. No proposal/event was created, accepted
or changed. `sync --safe-only` was not run because the explicit audit restriction
allows only the two report files and prohibits resolving state conflicts.

Production schema deployment, live scheduler state, real credentials/HPC, GPU
deployment, VASP operation, scientific performance and task reconciliation remain
**UNVERIFIED**. Source schema support and software tests do not prove deployment
or scientific validity.

`external_actions_performed = 0` for real external scientific actions. No SSH,
scientific scheduler commands, real model inference/training, VASP execution,
production database/Excel write, migration or remote scientific path mutation
occurred. Requested Git/GitHub audit and publication networking is outside this
count.

## Task changes and disposition

Only these two files are intentional repository changes:

1. `reports/refactor_audit/B1_B7_acceptance_report.md`
2. `reports/refactor_audit/B1_B7_acceptance.json`

The candidate worktree was clean after tests/reproductions and before writing
the reports. JSON verdicts match this report. Publication is limited to
`codex/b1-b7-final-acceptance` on `q2214299493/sbq123`. No merge, main update,
source repair or new phase is performed.

The next step is a separately authorized scientific-claim boundary repair,
followed by a fresh final acceptance audit. This task stops after publishing
these two audit artifacts.
