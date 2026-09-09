# Calculation Registry

## Purpose

Track every calculation, job status event, input/output file, extracted result, and scientific review without inventing missing values.

## Separation of Concerns

- Scheduler status records what the cluster reported.
- Scientific status records convergence, validity, and reviewer judgment.
- File records prove where evidence exists and how it was identified.
- Result records preserve value, unit, convention, source file, and validation.
- The registry never decides chemistry by itself.

## Storage Rule

Every input and output receives a record. Large runtime files and licensed POTCAR content may remain outside Git, but their path, role, checksum when available, retention location, and access status must be registered.

## Implementation

- `schema.sql`: SQLite schema for calculations, jobs, status history, files,
  results, reviews, contract-bound TS validation, matched-static barrier sets,
  reviewed TS strategy templates, and Excel-promotion receipts.
- `scripts/init_registry.py`: explicitly creates or transactionally migrates a named registry. Opening a registry never migrates it.
- `registry-write plan` validates an append-only JSON batch against the current
  schema without changing the database. It may also plan an explicit
  `workflow_status_changes` list that names the expected old status and writes
  an immutable `calculation_workflow_status_history` row before changing the
  current projection. `registry-write apply` requires the exact reviewed plan
  hash and applies all rows and status changes in one foreign-key-enforced
  transaction. New calculation workflows use this entrypoint instead of
  calling `sqlite3.connect` directly.
- `configs/registry_legacy_writers.yaml` is the bounded compatibility allowlist
  for historical calculation-local writers. It permits no new direct SQLite
  writer and does not make an allowlisted script authoritative.
- Default database path: `data/project_registry.sqlite3`.

No scientific record is inserted automatically during initialization. Active-job and historical backfill are separate reviewed tasks.

Completed adsorption/coadsorption workflows are different from initialization
or historical backfill: once the owning adsorption validator has established
normal termination, electronic convergence, ionic/force convergence,
compatibility, and accepted final chemistry/geometry, the workflow must create,
plan, review, and apply its append-only registry batch in the same completion
turn. This result registration is covered by durable user authorization and
does not wait for a separate reminder. It must be idempotent. A failed,
incomplete, incompatible, duplicate, or unreviewed calculation may receive
truthful status/provenance records but never an accepted-result record.
Adsorption-energy derivation and Excel promotion remain separate gates.

Current active-branch backfill: 24 H2/CHx/CHO adsorption relaxations are stored
with job/status provenance, four confirmed remote evidence files per job,
reviewed chemistry/site/duplicate fields, and dataset-compatibility reviews.
Current promotion states are 12 `static_needed`, six `duplicate`, and six
`needs_review`. The accepted clean static, six corresponding gas references,
and three reviewed gas isomers are also registered with complete remote file
inventories. The Step 12A baseline is also complete in the registry: CO/top
was already present, 23 historical calculations were backfilled from
hash-audited remote files, 19 unique final structures have accepted compatible
surface energies, and five duplicate final sites remain provenance-only.
Expired LSF history is represented as `UNKNOWN` rather than inferred job IDs.
Schema version 8 adds `ts_strategy_events` for immutable strategy variants,
attempts and reviewed outcomes through the existing registry layer. These
records cannot promote a TS or barrier; source-matched Grade-A template evidence
is required before a learning comparison counts a TS success. The additive
migration preserves all existing scientific rows.

Schema version 8 retains the TS evidence binding introduced in
version 4 and binds TS validation to the source saddle,
frequency output, reaction contract, atom map, and method branch. DIMER
validations may omit positive/negative mode displacements and connectivity;
those fields remain available for optional diagnostics and for methods whose
policy still requires connectivity. Reportable barriers require accepted,
compatible IS/TS/FS final-energy records. In the active Fe(110) branch these
are final `OUTCAR` `TOTEN` values from the `ISMEAR=1`, `SIGMA=0.20 eV`
production/DIMER convention; a matched single-point is not required. The TS
template table accepts an explicit evidence-complete Grade-A success or
reviewed failure. DIMER success templates require frequency and accepted
barrier evidence, while positive/negative downhill files remain optional
diagnostics. The canonical
database is versioned; WAL/SHM files and backups remain ignored.

## First Backfill Target

Start with the active true Fe(110) adsorption branch before broader historical
backfill:

- accepted gas references for H2, CH, CH2, CH3, CH4, H2O, CO, H, O, OH, C,
  CHO, CH2O, CH3O, CH4O, and reviewed isomers when accepted;
- accepted replacement clean Fe(110) `5x5x1` final static;
- submitted adsorption pilot and expansion jobs, with job ID, remote root,
  initial site, final site, final species, chemical event, plausibility status,
  convergence status, geometry verdict, and duplicate group;
- final static and adsorption-energy records only after the
  `dataset-compatibility-gate` passes;
- Excel promotion status so a result is never both "calculated" and invisible
  to the thesis table.

Do not backfill legacy fake-Fe(110)/Fe(211)-like records into the active
Fe(110) dataset. If retained for history, mark them as rejected or legacy-only.

## Outputs

- calculation, job, status-history, file, result, review, TS-validation, and
  TS-strategy-template records
- hash-bound Excel-promotion receipts with registry ID, worksheet row, workbook
  hashes before/after, resolved-value hash, and reviewer identity
- source paths, units, conventions, checksums when available, and scientific-review status

## Done Criteria

Every registered job has status history, every accepted result has provenance and review, and every required input/output has a file record.

## Excel Promotion

`registry-promote plan` (or `python -m scripts.registry_excel_promotion plan`) creates a read-only,
hash-bound plan from a reviewer-approved JSON request. Numeric adsorption cells
must resolve to `accepted_matched_static`,
`accepted_compatible_final_energy`, or the explicitly named
`accepted_compatible_adsorption_energy` registry result; the last status is
valid only when `result_name=adsorption_energy`. Barrier cells remain restricted
to accepted compatible final-energy results from an accepted, Grade-A,
kinetic-eligible barrier set.
Human-readable labels are allowed only as explicit reviewed metadata.
Adsorption rows additionally require an `adsorption_workflow` calculation, so
TS endpoint statics cannot enter the adsorption thesis table.
The request names an existing worksheet, its exact header labels, and the
header row so title rows are never mistaken for tabular data.

`apply` revalidates the request, registry state, and workbook hash, writes with
`@oai/artifact-tool`, and records both a SQLite `excel_promotions` row and a
JSON receipt. The default operation appends one row. A reviewed `target_row`
may instead update an existing deduplicated row; every preserved cell must be
declared as `existing_workbook_cell` and is compared before the accepted
registry value is written. A recorded historical scheduler `UNKNOWN` is not
invented as `DONE`; accepted hash-bound scientific evidence and the owning
workflow status remain the promotion authority. The gate refuses unknown
sheets, changed headers or preserved cells, repeated registry IDs, changed
workbook bytes, unreviewed requests, unaccepted results, or an unaccepted TS.
It never creates a new workbook table or infers scientific values from a
calculation folder.

## B4 persistence contract (schema 9)

`registry_write.py` remains the public API/CLI facade. `registry_mutations.py`
owns batch validation and the single SQL apply path; `registry_transactions.py`
owns database fingerprints, exact-plan approval and immutable apply receipts.
`registry_acceptance.py` only adapts B3 evidence and existing scientific owners.
It does not introduce scientific thresholds or replace TS acceptance.

Planning executes the complete batch against an in-memory database snapshot,
including foreign keys, constraints, transitions and scientific/evidence gates.
The plan includes `plan_sha256`, database identity/fingerprint, reviewer identity,
mutation scope and actions. Save this document and an explicit approval containing
`plan_sha256`, `database_fingerprint`, `reviewer`, `reviewed_at`, `decision=approve`
and the exact `scope`. `registry_transactions.approve_plan` constructs the
approval data; it does not authenticate the human or grant authority by itself.

Apply requires `--plan PLAN.json --approval APPROVAL.json --confirm-sha256 PLAN_HASH`
in addition to `--manifest` and `--db`. A former batch-only hash is insufficient.
The Python API preserves its name and adds required `plan` and `approval` arguments.
There is no silent planning at apply. Under `BEGIN IMMEDIATE`, apply checks the
snapshot, verifies all actions, inserts rows/events/receipt and commits together.
Failure rolls back and records `batch_failed` separately. Only these failed
attempt events are excluded from the logical database fingerprint to permit a
reviewed retry after rollback. Exact successful retries return the original receipt;
an altered plan cannot reuse a batch ID. Pending WAL content is included through
the active SQLite snapshot, not a hash of the main database file alone.

`compatibility_revisions` stores immutable content-addressed versions with an
optional superseded revision. `calculation_compatibility_revisions` permanently
binds each calculation to its original version; the existing compatibility table
is retained for reader compatibility. New compatibility is a new revision/new
calculation, never an update of historical evidence. Scientific records, reviews,
status histories, events and receipts reject UPDATE, DELETE and conflicting REPLACE.

`state_manager/job_lifecycle.py` owns recorded job/workflow transitions. Scheduler
aliases remain distinct from scientific validation. DONE cannot restart; FAILED
can reach DONE only with an explicit persisted `job_recovery_events` record.
`job_current_state` is a view over immutable observations. Observation records have
stable IDs/times and the enclosing batch event supplies actor/source and reason.

Predictions stay outside accepted result tables. New candidates require evidence;
accepted results require B3 transferable calculated-result evidence bound to the
exact result, compatibility and current scientific sources. The generic accepted
result adapter supports reviewed VASP relaxation `final_toten` in eV via existing
owners. Other scientific result kinds use their existing owning workflow; a bare
accepted status is not authority. Full provenance is preserved in `batch_applied`.
Published results retain the separate Excel promotion gate. Excel apply rechecks
the database under lock, records a publication event and restores workbook/receipt
on ordinary transaction failure. An interrupted attempt remains explicitly pending
reconciliation; files and SQLite cannot share a hardware-atomic commit.

### Explicit migration / rollback

`009_registry_governance.sql` adds schema 9 without changing existing scientific
rows. Initialization and upgrades use a single transaction through all versions,
with schema, integrity and foreign-key validation before commit. Unknown/newer or
incomplete schemas fail closed. No production migration is run during B4.

Before an operational upgrade, retain a reviewed off-line backup. Immediate
additive downgrade is available as `registry_schema.rollback_registry_v9(Path)`
and uses `009_registry_governance_rollback.sql`. It refuses to discard new events,
receipts, recovery records or new compatibility revisions. After operational use,
rollback requires a reviewed backup/recovery plan rather than deleting new history.
Opening a version-8 registry (even with legacy `migrate=True`) now requests explicit
migration; production rollout is a separate authorized operation.
