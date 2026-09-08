# TS Vibrational Validation

## Purpose

Determine whether a NEB/CI-NEB/DIMER candidate is a first-order saddle for the intended reaction and whether it can enter kinetics.

## Workflow

1. Receive a contract-bound, technically converged candidate through
   `python -m scripts.ts_strategy_engine.cli vfa-prepare`; arbitrary structures
   and mismatched NEB/DIMER analyses are rejected. DIMER candidates must pass
   the VASP atomic-force/negative-curvature hard gate. DIMCAR Force/Torque
   misses require a hash-bound human review; a frequency-only approval does not
   promote the candidate to a validated TS.
2. Verify source saddle-search convergence and geometry.
3. Approve the frequency method here, then use `modules/incar_custodian/` to validate its INCAR before running it.
4. Record every imaginary frequency and eigenvector.
5. Assign the principal mode to the intended bond-breaking/forming motion.
6. For DIMER-derived candidates, accept the TS after DIMER convergence and one
   accepted target imaginary mode. Bidirectional downhill connectivity and
   A/B/C grading are not DIMER acceptance requirements.
7. Register the validation evidence, then compute a barrier only from
   compatible accepted IS/TS/FS final `OUTCAR` `TOTEN` records. For the active
   Fe(110) branch these use `ISMEAR=1`, `SIGMA=0.20 eV`; no extra single-point
   is required.

The existing connectivity commands remain available as optional diagnostics
and for non-DIMER policies. Their output cannot override failed DIMER or
frequency evidence.

## Resumable Automated Pipeline

`validation-pipeline-status` is the single stage evaluator for the automatic
post-DIMER sequence. It never submits directly and never duplicates DIMER,
VFA, or VASP-input logic. A monitor may advance only through the
existing execution gate and `scripts.neb_agent.submission` executor:

1. require DIMER normal completion, electronic convergence, VASP maximum-force
   convergence, and negative curvature; unresolved DIMCAR Force/Torque remains
   a soft warning that needs its existing bound review;
2. prepare, gate, submit, and monitor VFA;
3. require a complete VFA with exactly one raw imaginary mode, an identified
   principal mode, reaction-atom overlap, accepted mode assignment, and passed
   TS geometry review;
4. record the accepted TS result. Optional classification output may remain
   `NOT_EVALUATED`; it does not block DIMER TS acceptance.

Two distinct rules must not be conflated:

- two imaginary modes in one candidate trigger higher-order-saddle/soft-mode
  review; they do not create two TS branches;
- two independently reviewed path maxima require a converged intermediate and
  two segment-local contracts (`IS <-> IM` and `IM <-> FS`). Each segment runs
  its own DIMER and VFA sequence so its imaginary mode is assessed against the
  correct local reaction definition.

A complete DIMER/frequency result with an accepted target mode is recorded as
`TS_ACCEPTED`. Numerical frequency thresholds are not invented and optional
classification remains `NOT_EVALUATED` when they are unset.

The machine-readable stage policy is `configs/ts_validation_pipeline.yaml`.
The evaluator is resumable and reports one `status` and one `next_action`; file
existence alone cannot advance a stage.

## Handoff

Database and downstream eligibility follow only `docs/10_TS_VALIDATION_PROTOCOL.md`.

The reaction-coordinate imaginary mode is excluded from the TS partition
function. The active partial-Hessian settings are owned by
`configs/true_fe110_production.yaml`; reaction atoms must be active and fixed
slab atoms must remain fixed. The default scope is the contract-defined local
reaction center; a full movable-slab Hessian is not mandatory. The active set
must receive a bound scope review, and it is expanded only for ambiguous mode
assignment, unresolved local surface coupling, or an explicit request. IS, TS,
and FS thermal corrections must use the same reviewed local active-set
definition and be labelled as partial-Hessian results.

## Outputs

- frequency and eigenvector record
- inspected target-mode assignment
- optional positive/negative displacement and endpoint-connectivity evidence,
  when a diagnostic or non-DIMER policy requests it
- A/B/C grade and database-eligibility decision

## Done Criteria

All required evidence is traceable and reviewed; only Grade A candidates are eligible for thermochemistry or kinetics.
