# Historical Results

This document stores durable historical results, diagnostic lessons, and downstream modeling plans. It is not a live job-status file.

## Source Register

- `H1`: `vasp-catalysis-workflow` adsorption/NEB/DIMER references.
- `H2`: read-only remote OUTCAR, CONTCAR, and directory checks on `sunboquan-codex`, 2026-06-23.
- `H3`: convergence CSV/README evidence under `modules/memory_migration/inputs/MM-002_evidence/`.
- `H4`: legacy active-session and project-context memory files.
- `H5`: local postmortem and structure-review folders under `C:\Users\86177\Desktop\结构`.
- `H6`: current endpoint-derived NEB precheck and endpoint match report.
- `H7`: installed DFT-to-kinetics workflow skills.
- `H8`: alpha-Fe bulk smearing OUTCAR/OSZICAR results from jobs `9542651-9542658` and the curated CSV under `reports/`.
- `H9`: primary Fe(110) literature linked in `reports/2026-06-23_alpha_fe_smearing_and_fe110_thickness_literature.md`.

## Fe Convergence Baselines

Criterion: two-stage static convergence against the highest ENCUT or densest k mesh, target `<=1 meV/atom`.

| ID | System | Recommended Baseline | Evidence | Status |
|---|---|---|---|---|
| `HR-009` | alpha-Fe conventional bcc, 2 Fe, `a=2.8665 A` | `ENCUT=400 eV`, Gamma `15 15 15`, `MAGMOM=2*2.2`; relax with `ISMEAR=1`, `SIGMA=0.10 eV`; static with `ISMEAR=-5` | `400 eV`: `0.322 meV/atom` from 600 eV; `15^3`: `0.754 meV/atom` from `23^3`; selected smearing: `0.490 meV/atom` from tetrahedron and entropy `0.239 meV/atom` | Verified from `H3,H8` |

Representative literature checked on 2026-06-23 (`H9`) places routine Fe(110) adsorption models mainly at four or five layers (six of eight selected primary studies). More conservative C-insertion and CO-dissociation studies use seven or eight layers. This supports five layers for workflow development but not a publication-level thickness-convergence claim for the final CO-dissociation barrier.

## Corrected True Fe(110) Thickness Result

Jobs `9554557-9554562` completed on the corrected bcc Fe(110) model. The 4-8-layer slabs remained flat and structurally valid. Surface excess values were `2.3977, 2.4049, 2.3894, 2.3837, 2.3731 J/m2`; the seven-to-eight-layer difference was `0.0106 J/m2`. The top interlayer spacing differed by only `0.0008 A` between seven and eight layers. Seven layers is the routine adsorbate-development choice, while eight layers is the high-accuracy clean-surface reference pending adsorbate/barrier-specific validation.

## Decisive DIMER History

| ID | Jobs / Archive | Durable Finding | Consequence |
|---|---|---|---|
| `HR-012` | `9429911`, `9430275`, `9430611`, `9430627`, `9430644`; matching remote `failed_attempt_*` directories | Fast/RMM instability, no effective DIMCAR step, unstable late TS-like start, dipole-field instability, and prescf stall are distinct failure modes. | Diagnose SCF, dipole, initial geometry, and mode separately; do not treat them as one generic convergence problem. |
| `HR-013` | `9433590`; `failed_attempt_9433590_dimer_mode_oscillation_20260614` | DIMER entered iterations but force oscillated around `2-4 eV/A` without a downward trend. | Rebuild the starting structure/mode instead of tuning only INCAR. |
| `HR-014` | `9434125`; `failed_attempt_9434125_COmode_damped_force_blowup_20260614` | C/O-only opposite stretch MODECAR drove force to about `691 eV/A`. | Never reuse that manual mode; inspect modes with `dimmode.pl`. |
| `HR-015` | Consolidated DIMER lesson | A chemically plausible, smooth NEB high-energy image is the preferred start; use literature/manual geometry only when tied to validated local states. | DIMER remains blocked until a credible saddle-like NEB image exists. |

## Decisive NEB History

| ID | Jobs / Archive | Durable Finding | Consequence |
|---|---|---|---|
| `HR-016` | `9430977`; `failed_attempt_9430977_D1_refined_3img_parallel_mdivide_20260611` | Three images could not divide 32 MPI ranks. | Choose image count/core allocation with exact divisibility. |
| `HR-017` | `9433782`, `9434479`; remote failure directories verified | Early elongated images recollapsed while another image overshot, showing a discontinuous reaction coordinate. | Do not force a molecular minimum to behave as a TS; rebuild the segment. |
| `HR-018` | `9434583`; `failed_attempt_9434583_endpoint_was_TS_not_D_20260614` | A C-O near `2.12 A` was incorrectly used as the endpoint. | The final D state must be separated C* + O*, never a TS-like stretched CO. |
| `HR-019` | `9435171`, `9435904`, `9436878`, `9438732` | Repeated B-like ordinary relaxations encountered ZBRENT/interruption or drifted toward weak adsorption/desorption. | Do not keep restarting from a detached CONTCAR; use a stable molecular endpoint suitable for the full NEB. |
| `HR-020` | `9441773` | A long path concentrated the transition around a small image interval and retained high force. | More images alone do not fix a wrong coordinate; refine the chemically active segment. |
| `HR-021` | `9452322`, `9454833` | Stable Fe electronic settings fixed startup SCF behavior, but images still concentrated into molecular and dissociated basins. | Separate electronic convergence from path validity. |
| `HR-022` | `9455800`; local `neb_9455800_stopped_58steps_postmortem` | After 58 steps, images 01-03 were molecular, image 04 only weakly activated, and image 04->05 C-O gap was about `1.701 A`. | Do not use this path for CI-NEB or barrier extraction. |
| `HR-023` | `9506942` | Fixed-C/O Fe pre-relaxation preserved geometry, but Fe forces plateaued; full Fe displacement transfer created an O-Fe coordination jump. | If conditioning is reused, blend Fe displacement conservatively and re-audit every image. |
| `HR-024` | `9532195`; local `neb_9532195_stopped_step9_postmortem` | Images 01-06 reformed molecular CO and image 06->07 C-O gap reached about `0.964 A`; SCF remained stable. | The failure was structural/path-related, not electronic. |
| `HR-025` | Endpoint-derived correction | Previous paths routed O through the wrong periodic image. Correct minimum displacements are C left/down and O right/down; pure interpolation still compresses early C-O. | Build nonlinear early rotation from exact endpoint branches and audit per-atom displacement, not only C-O. |

## DFT-to-Kinetics Roadmap

This is a plan, not completed modeling.

1. Validate adsorption states, transition states, and frequencies.
2. Apply thermal corrections and compute reaction/activation free energies.
3. Build machine-readable species, energy, reaction, barrier, and rate tables with units and provenance.
4. Assemble a balanced reaction network.
5. Solve baseline mean-field MKM for coverage, TOF, selectivity, and DRC.
6. Add coverage-dependent energetics only when supported by data.
7. Use surface-reaction KMC when heterogeneity, diffusion, lateral interactions, or spatial correlations matter.
8. Connect validated intrinsic rates to a specified reactor model.
9. Propagate sensitivity and uncertainty to choose the next DFT/NEB/frequency refinements.

GCMC and adsorption isotherms may provide equilibrium loading or initial coverage; they do not replace reaction KMC.

## Migration Status

All supported historical categories were reviewed in `MM-002` through `MM-004`. Items lacking raw evidence remain explicitly marked `Needs confirmation`; no transient job status was promoted into this document.

<!-- state-handoff:start task_history_events -->
## Managed Task History

<!-- state-handoff:item history:task-completed-7f21fefbbda64053a163a326 -->
### 2026-08-07 — Fe(110) CO dissociation electronic barrier completed

- Task: `fe110-co-dissociation`
- Outcome: The forward electronic barrier is 1.350209 eV; the result, Topic-1 workbook row, reusable strategy, and completion handoff are preserved without submitting another VASP job.
- Summary: Accepted Dimer job 9656664 and local-frequency job 9694935 were registered with the compatible SIGMA=0.20 IS/TS/FS energy chain.
- Acceptance event: `task-acceptance-fe110-co-electronic-barrier-local-frequency-20260807`
- Evidence SHA-256: `8eda76a85a1acddd464d1dab5c88f69437e23f84a6b89dd5c456db31533fd0f2`, `42ada3bd74bff75e9b98934f7ee30303a854ea2bad4992dbc4db5ad15ecdfec9`

<!-- state-handoff:item history:task-completed-966f70761e2de2c804e6dced -->
### 2026-08-29 — Failure-boundary dual-model VASP screening completed

- Task: `task-current`
- Outcome: Both models passed the current screening ceilings. Retain the MatRIS checkpoint; the next distinct scientific step is disjoint held-out TS validation, not automatic fine-tuning.
- Summary: Eight seed/fail structures were validated as exact SIGMA=0.20 VASP force labels and compared with frozen MatRIS and AQCat25 predictions.
- Acceptance event: `task-acceptance-fe110-c2ho-h-to-c2h2o-job1344-dual-model-error-20260829`
- Evidence SHA-256: `4d023b6f83abe254ab034e2049dc053cf5bf2a101ef730d0c9a7c2f530b63e9b`, `63cb30b9ef9f3a986c25b9b57df4c9edeb216668ec2c83c4551a81d8e729ff2a`

<!-- state-handoff:end task_history_events -->
