# Transition-State Vibrational Validation Protocol

## Purpose

Every NEB-, CI-NEB-, or DIMER-derived transition-state candidate must be graded before it can supply a barrier or rate constant to the project database, MKM, or KMC.

## Required Evidence

1. Convergence evidence from NEB, CI-NEB, or DIMER. For DIMER, normal VASP
   completion, electronic convergence, maximum atomic force meeting `EDIFFG`,
   negative curvature, and reviewed hash-bound initial/final modes are hard
   requirements. DIMCAR `Force` and `Torque <= DFNMin` are soft diagnostics.
   If either misses its target, frequency handoff requires an explicit
   SHA-256-bound human review acknowledging the exact warnings.

The DIMER VASP force component is evaluated from the last complete
`FORCES: max atom, RMS` line in `OUTCAR`: `max atom <= abs(EDIFFG)` passes.
The RMS value is recorded but is not a substitute for the maximum atomic
force. This force pass does not waive any other saddle, frequency, mode, or
provenance requirement.
2. Frequency values and eigenvectors from the TS frequency calculation.
3. A visual or quantitative assignment of the imaginary mode to the intended reaction coordinate.
4. TS geometry sanity checks, including reaction-specific bond lengths and surface contacts.
5. Source job IDs, paths, settings, and reviewer notes.
6. Reaction-contract, atom-map, compatibility, saddle-source, and
   frequency-output file bindings.

The project default is a contract-defined local finite-difference partial
Hessian for every reaction. The active set must contain all reaction atoms and
must be recorded and reviewed; it may also contain directly coordinated local
surface atoms. A full Hessian over all movable slab atoms is not required for
TS acceptance. Expand the active set only when the target-mode assignment is
ambiguous, local surface-mode coupling is unresolved, or an explicit request
requires it. Frequency reports must identify the result as partial-Hessian.
For ZPE or thermal corrections, use one consistent reviewed active-set
definition for IS, TS, and FS.

For DIMER-derived candidates, bidirectional downhill connectivity is optional
diagnostic evidence and is not part of TS acceptance. NEB/CI-NEB candidates
retain their existing connectivity policy unless separately changed.

The numerical boundary between a meaningful imaginary mode and a small soft
mode is **Needs confirmation** for automatic multi-mode classification. A
normally completed DIMER frequency calculation with exactly one raw imaginary
mode may still receive Grade A when the mode is explicitly reviewed and
accepted as the target reaction coordinate; this reviewed single-mode rule does
not require a separate VFA A/B/C classification stage. Multiple or borderline
modes remain `Ungraded` until the configured soft/meaningful thresholds resolve
them. The frequency setup and review must be stored with each result; optional
displacement/connectivity diagnostics retain their own provenance when present.

Multiple TS candidates and multiple imaginary modes are separate cases. Two
imaginary modes on one structure remain one unresolved higher-order/soft-mode
candidate. Two independently reviewed path maxima become separate TS
validation branches only after the intervening structure is independently
relaxed and accepted as a local minimum. The branches must use local endpoint
contracts (`IS <-> IM` and `IM <-> FS`) so each imaginary mode is assigned to
the correct local reaction step.

An incomplete frequency calculation is always `Ungraded`. Grade C from
frequency count requires normal completion and configured thresholds: zero
meaningful imaginary modes or more than one meaningful imaginary mode is a
Grade C condition. Additional modes between the configured soft and meaningful
limits remain `Ungraded` for review; raw imaginary-mode count alone cannot
produce Grade C.

The frequency POSCAR, source saddle, VFA handoff, and frequency OUTCAR must be
mutually SHA-256-bound. Matching a calculation ID or contract string without
those file bindings is insufficient.

## Grade A: Eligible for the Validated Database

All criteria must be satisfied:

- NEB/CI-NEB or DIMER is converged.
- A DIMER-derived candidate has negative curvature and converged VASP maximum
  atomic force. Its DIMCAR Force/Torque soft checks either pass, or an explicit
  `accept_for_ts_validation` review accepts their residuals. A weaker
  `allow_frequency_handoff` review authorizes only the diagnostic frequency
  calculation and cannot by itself satisfy Grade A.
- Exactly one clear imaginary frequency is present.
- Its eigenvector corresponds to the intended reaction coordinate.
- The TS structure has no evident geometric abnormality.
- When automatic frequency thresholds are unset, a hash-bound explicit review
  may establish the preceding two items only for a complete single-imaginary-
  mode DIMER result; it cannot waive a second mode, incomplete output, or an
  ambiguous mode assignment.

Database action: accept as a validated TS and allow use in thermochemistry, MKM, and KMC after the remaining free-energy requirements are met.

## Grade B: Retain for Manual Review

- One principal imaginary frequency is present.
- One additional small soft mode may be present.
- The principal mode is broadly consistent with the intended reaction.
- Notes and a repeat or manual review are required.

Database action: retain in a review table or quarantine state. Do not automatically use it for MKM or KMC.

Analyzer action: Grade B requires exactly two imaginary modes, an explicitly
selected principal-mode index, `mode_assignment=accepted`, and a reviewed
`soft_mode_assessment=one_additional_small_soft_mode_repeat_required` with
`repeat_required=true`. Without that explicit assessment, two imaginary modes
remain `Ungraded`; multiple clear imaginary modes are Grade C.

Optional bidirectional downhill analysis uses
`configs/ts_connectivity_gate.yaml`. Its result is diagnostic for DIMER and
does not alter the DIMER/VFA grade.

## Grade C: Not Eligible for MKM/KMC

Any one of the following is sufficient:

- No imaginary frequency is present.
- Multiple clear imaginary frequencies are present.
- The imaginary mode does not represent the intended reaction.
- The TS structure is abnormal.

Database action: reject from the validated kinetic dataset. Preserve provenance and the rejection reason for diagnosis.

## Classification Precedence

1. A Grade C condition overrides Grade A or B indicators.
2. Grade A requires complete evidence with no unresolved validation item.
3. Grade B is a temporary review state, not a weaker automatic acceptance state.
4. An unperformed frequency calculation is `Ungraded`, not Grade A.

## Required Database Fields

- reaction and TS identifiers
- source method, job ID, and calculation path
- calculation, job, input-file, and output-file registry IDs
- convergence status
- all imaginary frequencies in `cm^-1`
- principal-mode moving atoms and qualitative mode assignment
- soft-mode count and interpretation
- geometry sanity status and key distances
- optional positive/negative displacement files, connectivity job records, and
  connectivity-report file ID/SHA-256 when that diagnostic is performed
- grade: `A`, `B`, `C`, or `Ungraded`
- kinetic eligibility: `true` only for Grade A
- reviewer, review date, notes, and provenance
- reaction-contract, atom-map, compatibility, source-saddle, and evidence-file IDs

The reaction-coordinate imaginary mode must be excluded from the TS vibrational partition function. No soft mode may be silently removed or converted without a documented method and review.

The converged NEB profile is diagnostic. A technically accepted DIMER result
may supply the TS member of the formal energy chain. Reported forward and
reverse barriers require compatible registered IS/TS/FS final `OUTCAR` `TOTEN`
values under one reference convention and hash-bound source outputs.
