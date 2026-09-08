# Phase 2A.1 Closure Report

Date: 2026-07-27  
Verdict: **PASS**

## Closure conditions

| Condition | Evidence | Result |
| --- | --- | --- |
| Governance identity registered | `GOVERNANCE_DOCUMENT_DECISION.md` records `AGENT_RULE_TS_ENDPOINT.md` as `FORMAL_GOVERNANCE_DOCUMENT` with a bounded authority scope. | PASS |
| Migration remains blocked | `MIGRATION_REVISION_BACKLOG.md` records both SQL files as `FORMAL_MIGRATION`, `BLOCKED`, `PROHIBITED`, `NEEDS_REVISION`. | PASS |
| Historical v1 remains immutable | Pre/post SHA-256 values match for all three `artifacts/refactor_changeset/` files and `CHANGESET_MANIFEST.md`. | PASS |
| Additive v2 established | The seven exact files exist under `artifacts/review_baseline_v2/`; the parent points to v1 and the final hash file binds all v2 manifests and Phase 2A.1 reports. | PASS |
| Repository contract remains exact | Only three named artifact directories and their 3/5/7 named files are accepted; four focused regression tests cover acceptance and rejection boundaries. | PASS |
| Production source unchanged in this phase | The only tracked file edited in Phase 2A.1 is `tests/test_repository_contracts.py`; all other additions are reports or review-baseline files. | PASS |

## Historical-chain evidence

| Path | Frozen SHA-256 |
| --- | --- |
| `artifacts/refactor_changeset/tracked_changes.patch` | `187b5800b19c45cee8aa72e4f0d6f066c9af924e117659c167bf76844d170030` |
| `artifacts/refactor_changeset/untracked_source_manifest.txt` | `e8c3bdeb71e4214fc2e2ae17578b3952f33788dad4db36dd1b08f062136ecd5e` |
| `artifacts/refactor_changeset/changeset_sha256.txt` | `4e6e65ef073580b91e8ee971c77f096a478485e92ac8f7001c106806121c6efc` |
| `CHANGESET_MANIFEST.md` | `9d7a2bab9d46fc971eb24a17b59918c7249d32b2c36512cce6c9056df50f14a5` |

The old patch's inability to reverse-apply to the current repository-contract
test is an accepted historical fact. The old patch itself is unchanged, the
two exact contract expansions are documented, and v2 binds the current test.

## Validation executed

| Command | Exit code | Actual result |
| --- | ---: | --- |
| `python -m ruff check tests/test_repository_contracts.py` | 0 | Passed |
| `python -m pytest tests/test_repository_contracts.py -q -ra` | 0 | 17/17 passed |
| `python -m ruff check scripts modules tests` | 0 | Passed |
| `python -m pytest -q -ra` | 0 | 229/229 passed |
| `python -m pytest --collect-only -q` | 0 | 229 tests collected |
| `git diff --check` | 0 | Passed; only pre-existing line-ending warnings were emitted |

The `-ra` run reported no skipped or xfailed tests. A static search found no
`pytest.mark.skip`, `pytest.mark.xfail`, `pytest.skip`, or `pytest.xfail`
reference under `tests/`.

The full suite includes existing migration tests that create and migrate only
temporary `tmp_path` SQLite fixtures. Phase 2A.1 did not invoke a migration
runner against the project database or any persistent database. The project
database SHA-256 remained
`4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.

## Actual Phase 2A.1 changes

- Modified: `tests/test_repository_contracts.py`.
- Added: `GOVERNANCE_DOCUMENT_DECISION.md`.
- Added: `MIGRATION_REVISION_BACKLOG.md`.
- Added: `REVIEW_BASELINE_V2.md`.
- Added: `PHASE_2A1_CLOSURE_REPORT.md`.
- Added the seven exact files in `artifacts/review_baseline_v2/`.

No production Python, shell, configuration, Schema, scientific threshold,
reason code, status priority, SQL, database, calculation input, calculation
output, or runtime file was modified by this phase.

No SSH, LSF, `bsub`, `bkill`, VASP, or NEB command was executed. No file was
deleted, moved, staged, committed, or pushed.

The untracked-file count was 534 before Phase 2A.1 outputs and 545 after them;
the eleven additions are exactly the four reports and seven v2 files listed
above. No new unknown source file or calculation product appeared. The tracked
diff path count stayed at 65; Phase 2A.1 added no production-source diff path.

## Phase 2B entry boundary

Phase 2B may now begin only for NEB path-quality module responsibility
整理/归属 work described in `PHASE_2B_PROPOSAL.md`. It does not inherit
authority to change `AGENT_RULE_TS_ENDPOINT.md`, either migration, a database,
scientific thresholds, reason codes, status priorities, configuration Schema,
or to execute/submit a real calculation.

**PASS — the frozen conditions are closed and the bounded NEB path-quality 2B
scope may begin.**
