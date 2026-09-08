# NEB Literature-Prior Workflow Integration

## Source

- Imported specification: `D:/codex_neb_literature_prior_workflow.md`
- SHA256: `28821FB3A0AE34EBDBA9B9CEED54F5E0E1158EEA719BDF09C47A28C7B367D29F`
- Policy: requirements were normalized into existing project modules; the source text was not copied into project documentation.

## Result

- Replaced the former NEB module summary with one canonical closed-loop workflow.
- Added endpoint, literature-prior, ASE IDPP path, geometry, INCAR-candidate, NEB-output, and replan utilities.
- Added non-destructive restart, crop, split, DIMER-handoff, and vibrational-handoff tools.
- Kept DIMER settings and vibrational settings in their own modules. The imported generic DIMER `IBRION=44` example was not allowed to replace the current VTST DIMER method.
- Kept active Fe(110) VASP settings authoritative over generic templates.

## Acceptance

- Python syntax compilation: passed.
- Required six `--help` checks: passed.
- DIMER and VFA handoff `--help`: passed.
- Current Fe(110) 00/09 endpoint compatibility: passed, 47 atoms, `Fe C O`, Selective Dynamics preserved.
- Dynamic MAGMOM: `45*2.2 1*0.0 1*0.0`; C and O remain separate species groups.
- Fe110 project override candidate: `ALGO=All`, `LREAL=.FALSE.`, `SIGMA=0.2`, `IMAGES=8`.
- Ordinary IDPP dry-run: safely returned `REPLAN_REQUIRED` because C-O backtracked by `0.498 A`; no VASP job was submitted.

## Remaining Manual Inputs

- approved POTCAR path and provenance
- endpoint-matched KPOINTS source for each material
- approved LSF script and VASP executable
- real structured literature-search output for a target reaction
- non-Fe110 material magnetic overrides, especially carbides and oxides
- human visual review plus `dist.pl` and `nebmovie.pl 0` before submission
