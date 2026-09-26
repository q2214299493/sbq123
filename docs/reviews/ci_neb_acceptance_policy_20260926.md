## 2026-09-26 - CI-NEB acceptance without mandatory downhill connectivity

- User explicitly cancels CI-NEB positive/negative downhill connectivity as an
  acceptance requirement. It remains an optional diagnostic, never a fabricated
  connectivity PASS. Ordinary NEB policy is unchanged.
- Acceptance still reparses the actual current climbing-image VASP path,
  convergence, endpoint/contract binding, reviewed continuity, saddle/frequency
  geometry, and local target-mode evidence. A complete single imaginary mode
  may use an explicit bound target-mode review when numeric soft-mode thresholds
  are unset; multiple/incomplete/ambiguous modes are not waived.
- INT06-to-MID evidence: CI9796856 peak04 and local VFA9798421, sole imaginary
  mode15 386.611701 cm-1 assigned to H49 migration. Partial Hessian is not
  size-converged thermochemistry or a complete kinetic model.
- Earlier GPU-to-Dimer failures cannot be attributed solely to GPU geometry:
  Dimer9753172 diverged electronically before center movement despite a
  same-geometry static SCF pass; Dimer9781734 used unconverged SCF forces in
  22/24 evaluations; a pure VASP ordinary-NEB seed also failed Dimer refinement.
  Current VASP CI succeeds, but method/EDIFF changes prevent a single-cause
  inference. Seeded GPU1788 preserves the current VASP corridor in eight steps;
  this verifies local stability, not independent saddle discovery.
