---
name: fe-vasp-incar-custodian
description: Diagnose and safely tune or generate reviewable INCAR recommendations for Fe-based VASP adsorption, endpoint, NEB, CI-NEB, DIMER, and frequency calculations. Use when Codex must analyze SCF or optimizer failures, compare an INCAR with project-approved settings, generate dynamic species-separated MAGMOM values, apply custodian-like static recovery, or decide that an upstream geometry/path problem blocks INCAR tuning.
---

# Fe VASP INCAR Custodian

Use this skill only for INCAR ownership: structured read/write, error classification, conservative parameter changes, validation, and reports. Do not let it replace endpoint, path, DIMER-mode, or vibrational scientific review.

## Workflow

1. Read the project `AGENTS.md`, method protocol, current state, and relevant scientific module.
2. Inspect the current INCAR, POSCAR/CONTCAR, KPOINTS, diagnostics, and live output evidence.
3. Run upstream geometry/path diagnostics first. If they report endpoint/path failure, return `STOP_INCAR_TUNING_AND_REBUILD_PATH` without creating a continuation INCAR.
4. Use `scripts/incar_custodian.py`; it uses pymatgen for INCAR/POSCAR parsing and never edits the source INCAR.
5. Change the smallest parameter set justified by one diagnosed failure. Project/material overrides take precedence over generic profiles.
6. Diagnose in read-only mode by default. Persist candidates and review artifacts only with explicit `--write-artifacts`.
7. Review persisted artifacts before any submission and register only accepted recommendations. This skill never submits VASP or accepts a TS.

## Commands

```powershell
$tool = (Resolve-Path '.\skills\fe-vasp-incar-custodian\scripts\incar_custodian.py').Path
python $tool --help
python $tool --mode tune --workdir RUN --incar RUN/INCAR --poscar RUN/01/POSCAR --calculation-type pre_NEB --surface-family metal_fe --material Fe110 --failure-type scf_failure --read-only
python $tool --mode tune --workdir RUN --incar RUN/INCAR --poscar RUN/01/POSCAR --calculation-type pre_NEB --surface-family metal_fe --material Fe110 --failure-type scf_failure --write-artifacts
```

No output flag and `--read-only` both print JSON without creating files.
`--dry-run` is a backward-compatible alias for `--read-only`.
Only `--write-artifacts` writes candidates and reports. Existing candidate
outputs are never overwritten.

## Ownership Boundaries

- Adsorption geometry/energy consistency: project adsorption module.
- Endpoint and path validity: project NEB module.
- DIMER method, MODECAR, and convergence: project DIMER module.
- Frequencies, imaginary modes, connectivity, and A/B/C grade: TS validation module.
- This skill consumes those modules' JSON decisions and owns only INCAR recommendations.

Do not adopt DIMER algorithms, DFT+U, oxide MAGMOM patterns, cluster commands, or POTCAR choices without an approved project source.

## Failure Policy

- SCF failure: inspect NELM exhaustion/error evidence; adjust electronic tags only.
- Slowly decreasing force: prefer increasing NSW only.
- Plateau/oscillation with valid geometry: keep no-climb, reduce optimizer movement when supported, and avoid changing many tags at once.
- Walltime with valid geometry: restart from CONTCAR with minimal changes.
- Collision, penetration, desorption, atom mapping error, image jump, or stable intermediate: block INCAR tuning and return upstream.
- Iron oxide without an approved magnetic pattern: require user confirmation; never invent U or oxidation states.

Read `references/profiles.yaml` only when generating or validating a calculation-type profile. Read `references/error_rules.yaml` only when diagnosing output failures or blockers.

## Persisted Outputs

- Generated only with explicit `--write-artifacts`
- `INCAR.recommended` when a safe candidate exists
- `incar_change.json`
- `incar_validation.json`
- `incar_change_report.md`
- `vasp_error_report.json` for parse-errors mode

The Markdown report is UTF-8 with BOM for correct Windows PowerShell display.
All outputs are recommendations until human scientific review and project registration are complete.
