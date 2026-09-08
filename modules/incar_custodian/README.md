# INCAR Custodian

## Purpose

Provide the single project layer for reviewable Fe-based INCAR recommendations after the owning scientific module passes its structure/path/mode gate.

## Project Inputs

- current INCAR and POSCAR/CONTCAR
- calculation type, surface family, material, and upstream diagnostics
- `configs/true_fe110_production.yaml` for Fe(110) scientific settings;
  `configs/incar_custodian/project_profiles.yaml` only maps calculation stages
  and material-specific magnetic/recovery policy to that authority
- OUTCAR/OSZICAR or a structured failure diagnosis

## Ownership

- Scientific modules own geometry, path, DIMER method/MODECAR, frequencies, connectivity, and acceptance.
- This module owns stage mapping, diagnosed recovery changes, recommendation provenance, and registry handoff; it does not duplicate Fe(110) scientific settings.
- The installed `fe-vasp-incar-custodian` skill owns commands, tuning logic, validation, and output formats.
- The CLI is read-only by default. `--read-only` and legacy `--dry-run` write
  nothing; only explicit `--write-artifacts` may persist an INCAR candidate or
  review files.

Algorithm-specific DIMER settings, oxide MAGMOM, and DFT+U remain **Needs confirmation** unless their owning module approves them.

## Done Criteria

The skill and project profiles are validated, blockers prevent inappropriate tuning, recommendations are reviewed and traceable, and no job is submitted automatically. This module remains active while calculations continue.
