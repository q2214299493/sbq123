# B2 Scientific Contract and VASP Validation Completion Report

Scope: B2 only. Base: `b1c59addbc7d7be64347db66a201dc5841404341` on
`codex/b1-execution-lifecycle`. Publication: `q2214299493/sbq123`, branch
`codex/b2-scientific-contract`. No merge and no B3 changes.

## Issue closure

| Issue | Status | Implementation and evidence |
| --- | --- | --- |
| B2-01 Final electronic convergence | PASS | Shared streaming parsing tracks latest started/completed electronic cycles, final target completeness, explicit EDIFF evidence and incomplete output. Newer incomplete, truncated or unconverged cycles cannot inherit historical success. OUTCAR and OSZICAR final cycles must align; numeric-only evidence requires both final dE and d eps. Tests include multi-step runs, appended OUTCAR runs, repeated DIMER ionic indices, NELM exhaustion and malformed output. |
| B2-02 Authoritative INCAR parser | PASS | `read_incar_values` owns semicolon, whitespace, case, comment, continuation and quoted-value parsing. Same duplicate values are accepted; conflicting assignments and malformed scalars are rejected. Existing string-returning aliases delegate directly. |
| B2-03 Contract semantics | PASS | Both raw and hash-consistent normalized contracts use `_normalize_contract_payload` through `normalize_contract`. Required text, complete bijective atom maps, index base, mapped atoms/bonds/coordinates, endpoint calculation IDs and compatibility metadata are checked. Rehashed invalid normalized contracts remain invalid. |
| B2-04 Finite numbers and ranges | PASS | One scientific scalar/range owner rejects NaN, infinities, null/bool scalars, fractional integers and invalid positive/nonnegative ranges. Contracts, INCAR, strategy/path policies, DIMER and VFA numeric inputs use it. Nonfinite VFA frequencies/vectors are explicitly rejected instead of silently skipped. No numerical thresholds were changed. |
| B2-05 Chemical family matching | PASS | Family definitions are matched to element-labelled broken/formed bonds, not merely nonempty bond lists. Chemistry remains comparable across atom renumbering. Structure similarity and exact result identity are separate; neither authorizes reuse without chemical equivalence and existing accepted evidence. |
| B2-06 TS science preservation | PASS | Existing validated_ts, DIMER technical acceptance, frequency grade, connectivity and source-hash requirements remain. Explicit positive and negative TS regressions supplement existing DIMER/VFA pipelines. B1 gate/evidence/submission code and GPU wrappers have no diff. |

## Authoritative ownership and compatibility

- `scripts/neb_agent/utils_vasp.py` owns OUTCAR/OSZICAR electronic cycles. Its
  cycle-transition helper is inside the same parser module; no alternate parser
  or executor was added. Legacy force/magnetization/energy history fields remain.
- `scripts/vasp_result_gate.py` owns INCAR lexical/scalar parsing and final SCF
  interpretation. `final_scf_state` consumes parsed evidence without I/O;
  `final_scf_status` retains the original six-field default summary. Callers may
  request `include_cycles=True` for explicit PASS/NOT_CONVERGED/INCOMPLETE and
  cycle details. This preserves strict force-label document schemas without
  changing the learning pipeline or its schemas.
- Legacy adsorption report APIs still provide their specialized force/ionic
  tables, but delegate convergence facts to these owners. Their maintained
  independent INCAR readers and historical electronic-success rules were removed.
  The baseline direct-file CLI remains standard-library-only (tested with Python
  `-S` from an unrelated temporary directory). The pre-existing remote backfill entry ships the current shared parser source
  in memory; it does not maintain a second remote implementation or install files.
- `scripts/ts_strategy_engine/contract.py` remains the semantic owner. Identity
  hashes remain necessary and do not replace semantic checks. Valid raw and
  normalized contracts retain their existing schema meaning and hashes.
- `scripts/scientific_validation.py` owns finite scalar and range checks only;
  it contains no scientific thresholds or acceptance policy.
- `fingerprint.py` describes labelled chemistry, structural comparison and result
  identity; `strategy.py` checks those events against existing family definitions.
  Planning gets species from the already checked initial endpoint. Optional
  `atom_symbols` metadata must cover the full map and agree with endpoint labels.
  The existing `fingerprint_id` remains unchanged for path-binding compatibility.
  Exact result reuse additionally requires endpoint/result IDs, atom map,
  compatibility and chemical-event identity, plus existing accepted evidence.
- Old stored fingerprints lacking species/event evidence are not silently promoted
  to reusable scientific results. They require re-derivation from their original
  validated inputs. No historical artifacts or registry records were rewritten.
- Existing external-facing parser names/signatures were searched across imports,
  CLIs, tests and docs. Legacy INCAR aliases remain direct references. Tests cover
  both legacy summary schemas and the richer optional cycle model.

The repository-owned INCAR reader is retained because consumers require strings
(including repetition/logical tokens) and fail-closed malformed-token handling;
using the installed pymatgen `Incar.from_str` directly would change coercion and
silently skip some malformed assignments. The adsorption typed consumer builds
`Incar` from the canonical parsed mapping instead of introducing another lexer.
Supported syntax follows the [VASP INCAR documentation](https://vasp.at/wiki/INCAR).
Final numeric convergence checks use both energy deltas described by
[VASP EDIFF](https://vasp.at/wiki/EDIFF) and [OSZICAR](https://vasp.at/wiki/OSZICAR).

## Scientific behavior boundaries

Intentional changes reject invalid or incomplete states: stale historical SCF
success, incomplete current cycles, missing partial convergence evidence,
nonfinite/invalid numeric values, self-consistent but semantically invalid
contracts, and chemically wrong family/result matches. Existing thresholds,
EDIFF comparisons, VASP settings, TS grading/acceptance and B1 authorization
semantics were not relaxed or retuned. Complete final OUTCAR evidence can confirm
an otherwise partial OSZICAR SCF row; missing d eps alone does not defeat current
explicit complete OUTCAR convergence evidence.

No GPU/VASP jobs, scheduler submissions, remote audits, registry writes, model
operations or calculation-output modifications were run. Configurations, schemas,
production data, POTCAR and model weights are outside the diff.

## Exact files changed

- `modules/fe_convergence_baseline/validate_baseline.py`
- `reports/refactor_audit/B2_completion_report.md`
- `scripts/README.md`
- `scripts/adsorption/analyze_fe110_ch_h_relaxation.py`
- `scripts/adsorption/backfill_step12a_registry.py`
- `scripts/adsorption/finalize_step12a_gas_references.py`
- `scripts/adsorption/preflight_fe110_adsorption.py`
- `scripts/adsorption/preflight_gas_references.py`
- `scripts/adsorption/register_step12a_gas_reference_submission.py`
- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`
- `scripts/neb_agent/analyze_neb_outputs.py`
- `scripts/neb_agent/diagnose_path_geometry.py`
- `scripts/neb_agent/path_quality_control.py`
- `scripts/neb_agent/path_quality_service.py`
- `scripts/neb_agent/utils_vasp.py`
- `scripts/scientific_validation.py`
- `scripts/ts_strategy_engine/contract.py`
- `scripts/ts_strategy_engine/dimer_analysis.py`
- `scripts/ts_strategy_engine/dimer_gate_common.py`
- `scripts/ts_strategy_engine/fingerprint.py`
- `scripts/ts_strategy_engine/strategy.py`
- `scripts/ts_strategy_engine/workflow.py`
- `scripts/ts_validation/analyze_vfa.py`
- `scripts/vasp_result_gate.py`
- `tests/test_b2_scientific_contract.py`
- `tests/test_code_structure.py`
- `tests/test_ts_strategy_engine.py`
- `tests/test_vasp_output_streaming.py`

## Validation

Validation uses the isolated source-release worktree based on the specified B1
commit, preserving all unrelated modifications in the desktop checkout. Local
runtime is Windows/Python 3.13.9 with Git Bash; GitHub uses Ubuntu/Python 3.11.

Final focused B2/TS/architecture command:

```text
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_ts_validation.py tests/test_ts_validation_pipeline.py tests/test_code_structure.py
```

Final focused result: 119 passed in 5.81s, exit 0. This includes 83 dedicated B2
cases and the existing TS and architecture suites. Eight final compatibility
cases cover the standard-library direct CLI, nonfinite VFA frequency/vector rows,
and overflowing numeric text in scientific policies.

Supplemental B1/TS/interface regression command:

```text
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_vasp_result_gate.py tests/test_vasp_output_streaming.py tests/test_ts_strategy_engine.py tests/test_ts_validation.py tests/test_ts_validation_pipeline.py tests/test_neb_pilot_validation.py tests/test_neb_execution_gate.py tests/test_neb_submission.py tests/test_neb_path_quality_control.py tests/test_execution_lifecycle.py tests/test_execution_gate_compatibility.py tests/test_gpu_execution_lifecycle.py tests/test_aqcat25_path_active_learning.py tests/test_aqcat25_ts_active_learning.py tests/test_code_structure.py
```

Supplemental result: 412 passed in 148.97s (0:02:28), exit 0. The final added numeric-text
policy case is covered by the final focused and full runs above/below.

Required exact CI commands:

```text
python -m ruff check scripts modules tests
python -m pytest -o addopts= -q
```

Ruff: All checks passed, exit 0. `git diff --check` also passed.
The exact 28-file report list and protected B1/configuration/schema/data/shell
paths were independently checked against the B1 base.
Full pytest: 835 passed in 220.62s (0:03:40), exit 0. The preceding full run passed 827 tests
in 219.31s before eight additional CLI/VFA/numeric-text regressions were added.

Initial broad validation exposed strict force-label schema incompatibility and
partial OSZICAR pilot fixtures. These were corrected through the compatible
six-field summary and current explicit OUTCAR evidence, without editing ML
schemas, pilot fixtures or TS acceptance rules. Architecture tests guard shared
parser/semantic ownership alongside the unchanged B1 ownership constraints.

The startup repository-state audit exited 0 with existing external-worktree
warnings. Read-only sync preflight identified unrelated task/projection writes
(`proposal-fee2a84125c5942786d73c1d`, `proposal-3d6eb2a10df8ce681cd60ffb`) and the
existing error `version 1 archive/delete applies to files only`. Those projections
were not applied because they target runtime state outside B2; no state-manager
repair is included.

## Remaining production-only uncertainties

- Real VASP/VTST version-specific and alternative solver output variants beyond
  the regression fixtures were not executed. Unknown/incomplete cycle evidence
  cannot establish PASS. Deployment should check representative retained output
  copies without resubmitting calculations.
- Existing remote backfill source transport was tested in a temporary local
  runtime, not over SSH against an HPC deployment. The remote Python/runtime and
  filesystem availability remain unverified.
- Missing species in historical fingerprints requires validated-source
  re-derivation before chemical-event reuse; no automatic migration was performed.
- Existing B1 production uncertainties (scheduler response loss, privileged
  concurrent filesystem changes and abrupt process/storage loss) remain unchanged.


## B2.1 scientific acceptance boundary closure

Status: PASS on the complete publication snapshot.

This supplement closes two gaps in the original B0/B2 package. The preceding B2
results describe commit 99b82eab; they did not establish these missing boundaries.

| Original audit mapping | Current B2 mapping | Correction |
| --- | --- | --- |
| B0 B2-03: finite final energies | B2-04 | Finite values at final-energy acceptance, arithmetic output, formal registration consumers, template evidence and export. |
| B0 B2-04: cross-DIMER/VFA identity | B2-06 | Same current DIMER analysis, saddle geometry, contract/map/method and applicable handoff/scope/reviews before TS_ACCEPTED. |

### Source and publication ownership

All B2.1 implementation and fixture changes were made in the real development
source, C:/Users/86177/Desktop/work. Before edits, the scoped files were clean and
their normalized source digests matched public base
99b82eab15aaf22ef7dc880af54e77314eb49b53. Existing unrelated changes were inventoried
and preserved; no reset, clean, stash or production-data operation was used.

The existing release worktree is only a validation/publication snapshot. Its
task-owned files were copied byte-for-byte from work; all remaining tracked files
stay on the existing sbq123 release history. Tests run against this complete
repository snapshot, not an extracted standalone reproduction. No repair was
developed in the release worktree. Publication remains
q2214299493/sbq123, codex/b2-scientific-contract, without a merge or B3 work.

Source/test snapshot (the 11 changed Python files, sorted path-to-file-SHA256
mapping serialized as compact sorted JSON): 42b3b5cc3f797d3e01bd6100cf0256da35db2b0a372d1d81940d82d2f585c292.
The full snapshot is public base 99b82eab plus exactly the task-owned changes
listed below. Interpreter: 3.13.9 | packaged by Anaconda, Inc. | (main, Oct 21 2025, 19:09:58) [MSC v.1929 64 bit (AMD64)].

### Implemented boundary behavior

- Both analyzers support write_output=False. The pipeline reuses their original
  scientific parsing and acceptance logic without rewriting source records.
  DIMER summaries bind raw inputs, modes/reviews, scheduler evidence and final
  structure contents. VFA summaries bind the frequency output, POSCAR, review,
  applicable scope/soft review and policy, and retain the full supplied contract.
- validate_dimer_vfa_binding in the existing VFA owner verifies current manifests,
  actual DIMER analysis identity and contents, actual final-saddle/VFA geometry,
  and a semantically normalized contract with matching map and compatibility.
  It reproduces both summaries from current inputs, rather than trusting embedded
  PASS booleans. Review identity/approval is checked independently of optional
  frequency classification. Handed-off geometry is compared at the existing
  POSCAR writer's 12-digit serialization precision; no force, frequency or
  geometry acceptance threshold was changed.
- The existing scope checks were moved verbatim from submission preflight to
  prepare_vfa_from_ts_image.vfa_scope_checks. Both preflight and scientific
  validation call that owner. B1 reservation, authorization, upload, receipt and
  GPU wrapper behavior is unchanged; no parallel executor or scope validator was
  added. Source paths are canonicalized when produced so changing the caller's
  directory does not invalidate a legitimate source chain.
- Missing optional topology remains optional. Explicit missing/corrupt/stale
  topology, branch plan, VFA file or applicable review is an error or blocking
  result. Multi-TS acceptance binds the selected local contract and the candidate
  ID in the original DIMER handoff. Frequency-only soft review cannot authorize
  final acceptance. A matching valid local segment is tested positively.
- matched_static_convention calls the existing finite_number validator for every
  accepted total energy. barrier_values validates inputs and all three subtraction
  outputs through validate_barrier_values, including finite-input overflow.
  Negative DFT total energies remain valid; the original strict negative-barrier
  rejection is unchanged. Unit, method, source-file/job and registration transaction
  checks are retained.
- Formal barrier registration already consumes these owners; no duplicate checks
  were added to evidence.py. Accepted template evidence and Excel promotion now
  reject nonfinite stored barriers; eV result export rejects missing/nonfinite
  numeric energy. Tests use only temporary SQLite registries and synthetic data.

No downhill-connectivity requirement, full Hessian, new frequency threshold,
changed VASP parameter, new TS grading policy, registry schema or production
data change is included. Optional classification and thermochemistry/kinetics
eligibility retain their existing policy. Original behavioral assertions remain;
old positive fixtures now contain the actual matching evidence previously absent.

### Exact B2.1 task-owned files

- `scripts/neb_agent/submission.py`
- `scripts/ts_strategy_engine/dimer_analysis.py`
- `scripts/ts_strategy_engine/matched_static_evidence.py`
- `scripts/ts_strategy_engine/templates.py`
- `scripts/registry_excel_promotion.py`
- `scripts/ts_validation/analyze_vfa.py`
- `scripts/ts_validation/prepare_vfa_from_ts_image.py`
- `scripts/ts_validation/validation_pipeline.py`
- `tests/test_b21_scientific_acceptance.py`
- `tests/test_ts_validation.py`
- `tests/test_ts_validation_pipeline.py`
- `modules/ts_vibrational_validation/README.md`
- `reports/refactor_audit/B2_completion_report.md`

### Executed validation

The first new regression run against the unmodified production implementation
failed as required: 38 failed, 3 passed, 0 skipped in 7.94s, exit 1:
python -m pytest -o addopts= -q tests/test_b21_scientific_acceptance.py --tb=no

Further adversarial regressions were also run before their fixes: 7 failures for
self-consistent wrong geometry/unapproved review/export consumption; 3 failures
for explicitly supplied invalid branch plans; and 1 failure for relative sources
read from a different caller directory. Their matching-object positive controls
were retained. The final file contains 53 regressions, including direct calls to
evaluate_validation_pipeline and the formal barrier registration transaction.

Final expanded B2/TS/barrier/B1 regression command:

    python -m pytest -o addopts= -q tests/test_b21_scientific_acceptance.py tests/test_b2_scientific_contract.py tests/test_ts_validation.py tests/test_ts_validation_pipeline.py tests/test_ts_strategy_engine.py tests/test_registry_excel_promotion.py tests/test_code_structure.py tests/test_execution_lifecycle.py tests/test_gpu_execution_lifecycle.py tests/test_neb_submission.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_artifact_io.py tests/test_execution_backends.py tests/test_vasp_result_gate.py tests/test_vasp_output_streaming.py

Final expanded result: 465 passed, 0 failed, 0 skipped in 149.59s (0:02:29), exit 0.

Required complete repository commands on the same pending-release source snapshot:

    python -m ruff check scripts modules tests
    python -m pytest -o addopts= -q

Final Ruff result: All checks passed, exit 0. Scoped git diff --check passed.
Final complete pytest result: 888 passed, 0 failed, 0 skipped in 231.41s (0:03:51), exit 0.

The real work checkout's start audit returned 0 errors and five pre-existing
warnings (external worktrees and unrelated root items). Managed runtime projections
are outside this patch and were not used as scientific evidence. Read-only sync
preflight found the existing error "repository item changed after classification:
sbq_catalyst_agent_workflow.egg-info/PKG-INFO" and unrelated projection proposals
proposal-fbdd167f3d1d22bcc040c277, proposal-fc9e18ea99ec76fdad03d6bd and
proposal-11c7077298b7b7ea07cbf254. No projections or state events were applied.

### Remaining production-only uncertainties

No SSH, cluster/VASP/GPU job, real registry query, model operation or historical
result rewrite was performed. Tests verify synthetic complete and damaged files,
source identity, read-only replay, SQL rejection/rollback and existing B1 behavior;
they do not establish any production TS or barrier.

Historical summaries missing current source bindings require reanalysis and, when
referenced hashes change, the existing reviewer-controlled handoff/scope/review
refresh. They are not silently migrated or accepted, and this does not authorize
rerunning a calculation. Multi-segment handoffs must carry their reviewed candidate
identity. Real retained output variants and deployed cluster environments remain
unverified. As before, read/verify checks are not an immutable snapshot against
concurrent privileged changes to source files.
