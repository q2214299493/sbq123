---
document_class: GENERATED_CURRENT_REPORT
as_of: '2026-09-10T00:00:00+08:00'
as_of_scope: B7 software build and release checks, not scientific/production observation
source_scope: isolated B7 release worktree and exported indexed public source
source_branch: codex/b7-release-environment
source_version: 93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a
source_version_role: B7 base commit; task source identified by the Git commit containing this report
evidence_kind: SOFTWARE_TEST_RECORD
production_schema_version: NOT_VERIFIED_IN_B6
---

# B7 Release, Packaging and Cross-Platform Reproducibility Report

Scope: B7 only. Base `93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a` on
`codex/b6-documentation-data-governance`, publication target `q2214299493/sbq123`.
Development source remains `C:/Users/86177/Desktop/work`; its 356 pre-existing
status entries at B7 start were not folded into this task. Changes and tests use
`C:/Users/86177/AppData/Local/Temp/sbq123-b7-release-environment`.
No automatic merge, new scientific feature, or further overhaul phase is included.

## B7 closure status

| Issue | Status | Evidence |
|---|---|---|
| B7-01 | PASS | Pre-change real wheel and clean core install characterized; source/resource/CLI reference searches cover configs, schemas, templates, metadata, skill references, runtime documents and SQL. Baseline failures below. |
| B7-02 | PASS | One explicit package-vs-repository contract; package defaults use the shared resolver, repository-only CLIs fail with REPOSITORY_CONTEXT_REQUIRED. |
| B7-03 | PASS locally | Real wheel built and installed without editable mode in a new venv, then invoked outside the source tree. Nine declared console scripts pass --help. |
| B7-04 | PASS | 60 enumerated runtime resources, copied only at build time from canonical source owners; importlib.resources resolves installed data. |
| B7-05 | PASS locally | Artifact gate audits all 285 wheel members, reads all 60 resources, checks installed code location and explicit repository errors, and runs fixture operations. |
| B7-06 | PASS locally | Fresh editable and normal installations match all nine CLI help interfaces, all resource hashes and deterministic integration-smoke output. |
| B7-07 | LOCAL PASS; CI_PENDING | Windows 11/Python 3.13.9 exercised locally; required Ubuntu/Windows Python 3.11 matrix awaits the branch CI result. |
| B7-08 | PASS locally | Atomic publication/exclusive reservation/state/SQLite tests retained; repeated writes and injected sharing errors preserve complete prior state/reservation markers. No retry/sleep workaround or B1 executor change. |
| B7-09 | PASS | Core install avoids ASE/Sella/pymatgen/ML imports for unrelated entrypoint help; explicit optional errors identify capability and extra. Existing reviewed semantic/precomputed modes and Sella failure policy remain. |
| B7-10 | PASS | Generated SOFTWARE_ENVIRONMENT manifest records Python/OS, direct/key optional resolved versions, package/WHEEL metadata, content inventory and smoke results. |
| B7-11 | PASS for new classifications | Generated egg-info/dist-info/cache entries are ignored/excluded from new managed-state proposals. Prior immutable events remain intact; no physical metadata deletion. |
| B7-12 | STATE_RECONCILIATION_REQUIRED | Existing competing current-task events remain unresolved; safe sync fails explicitly, without applying or rewriting state. |
| B7-13 | IMPLEMENTED; CI_PENDING | Full Linux suite retained; engineering and actual-wheel matrices added for Windows/Ubuntu Python 3.11. Environment reports/logs are CI artifacts. |
| B7-14 | PASS locally | Fresh export uses only Git index content, including tests proving untracked/runtime and unstaged changes are not copied. Wheel and document/resource checks run against that export. |
| B7-15 | PASS | Public indexed paths and every built wheel member audited; no excluded credential, private key, POTCAR, production DB or model-weight artifact detected. Historical path text retained. |
| B7-16 | PASS | [Installation contract](../../docs/INSTALLATION.md), README and current publication scope distinguish editable/wheel/repository-only/external deployment and extras. |
| B7-17 | PASS | Synthetic contract -> bound local file -> temporary registry plan -> explicit test approval -> transaction -> persisted read/idempotency. Two rows inserted, zero scientific result rows, zero external actions. |
| B7-18 | PASS locally; CI_PENDING | Focused B7 and B1-B7 regressions plus real installed-artifact checks; exact local results below. |

## Pre-change compatibility baseline

Before packaging edits, `python -m pip wheel --no-deps --no-build-isolation` built
`sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`: 217 members, **zero non-Python
runtime resources**. SHA-256 was
`eeddcd6eaff3c82dea753643665f623dedc4774016f0fbdfdcc212ef60dc6ef4`.
It was installed into a fresh core-only venv and exercised outside the repository.

- Registry write, document help and state-manager help: exit 0.
- Registry initialization with a temporary explicit DB: exit 1, missing schema SQL.
- TS --help: exit 1, deep eager ASE import failure.
- Readiness generation: exit 1, missing site-packages/docs/DOCUMENT_GOVERNANCE.md.
- Retrieval whitelist path existed as a computed path but `is_file()` returned false.

This establishes the editable/source-tree masking problem. No baseline operation
opened a production database. Task-created baseline build output was moved to an
external temporary location; unrelated build/runtime files were not removed.

## Distribution and resource ownership

The [installation contract](../../docs/INSTALLATION.md) is the maintained user guide.
`pyproject.toml` still declares Python >=3.11 and package version 0.1.0.
No parallel executor, parser or scientific validator was introduced.

| Resource kind | Classification | Runtime owner/handling |
|---|---|---|
| Reviewed configs, backend restrictions, scientific profiles, gate policies, data-governance policy | PACKAGE_RUNTIME_RESOURCE | Exact source paths enumerated in [release_resources.json](../../configs/release_resources.json); values unchanged except generated-metadata classification patterns. |
| Registry base schema and four migration/rollback SQL files | PACKAGE_RUNTIME_RESOURCE | Original modules/calculation_registry files; SQL unchanged. Registry/schema and TS endpoint owners use the same resolver. |
| Retrieval source whitelist, record/image schemas | PACKAGE_RUNTIME_RESOURCE | Original skills/catalysis-data-retrieval/references files; validation/ranking remain in scripts/catalysis_retrieval. |
| LSF template, remote shell adapters, Excel JS adapter | PACKAGE_RUNTIME_RESOURCE | Original scripts files; rendering/copying only. No command is executed by resource loading. |
| Method docs, current/module state, module READMEs, skill procedures, history, task/event ledgers, public initial export manifest | REPOSITORY_ONLY_RESOURCE | Explicit checkout/workspace required. Document/readiness/state operations do not select installed site-packages as repository state. |
| INCAR custodian skill references and report templates; module compatibility aliases; campaign-specific scripts and reviewed campaign paths | REPOSITORY_ONLY_RESOURCE | Remain source checkout capabilities. They are not silently copied into an installed application. |
| Node.js/@oai/artifact-tool, Git, semantic model cache, optional Python stacks | OPTIONAL_EXTERNAL_RESOURCE | Explicit dependency/context contracts. Excel operations retain repository containment; wheel exposes help and the adapter, not a new workbook execution path. |
| Local calculation inputs/results, registry data, AQCat25/MatRIS checkpoints | SCIENTIFIC_EXTERNAL_ARTIFACT | Caller/deployment-owned; excluded from wheel. Scientific acceptance is never inferred from installation. |
| POTCAR, private credentials/keys, production DB, WAVECAR/CHGCAR and private runtime state | SENSITIVE_EXCLUDED or scientific external artifact | Not packaged, opened, migrated or transferred. |

There are **60 exact packaged resource paths** in the single manifest. Its list is
also enforced by MANIFEST.in for source distributions and by the wheel audit.
`release_build.BuildPy` copies originals only into build output under
`scripts/_resources/`; no second manually maintained resource directory exists.
`runtime_resources.resource_path` supports reviewed installed data/source code and
explicit checkout paths with canonical containment. Windows drive/UNC, POSIX
absolute and traversal escapes are rejected. Git attributes make YAML/YML/TOML
release sources use LF without reserializing scientific data or changing values.

The only retained legacy resource fallback is the existing standalone AQCat25
schema/handoff facade: explicit/sibling schema deployments still work without a
new packaging helper. No remote deployment or GPU wrapper content was changed.
TS CLI imports are deferred within the existing handlers; the public gate and
submission, evidence, registry and scientific owners remain the same. Legacy
retrieval skill paths delegate to installed CLI adapters and keep direct API
re-exports and existing arguments.

## Built artifact and parity

Final local artifact: `sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`.
SHA-256: `781e15c1de43ab9150d153b99d1f81075fe12db61e36dfab3c317fd996364d9a`.
285 members; tag `py3-none-any`; generator `setuptools (84.0.0)` from pip's isolated
PEP 517 build environment. Full member list, resource hashes and resolved versions
are in [release_environment.json](../release_environment.json).

Clean normal and editable environments use **Windows 11/Python 3.13.9**, core-only
requirements: jsonschema 4.26.0, NumPy 2.5.3, PyYAML 6.0.3. ASE, Sella, pymatgen,
matplotlib and sentence-transformers are absent in the normal installed smoke
environment. Installed code resolves inside the venv, not the source checkout;
PYTHONPATH/PYTHONHOME are removed from child environments and cwd is outside both
source and package directories. Source/build host versions are recorded separately
and are not confused with the isolated build backend or clean runtime versions.

| Installed command | Normal wheel | Editable | Interface parity |
|---|---|---|---|
| registry-write | --help exit 0 | --help exit 0 | identical |
| registry-init | --help exit 0 | --help exit 0 | identical |
| ts-strategy | --help exit 0 | --help exit 0 | identical |
| catalysis-search | --help exit 0 | --help exit 0 | identical |
| catalysis-validate | --help exit 0 | --help exit 0 | identical |
| repo-state | --help exit 0 | --help exit 0 | identical |
| registry-promote | --help exit 0 | --help exit 0 | identical |
| document-governance | --help exit 0 | --help exit 0 | identical |
| capability-readiness | --help exit 0 | --help exit 0 | identical |

All resource bytes and deterministic smoke results match across installation modes.
Installed registry migration SQL is actually executed against a temporary DB.
No-root readiness/state calls fail with REPOSITORY_CONTEXT_REQUIRED; installed
document/readiness commands with the explicit clean source root succeed.
The smoke inserts one synthetic calculation and one bound input-file record, then
replays the same approved plan idempotently; no scientific result is accepted.

## Optional/platform contract

Core: jsonschema, NumPy, PyYAML, standard-library SQLite.
Optional extras: `neb`/`adsmind` -> ASE; `vasp` -> pymatgen;
`visualization` -> matplotlib; `retrieval` -> sentence-transformers;
`sella` -> Sella; `release` -> build/wheel; `dev` -> pytest/Ruff/pymatgen.
The exact constraints stay in pyproject.toml; transitive dependencies are not
blindly pinned. Missing optional capabilities raise explicit errors and never
select a weaker scientific/ranking mode. Linux/Python 3.11 with Sella remains the
reference full scientific/mock environment. Windows/Python 3.11 covers engineering
and clean package installation; Windows Sella/GPU deployment is not established.
Local Python 3.13.9 software-test success is additional compatibility evidence.

## Exact local validation

- `python -m ruff check scripts modules tests`: exit 0, All checks passed.
- `python -m pytest -o addopts= -q`: exit 0, **1097 passed in 291.48s (0:04:51)**.
- B7-only `python -m pytest -o addopts= -q tests/test_b7_release.py`: exit 0, **17 passed in 0.81s**.
- Final critical B1-B7 group: exit 0, **495 passed in 76.51s (0:01:16)**.

```text
python -m pytest -o addopts= -q tests/test_b7_release.py tests/test_execution_lifecycle.py tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_b3_evidence_governance.py tests/test_b3_ml_governance.py tests/test_b4_registry_governance.py tests/test_b4_state_governance.py tests/test_registry_write.py tests/test_registry_schema.py tests/test_state_manager.py tests/test_b5_architecture_boundaries.py tests/test_b6_governance.py tests/test_code_structure.py tests/test_repository_contracts.py tests/test_artifact_io.py
```

- Real artifact gate: `python -m scripts.validate_release --source . --output C:/Users/86177/AppData/Local/Temp/b7-release-validation-final2`: exit 0, PASS, parity true, 285 audited wheel files. Builds from an indexed clean snapshot; installs actual wheel plus editable source into two new isolated environments.
- Document check: `python -m scripts.document_governance README.md docs/INSTALLATION.md docs/PUBLIC_RELEASE.md --links`: exit 0, no findings. Newly affected Markdown links also resolve.
- Existing B6 readiness determinism and protected historical/source contracts remain in the critical/full suites.
- Public index scan: no excluded file suffix/name or actual private-key header detected. No existing scientific configuration, SQL, calculation/data/output path is modified.

Earlier integration checks exposed and corrected a misplaced repository guard
that rejected explicitly configured temporary API workspaces, a Windows export
prefix problem, and a wheel scanner false positive on its own quoted test string.
The fixes preserve existing tests and move the context requirement to CLI dispatch;
new export/artifact regressions cover the release-tool defects. No architecture
limits or existing test assertions were weakened.

## Linux/Windows CI

Linux/Windows CI is required before final acceptance and is pending this branch push.
The final closure update will record the actual run/result; no CI success is claimed here.

The workflow retains full Linux tests and adds Ubuntu/Windows Python 3.11
engineering and wheel jobs. Each wheel job exports a clean indexed source, builds
an actual wheel, audits it, tests outside the checkout, compares editable parity,
and uploads software environment JSON/log artifacts. The full scientific/mock
suite is not unnecessarily repeated on every OS. CI contains no SSH, scheduler,
VASP/GPU job or model training step.

## State and remaining production limitations

Start audit: exit 1, one existing event-ledger conflict, 11 warnings and 12 review
required findings. End read-only preflight and
`python -m scripts.state_manager.cli sync --safe-only` again hit:

```text
STATE_RECONCILIATION_REQUIRED
multiple unsuperseded events for one entity: task:task-current=task-completed-966f70761e2de2c804e6dced,task-migration9748648-open-20260909-v2
```

The actual sync command exited 1 before any projection application. No event was
chosen, superseded, deleted or rewritten. The older generated PKG-INFO mismatch
cannot be safely repaired by rewriting its historical hash; new metadata is now
excluded from classification, while old history remains subject to reconciliation.
No pending proposal ID was produced by the conflict.

No production registry was opened/migrated; schema version remains 9 in code and
production remains unverified. No scientific threshold, VASP parameter, NEB/DIMER
behavior, TS/frequency acceptance, B1 reservation/execution authorization, B3
evidence acceptance, or B4 transaction algorithm was changed. Atomic writers retain
closed-before-replace and exclusive creation; unsupported sharing conflicts fail
explicitly without removing a reservation. Physical GPU/HPC deployments, Node
workbook integration, real model caches/weights and all production-only behavior
remain unverified. A release smoke PASS is SOFTWARE_ENVIRONMENT evidence only.

## Exact task-owned changed files

- `.gitattributes`
- `.github/workflows/state-manager.yml`
- `.gitignore`
- `MANIFEST.in`
- `README.md`
- `configs/data_governance.yaml`
- `configs/release_resources.json`
- `docs/INSTALLATION.md`
- `docs/PUBLIC_RELEASE.md`
- `pyproject.toml`
- `reports/capability_readiness.json`
- `reports/refactor_audit/B7_completion_report.md`
- `reports/release_environment.json`
- `scripts/README.md`
- `scripts/adsmind_lite/adsmind_common.py`
- `scripts/adsmind_lite/analyze_relaxed_adsorption.py`
- `scripts/adsmind_lite/deduplicate_adsorption_states.py`
- `scripts/adsmind_lite/detect_surface_sites.py`
- `scripts/adsmind_lite/evidence_gate.py`
- `scripts/adsmind_lite/generate_adsorption_candidates.py`
- `scripts/adsmind_lite/plan_adsorption_candidates.py`
- `scripts/adsmind_lite/validate_candidates.py`
- `scripts/adsorption/build_fe110_adsorption.py`
- `scripts/adsorption/preflight_fe110_adsorption.py`
- `scripts/aqcat25_handoff.py`
- `scripts/aqcat25_ts_schema.py`
- `scripts/catalysis_retrieval/cli.py`
- `scripts/catalysis_retrieval/ranking.py`
- `scripts/catalysis_retrieval/records.py`
- `scripts/catalysis_retrieval/validate_cli.py`
- `scripts/document_governance.py`
- `scripts/execution_backends.py`
- `scripts/generate_capability_readiness.py`
- `scripts/init_registry.py`
- `scripts/neb_agent/analyze_neb_outputs.py`
- `scripts/neb_agent/diagnose_path_geometry.py`
- `scripts/neb_agent/path_quality_cli.py`
- `scripts/neb_agent/path_quality_control.py`
- `scripts/neb_agent/pilot_validation.py`
- `scripts/neb_agent/remote_monitor.py`
- `scripts/offline_mlip_fusion_feasibility.py`
- `scripts/optional_dependencies.py`
- `scripts/prepare_aqcat25_ml_neb_handoff.py`
- `scripts/prepare_reviewed_neb_peak_dimer.py`
- `scripts/prepare_ts_heldout_vasp_label_batch.py`
- `scripts/registry_excel_promotion.py`
- `scripts/registry_schema.py`
- `scripts/registry_write.py`
- `scripts/release_build.py`
- `scripts/release_environment.py`
- `scripts/release_smoke.py`
- `scripts/review_completed_neb_parent.py`
- `scripts/runtime_resources.py`
- `scripts/select_dual_model_ts_vasp_labels.py`
- `scripts/state_manager/cli.py`
- `scripts/state_manager/models.py`
- `scripts/state_manager/projections.py`
- `scripts/state_manager/stale_items.py`
- `scripts/ts_endpoint/database.py`
- `scripts/ts_endpoint/purpose.py`
- `scripts/ts_endpoint/validator.py`
- `scripts/ts_strategy_engine/active_learning_cli.py`
- `scripts/ts_strategy_engine/active_learning_path_labels.py`
- `scripts/ts_strategy_engine/active_learning_state.py`
- `scripts/ts_strategy_engine/cli.py`
- `scripts/ts_strategy_engine/cli_commands.py`
- `scripts/ts_strategy_engine/contract.py`
- `scripts/ts_strategy_engine/dimer_gate.py`
- `scripts/ts_strategy_engine/dimer_gate_common.py`
- `scripts/ts_strategy_engine/dimer_path_gate.py`
- `scripts/ts_strategy_engine/strategy_learning.py`
- `scripts/ts_strategy_engine/workflow.py`
- `scripts/ts_validation/analyze_vfa.py`
- `scripts/ts_validation/connectivity.py`
- `scripts/ts_validation/validation_pipeline.py`
- `scripts/validate_release.py`
- `scripts/vasp_inputs.py`
- `scripts/vasp_lsf.py`
- `skills/catalysis-data-retrieval/scripts/hybrid_search.py`
- `skills/catalysis-data-retrieval/scripts/validate_records.py`
- `tests/test_b7_release.py`
