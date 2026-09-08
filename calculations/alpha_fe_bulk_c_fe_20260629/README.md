# Alpha-Fe Bulk `c_fe` Pre-Submission Snapshot

Status: `SUBMITTED_PEND`

## Remote Location

- Host: `sunboquan-codex`
- Directory: `~/sbq/c_fe`
- Prepared: `2026-06-29 00:36 CST`
- Submission: `bsub vasp541std.lsf`
- Job ID: `9556519`
- Submission checkpoint: `2026-06-29 01:00 CST`
- Scheduler at checkpoint: `PEND` in `Gkn_normal`

## Structure Selection

- Whitelist evidence: NOMAD record `nomad--EIm3uUgIh58NK0wL_rIwQBfFvSc`, pure Fe2, bcc alpha-Fe, space group `Im-3m`, VASP/PBE.
- Reviewed retrieval: `modules/catalysis_data_retrieval/outputs/20260628_alpha_fe_bulk_kmesh/`.
- Accepted local structure: `modules/fe_convergence_baseline/systems/alpha_fe_bulk/POSCAR`.
- Model: conventional bcc Fe2, `a=2.8665 A`, fractional sites `(0,0,0)` and `(0.5,0.5,0.5)`.
- POSCAR SHA-256: `b22ff5ab2432b583d9197ce776b4264a20b96a2e8e29713fa3eb93f507fbff7d`.

The whitelist record establishes the transferable structure family. The local convergence package, not the database single-point settings, owns the starting lattice and VASP parameters.

## Remote Input Inventory

| File | SHA-256 / identity |
|---|---|
| `POSCAR` | `b22ff5ab2432b583d9197ce776b4264a20b96a2e8e29713fa3eb93f507fbff7d` |
| `INCAR` | `6b92c354a90a454e9d7b865fcb1f3e1ea49469829c3156531f36b09265809bc2` |
| `KPOINTS` | `49e2a5d2a16569aa5cb392d2a81366e0cb263ae47bd04542481ff96816dbf4ff` |
| `POTCAR` | `PAW_PBE Fe 06Sep2000`; `cd5a22d9368cc8b5cc476bea79732366149640da08ac9009b0e1b7fc627eea28` |
| `vasp541std.lsf` | `fda95a98e789c299aab53a1ddd77cdf77c2c0a94f58a77a3b7868fa287d3daf6`; 32 cores |

Licensed `POTCAR` content remains remote and is not stored in Git.

## Review Notes

- The input matches the validated alpha-Fe relaxation branch: `GGA=PE`, `ENCUT=400 eV`, Gamma `15x15x15`, `ISPIN=2`, `MAGMOM=2*2.2`, `ISMEAR=1`, `SIGMA=0.10 eV`, `EDIFF=1E-5`, `EDIFFG=-0.02 eV/A`, `IBRION=2`, and `ISIF=3`.
- No VASP output files existed at the final pre-submission check.
- The user approved the inputs before submission.
- For high-symmetry bcc Fe, validate the final lattice with residual pressure/stress and preferably a volume/EOS check; force convergence alone is insufficient.
