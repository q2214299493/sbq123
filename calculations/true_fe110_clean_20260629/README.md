# True Fe(110) Clean-Slab Pre-Submission Snapshot

Status: `SUBMITTED_PEND`

## Paths

- Bulk source: `sunboquan-codex:~/sbq/c_fe/CONTCAR`, job `9556519`.
- Fe(110) project root: `sunboquan-codex:~/sbq/Fe110`.
- Current clean-slab input: `sunboquan-codex:~/sbq/Fe110/fe110`.

## Bulk Basis

- Scheduler: `DONE`.
- VASP: reached required accuracy.
- Final cubic lattice: `a=2.8269483674 A`.
- Final external pressure: `1.50 kB`.
- Final magnetic moment: approximately `4.340 mu_B/cell`.

## Slab Model

- Facet: true bcc alpha-Fe(110).
- Lateral cell: primitive-surface `3x3`.
- Thickness: five layers, nine Fe per layer, 45 Fe total.
- Vacuum: `15.0 A`.
- Fixed region: bottom two layers, 18 Fe atoms.
- Initial interlayer spacing: `1.998954 A`.
- Minimum Fe-Fe distance: `2.448209 A`.

Five layers is the user-selected model for this clean-slab input. Seven layers remains only the convergence reference until the matched five-versus-seven-layer adsorption/reaction observable gate is completed.

## Numerical Protocol

- `GGA=PE`, approved Fe PAW-PBE POTCAR, `ENCUT=400 eV`.
- Gamma `5x5x1`.
- `ISPIN=2`, `MAGMOM=45*2.2`.
- Relaxation: `EDIFF=1E-5`, `EDIFFG=-0.02 eV/A`, `ISMEAR=1`, `SIGMA=0.20 eV`, `ISIF=2`.

No Fe(110) job may be submitted until the user reviews the remote POSCAR and INCAR.

## Submission

- User approval received before submission.
- Command: `bsub vasp541std.lsf`
- Job ID: `9557161`
- Submission checkpoint: `2026-06-29 12:51 CST`
- Scheduler: `PEND` in `Gkn_normal`
