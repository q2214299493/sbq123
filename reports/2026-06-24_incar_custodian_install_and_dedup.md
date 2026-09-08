# INCAR Custodian Installation and Repository Deduplication

## Source Audit

- Source: `D:/fe_vasp_incar_custodian_skill.zip`
- SHA256: `E2CB5442D50C0419430BA1AC5C138CDA00E26538852873C119BFDB5139CD71BB`
- Archive paths: no absolute paths or parent traversal found.
- Initial strict scan: low risk; invalid underscore name, missing frontmatter, and missing license metadata.
- Manual review: no credential access, upload, persistence, hidden binary, destructive command, or automatic VASP submission.
- Source quality: 1331-line specification plus nine identical non-functional skeleton CLIs.

## Normalized Skill

- Name: `fe-vasp-incar-custodian`
- Repository source: `skills/fe-vasp-incar-custodian/`
- Installed path: `C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/`
- Dependencies: `pymatgen 2026.5.4`, `custodian 2025.12.14`.
- Structure: 60-line `SKILL.md`, one functional CLI, two rule/profile resources, and Chinese report resources.
- Final strict scan: safe, maximum severity `INFO`; only the absent upstream license declaration remains. No license was invented.
- Skill-creator validation: passed.

## Project Integration

- Added `modules/incar_custodian/README.md` and registered the module as `Active`.
- Centralized Fe surface-family and Fe110 stage overrides in `configs/incar_custodian/project_profiles.yaml`.
- NEB now hands a reviewed path to INCAR custodian instead of generating its own generic INCAR candidate.
- DIMER algorithm settings and VFA/TS acceptance remain owned by their scientific modules.
- Species groups are preserved in MAGMOM: Fe C O `45 1 1` writes `45*2.2 1*0.0 1*0.0`, not `45*2.2 2*0.0`.

## Deduplication

Removed or consolidated:

- three generic NEB INCAR templates and the old NEB INCAR renderer
- duplicate NEB material/project profile files
- duplicate Fe convergence-baseline sentence in `modules/README.md`
- stale current-route duplication in `docs/12_WORKFLOW_ARCHITECTURE.md`
- historical/convergence detail duplicated in live `docs/02_CURRENT_STATE.md` (88 to 45 physical lines)

Preserved intentionally:

- repeated endpoint POSCARs and input snapshots inside calculation directories
- copied scripts/LSF files inside historical run folders
- memory-migration evidence copies and curated baseline evidence
- archived user packages and historical reports

These retained copies carry calculation or migration provenance and were not treated as disposable duplicates. No scientific calculation file was changed or deleted.

## Verification

- `--help` and Python compilation: passed.
- Fe110 SCF tuning dry-run: changed only `NELM 250 -> 300`; retained project `ALGO=All`.
- Fe110 generation dry-run: produced eight-image pre-NEB settings and species-separated MAGMOM.
- Upstream bad-path test: returned `STOP_INCAR_TUNING_AND_REBUILD_PATH` and wrote no continuation INCAR.
- VASP execution/submission: not performed.
- Exact-hash audit: no duplicate files remain in active core directories after excluding intentional migration/baseline evidence copies.
- Installed skill hashes match the repository skill source.
