---
document_class: HISTORICAL_SNAPSHOT
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: SOFTWARE_TEST_RECORD
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
report_source_branch: SEE_ORIGINAL_BODY_OR_NOT_RECORDED
test_source_version: SEE_ORIGINAL_BODY_OR_NOT_RECORDED
production_scope: original limitations remain; never a production verification
---

# B3 Evidence and ML Data Governance Completion Report

Scope: B3 only. Public base: `3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c`
on `codex/b2-scientific-contract`. Publication target:
`q2214299493/sbq123`, `codex/b3-evidence-ml-governance`. No merge or B4.

## Issue closure

| Issue | Status | Implementation and verification |
| --- | --- | --- |
| B3-01 Evidence lifecycle | PASS | Derived IMPORTED → SCHEMA_VALID → SOURCE_VERIFIED → CONTENT_BOUND → REVIEWED → TRANSFERABLE. Snapshot identity/availability/time, extracted source span, reviewer decision/scope and reviewed compatibility are separate requirements. Stored flags cannot advance a stage. |
| B3-02 Retrieval validation | PASS | Precomputed vectors require model/time/dimension and current record/content bindings. Query text and model are bound independently. Nonfinite, empty, zero-norm, malformed and mismatched vectors fail. Ranking output never authorizes scientific acceptance. |
| B3-03 Claim provenance | PASS | Literature, expert opinion, model prediction, calculated result and experimental report remain distinct. Prediction claims require prediction metadata; opinions/predictions are limited to candidate guidance. Whitelist checking is reused by the adsorption gate. Cached external plans are replayed against their source before consumption. |
| B3-04 Training governance | PASS | MatRIS replay/preflight, benchmark folds and AQCat25 database construction reuse source/identity and split checks. Calculation, source-row, reaction and equivalent-structure overlap across splits is rejected. Current sources are checked before training eligibility; completed model-usage records bind training items to checkpoint identity. |
| B3-05 Prediction provenance | PASS | CARE/GAME-Net-style imported predictions require typed metadata; MatRIS, AQCat25 and dual-model producers retain model/input/time/uncertainty provenance. Explicitly unavailable uncertainty is never converted into an estimate. External/prediction declarations cannot enter the local calculated-result batch writer. |
| B3-06 Numeric quality | PASS | Existing scientific_validation owns finite scalars and the new rectangular finite-array validator. Embeddings, descriptors, source labels, predicted energy/forces and uncertainty reject nonfinite or malformed values. Cosine normalization scales inputs before norm calculation to prevent finite-input overflow. |
| B3-07 Ownership | PASS | One evidence lifecycle owner, one shared label hydration owner, one cross-split validator, one finite-array owner. Retrieval and ML metadata code do not submit, promote registry results or accept TS science. Regression tests inspect those boundaries. |
| B3-08 Regression validation | PASS | Full suite 961 passed; focused suite 146 passed; Ruff and retrieval CLI self-test passed. |

## Ownership and removed duplication

- `scripts/adsmind_lite/evidence_lifecycle.py` extends the existing external
  evidence gate; it introduces no second executor, registry or evidence CLI.
  `evidence_gate.py` applies source/target/template checks and `prescreen.py`
  reuses that same gate when consuming an external plan.
- `skills/catalysis-data-retrieval/scripts/validate_records.py` retains source
  whitelist and embedding validation; `hybrid_search.py` owns ranking only.
  The misleading `precomputed-reviewed` label is replaced with
  `precomputed-source-bound`. Existing ranking PASS/production_ready fields
  are explicitly scoped to ranking and accompanied by scientific_acceptance=false.
- `scripts/provenance_fields.py` owns only strict identity text and
  timezone-aware timestamps, shared by evidence and model provenance without
  a dependency cycle. `prediction_provenance.py` owns ML metadata validity;
  the evidence lifecycle uses it for prediction-typed claims.
- `scripts/matris_training_data.py` is the shared MatRIS/AQCat25 label-binding
  owner. Existing MatRIS source/hydration and label-set validation were moved
  here and reused by package preparation, preflight and AQCat25 database
  construction. Existing VASP force-label acceptance is called through its
  original owner; no convergence, force or TS acceptance logic was replaced.
- `scripts/matris_training_exclusions.py` owns split isolation. Duplicated
  MatRIS package/preflight exclusion loops were removed in favor of this owner.
  Its private SHA-256 validator was removed; calls use artifact_io.require_sha256.
- Repeated energy/force coercion and finite-array checks in the changed data
  consumers use scientific_validation. Existing scientific thresholds and
  numerical label comparisons are unchanged.

## Evidence and ML boundaries

The source snapshot is bound by SHA-256 to an immutable reference. Extracted
content must match its zero-based, end-exclusive Unicode character span.
Review binds the complete claim/source/content subject, including compatibility,
record identity and prediction metadata when applicable. Rejected reviews remain
REVIEWED but cannot transfer. Transfer requires the actual target domain, scope
and reviewed compatibility conditions; a hash alone establishes none of these.

Adsorption READY additionally requires a current template path and digest.
Whitelisted sources use the existing URL validator. Literature still requires the
existing whitelist-first fallback, DOI/publisher and journal review. External
energies remain ordering references only and are never local calculated results.

Dataset stages are RAW, PARSED, VALIDATED, TRAINING_ELIGIBLE and USED_IN_MODEL.
TS label sources require an explicit reaction identity that agrees with their
source batch; null/empty/coerced identifiers cannot bypass reaction grouping.
Hydration ignores claimed eligibility and validates current source files,
calculation/structure/reaction identity and finite labels. Split isolation runs
before optimizer eligibility or database creation. Validation/test rows never
receive training eligibility. Completed MatRIS receipts and AQCat25 model-use
records link used training rows to checkpoint and source-manifest identities.

The added structure descriptor uses labelled periodic distance neighborhoods and
cell volume, retaining the prior five-decimal exclusion precision. It is invariant
to atom permutation, periodic translation and rigid rotation. Legacy ordered
geometry hashes remain unchanged for artifact binding. Descriptor collisions
are conservative exclusion decisions; they never prove scientific-result
identity or authorize reuse. Same declared reaction identities cannot cross
training/validation/test, including a newly rehashed manifest.

Every new covered prediction records model identity/version, input fingerprint,
source reference, generation time, uncertainty and available split metadata.
A single model without an uncertainty estimator records an explicit unavailable
status and reason. This is not calibrated uncertainty, confidence in a scientific
result, or zero error. MatRIS versions bind actual in-memory state, including
unsaved updates; input files are rechecked before prediction. GPU inference
wrappers and backend restrictions are unchanged; AQCat25's schema addition is
limited to candidate prediction metadata.

No dedicated active GAME-Net or expert-opinion execution module was found in
maintained scripts/skills. CARE is an import/pose-transfer consumer. The shared
typed metadata/evidence validators cover these imported records; no new model
runner or expert system was invented. Existing local strategy-learning
observation/file/review separation was inspected and its unrelated dirty changes
were preserved.

## Compatibility impact

Existing valid parser APIs, B1 authorization/submission behavior, VASP settings,
NEB/DIMER/TS acceptance, GPU wrappers and registry schema remain unchanged.
Scientific acceptance is still owned by the existing scientific modules.

Intentionally rejected legacy states include raw precomputed vectors without
provenance, booleans standing in for source/review/template evidence, stale
external READY documents, legacy exclusion manifests without the new equivalence
binding, label caches without current source files/calculation identity, and
reaction overlap across splits. Existing within-reaction holdouts are not
independent reaction tests and need a reviewed grouped split. These states
require explicit reviewed metadata/source
refresh, not automatic migration or new calculations. CARE CSV imports now
require a JSON prediction_provenance column. Old AQCat25 prediction documents
retain their existing candidate-only schema; that does not grant governed
evidence or training eligibility.

The shared training-data preflight requires the repository package and accessible
bound source files. A former flat standalone AQCat25 training deployment must
stage these dependencies and sources, or build its governed database under work.
No remote deployment or wrapper change is included.

## Development, files and validation

Implementation was performed in the real source directory
`C:/Users/86177/Desktop/work`. The separate
`C:/Users/86177/AppData/Local/Temp/sbq123-b3-evidence-ml-governance`
worktree is a source-release validation/publication snapshot on the existing
sbq123 history. Task-owned pre-edit tracked sources were checked against the
public B2 base; final task files are mirrored byte-for-byte. Unrelated local
learning changes, runtime data and production database changes are excluded.
No reset, clean, stash, force push or historical artifact rewrite was used.

### Exact changed files

- `scripts/scientific_validation.py`
- `scripts/adsmind_lite/evidence_lifecycle.py`
- `scripts/adsmind_lite/evidence_gate.py`
- `skills/catalysis-data-retrieval/scripts/validate_records.py`
- `skills/catalysis-data-retrieval/scripts/hybrid_search.py`
- `scripts/matris_training_exclusions.py`
- `scripts/matris_training_data.py`
- `scripts/matris_energy_force_finetune.py`
- `scripts/prepare_matris_replay_finetune_package.py`
- `scripts/prediction_provenance.py`
- `scripts/matris_finetune_speed_benchmark.py`
- `scripts/adsorption/build_fe110_care_isomers.py`
- `scripts/registry_write.py`
- `tests/evidence_fixtures.py`
- `tests/test_b3_evidence_governance.py`
- `tests/test_b3_ml_governance.py`
- `tests/test_adsorption_evidence_gate.py`
- `scripts/adsmind_lite/prescreen.py`
- `tests/test_adsmind_prescreen.py`
- `scripts/aqcat25_ts_force_prediction.py`
- `scripts/dual_model_ts_force_prediction_batch.py`
- `configs/aqcat25_ts_active_learning.schema.json`
- `scripts/aqcat25_ts_training_data.py`
- `scripts/ts_strategy_engine/active_learning_training.py`
- `tests/test_aqcat25_ts_active_learning.py`
- `modules/catalysis_data_retrieval/README.md`
- `scripts/README.md`
- `skills/catalysis-data-retrieval/SKILL.md`
- `skills/catalysis-data-retrieval/references/record_schema.json`
- `scripts/provenance_fields.py`
- `reports/refactor_audit/B3_completion_report.md`

### Final validation

Runtime: Windows, Python 3.13.9 (Anaconda). The GitHub workflow uses Ubuntu
and Python 3.11. Tests ran against the complete source-release snapshot.

Normalized source snapshot SHA-256 (30 task-owned source/test/document files,
excluding this completion report; CRLF normalized to LF; sorted compact JSON
mapping paths to file SHA-256 values):
`e8f2ba9318f3e4b4953ab59e2376ddacce8af8d52c7ddba1b4ae9a45a6682625`.

Focused command:

```text
python -m pytest -o addopts= -q tests/test_b3_evidence_governance.py tests/test_b3_ml_governance.py tests/test_catalysis_retrieval.py tests/test_adsorption_evidence_gate.py tests/test_adsmind_prescreen.py tests/test_matris_training_exclusions.py tests/test_matris_energy_force_finetune.py tests/test_prepare_matris_finetune_request.py tests/test_dual_model_ts_force_prediction_batch.py tests/test_aqcat25_ts_active_learning.py tests/test_aqcat25_path_active_learning.py tests/test_registry_write.py tests/test_code_structure.py
```

Focused result: **146 passed, 0 failed, 0 skipped in 31.77s**, exit 0.

Required complete repository commands:

```text
python -m ruff check scripts modules tests
python -m pytest -o addopts= -q
```

Ruff: **All checks passed**, exit 0.
Full pytest: **961 passed, 0 failed, 0 skipped in 339.97s (0:05:39)**, exit 0.

Additional checks: Ruff on the retrieval skill scripts passed; its dependency-light
CLI self-test printed PASS. Scoped git diff --check passed. The 31-file task set,
actual imported module locations, unchanged protected B1/B2 sources, and the
prediction-only schema extension were checked. No GPU shell wrapper or
production data path is in the patch.

The initial complete intermediate snapshot passed 942 tests in 346.78s.
Further governance checks were added afterward; only the final snapshot results
above establish completion. Updated positive fixtures supply real temporary
source/template bindings; original force-only, motif-ranking and scientific
assertions were retained. Adversarial tests cover missing/stale source and review,
wrong target, cached READY bypass, query/model mismatch, nonfinite embeddings,
uncertainty, rehashed reaction leakage, reordered equivalent structures, dataset
source loss and rejection before a temporary registry/database write.

Startup state audit: exit 0, zero errors and five existing warnings. Read-only
sync preflight found the pre-existing error
`repository item changed after classification: sbq_catalyst_agent_workflow.egg-info/PKG-INFO`
and unrelated projection proposals
`proposal-fbdd167f3d1d22bcc040c277`,
`proposal-fc9e18ea99ec76fdad03d6bd`, and
`proposal-11c7077298b7b7ea07cbf254`.
They target tasks/current_task.md and data/state_handoff/projection_manifest.json.
No state projections or event changes were applied; state-manager repair is
outside B3. A successful mutating sync is not claimed.

## Remaining uncertainties

- No production database access/write, real model inference/fine-tuning,
  GPU/VASP job, scheduler query or SSH operation was performed. Model tests use
  fake calculators and temporary inputs; databases are temporary test databases.
- Deployed dependency/source staging and real model-output variants remain
  unverified. Per-prediction in-memory model hashing has not been benchmarked
  on production hardware.
- Snapshot hashes/reviewer identity fields are traceability, not cryptographic
  authentication of publisher/reviewer truth. Source access, review authority
  and scientific interpretation still require accountable review.
- Near-equivalent structures outside the retained precision and different
  primitive/supercell representations are not asserted interchangeable.
  Conservative descriptor collisions require review; reaction IDs must describe
  the actual reaction, not be relabelled to evade a split.
- File rechecks do not provide an immutable filesystem snapshot against
  concurrent privileged source changes. Legacy evidence/data are not silently
  upgraded, and no production acceptance or model promotion is established.

