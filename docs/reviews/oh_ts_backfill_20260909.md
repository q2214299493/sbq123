# O–H TS evidence backfill — 2026-09-09

## Scope and result

User authority: automatically backfill eligible completed records without a
separate reminder. This does not waive outstanding scientific review or authorize
new calculations. Branch: MID9737143 → FS-A9725471, not the full IS-A → FS path.

Canonical registry batch `backfill_oh_dimer9746548_vfa9747902_20260909` inserted
35 rows: 2 calculations, 2 jobs, 2 DONE status events, 27 hashed files and 2 reviews.
Both calculations remain `needs_review`; no accepted TS, barrier, successful
strategy template or formal topic-table result was created.

Evidence and immutable plan/approval/receipt are under
`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/oh_ts_registration_audit_20260909/`.
Plan SHA-256: `eb64fb492050b858f387d17ebd879bd949bf5045149f9c354d9fcc3b99589d20`.

## Verified evidence and remaining acceptance

- Dimer9746548: scheduler DONE, normal termination, final electronic convergence;
  atomic maximum force 0.018201 eV/Å. DIMCAR Force 0.06398, Torque 1.2054,
  curvature -11.8812 eV/Å². Current review permits frequency handoff only.
- VFA9747902: scheduler DONE, normal termination, final electronic convergence;
  one imaginary mode, 1407.654162 cm^-1, mode 6. Partial Hessian: O48/H50
  (zero-based 47/49), six degrees of freedom. This is not a full-system Hessian.
- Formal acceptance still requires a current hash-bound residual review allowing
  `accept_for_ts_validation` and the owning module's bound final mode validation.
  The existing frequency-only review is preserved, not silently broadened.
- After those requirements and the execution gate pass, automatically register
  eligible TS evidence, compatible final TOTEN barrier, topic-table result and
  method-only strategy template through existing canonical writers. Do not copy
  atom indices, structures, MODECAR or barriers into a new reaction.
- No new VASP/GPU job was submitted. No thermochemistry or kinetics claim is made.

## Parser repair and verification

The numbered OUTCAR electronic-loop parser incorrectly created an extra target
when an inner `energy(sigma->0)` line preceded the EDIFF termination marker.
The marker now stays with its numbered loop. Historical scientific evidence and
its hash-bound reviews were not overwritten.

Reparsed real outputs: Dimer has 36 electronic targets, VFA has 13; both final
SCF checks pass. Regression coverage includes a subsequent unfinished target,
which must remain unconverged. Syntax, Ruff and the 40-test related VASP-output,
result-gate, TS-validation and execution-gate suite passed.

Registry schema validation and SQLite integrity check passed. Exact replay
returned `already_applied: true`; verification found 27 files, 2 reviews and zero
formal result rows for these calculations. An initial apply using the batch hash
was rejected before mutation; the reviewed plan hash was then used successfully.

`repo-state sync --safe-only` remains blocked by unrelated conflicting live events
`task-completed-966f70761e2de2c804e6dced` and
`task-migration9748648-open-20260909-v2`. No lifecycle event was silently changed.

## Completion discipline

At each completed-job checkpoint, register eligible raw evidence first, then
check TS acceptance, compatible barrier, topic table and strategy registration
separately. Automatically fill only eligible missing records, use canonical
idempotent writers, and name every remaining blocker. A registered DONE job is
not an accepted TS. No separate reminder is needed once acceptance is established.
