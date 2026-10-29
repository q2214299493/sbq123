---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Decisions Log

## 2026-09-05 - Add Sella to the current MatRIS candidate loop

- User requested Sella integration and comparison with the current workflow.
  Keep complete-path MatRIS NEB as the default and add optional standard Sella
  refinement of a converged, geometry-valid single peak with the same checkpoint.
- Preserve AQCat25 BA-Sella as its existing separate model/optimizer route.
  Do not treat standard Sella as the bond-aware implementation or infer a
  best-performing method without a matched local benchmark.
- Reuse VASP label selection/error assessment and MatRIS training gates.
  Require an exact label for the Sella candidate and a reviewed new-checkpoint
  full-path rerun that retains Sella settings. Geometry failures alone do not
  trigger training. Preserve all final TS/execution gates.
- Scope is local code and tests; no remote deployment, job action or checkpoint
  promotion was performed. Implementation and limitations are in
  `modules/transition_state_search/SELLA_BRANCH.md`.

## 2026-09-05 - Improve the Existing TS Strategy Without Resetting Calculations

- User authority: add Sella as a reference option and implement/test bounded
  strategy improvement on the current architecture; no scientific job is authorized.
- Reuse the existing AQCat25/BA-Sella candidate branch, registry and execution
  gate. Its historical job-737 candidate is not a validated TS or proof of
  transferability to the current O-H reaction.
- Capture current inputs, workflow files and explicit checkpoint references;
  preserve baseline/parent/attempt identities. Restrict candidate changes to
  declared strategy fields, with one changed field and two candidates per parent.
- Record reviewed outcomes separately from successful TS templates. Confirmed
  deterministic failures block the identical execution inputs; uncertain or
  stale observations require review. Runtime/path failure does not imply model
  error or authorize fine-tuning.
- Add registry schema 8 through an additive migration after a local SQLite
  backup at `archive/strategy_learning_20260905/registry_before_v8.sqlite3`.
  Existing table counts, integrity and foreign keys were verified after migration.
- Keep scientific thresholds, model-training gates, submission authorization
  and final TS/barrier acceptance outside the learning optimizer. See
  `modules/transition_state_search/LEARNING.md` for the implementation and limits.

## 2026-06-23 - Use Endpoint-Derived Periodic Branches

- Decision: move C toward its final site along the short leftward branch and O along the short rightward branch.
- Reason: endpoint analysis showed the prior left-moving O branch used the wrong periodic image.
- Consequence: the active path follows the actual endpoint sites and avoids unnecessary O migration.

## 2026-06-23 - Use Nonlinear Early C/O Waypoints

- Decision: manually control images 01-04 instead of pure endpoint interpolation.
- Reason: direct interpolation compresses C-O early in the path.
- Consequence: C-O progresses through `1.20`, `1.35`, `1.65`, and `2.05 A` before dissociation.

## 2026-06-23 - Start with Damped Ordinary NEB

- Decision: use eight images, non-climbing NEB, `IOPT=3`, `TIMESTEP=0.05`, and `MAXMOVE=0.10`.
- Reason: establish a continuous path before climbing-image refinement and reduce aggressive early motion.
- Consequence: CI-NEB is deferred until the ordinary path is acceptable.

## 2026-06-23 - Project Files Become the Handoff Source

- Decision: future threads must resume from this state system and verified outputs rather than chat history.
- Consequence: every completed task must update the state, logs, file index, and task files.

## 2026-06-23 - Automatically Route New Module Requests

- Decision: Codex will identify requests for new methods, models, integrations, or major workflows as possible project modules.
- Reason: module registration and dependency tracking must happen before implementation begins.
- Consequence: a new module is added to `docs/06_MODULE_MAP.md`, prerequisites go to the backlog, and the first executable step becomes `tasks/current_task.md` when immediate implementation is requested.

## 2026-06-23 - Migrate Historical Memory in Controlled Batches

- Decision: migrate one durable category at a time with provenance instead of copying complete memory or chat history.
- Reason: the active state must stay concise, current, and evidence-based.
- Consequence: historical results go to `docs/08_HISTORICAL_RESULTS.md`, durable preferences go to `docs/09_USER_PREFERENCES.md`, and progress is tracked in `docs/07_MEMORY_INDEX.md`.

## 2026-06-23 - Current Project State Supersedes Stale Memory Paths

- Decision: use `~/sbq/agent/jobs` for this project and treat `~/sbq/Fe_agent_demo` references as superseded.
- Reason: a read-only server check confirmed the current root exists and the legacy root does not.
- Consequence: legacy summaries and the VASP skill must not override the project state when constructing remote paths.

## 2026-06-23 - Preserve Fe Production Convergence Baselines

- Decision: retain `ENCUT=400 eV`; use Gamma `15 15 15` for alpha-Fe bulk and Gamma `5 3 1` for routine 3x3 Fe(110) slab/NEB work.
- Reason: copied convergence summaries meet the recorded `<=1 meV/atom` target.
- Consequence: use Gamma `7 5 1` for key final clean-slab single points when affordable; extra smearing/thickness decisions remain unresolved.

## 2026-06-23 - Unify Alpha-Fe and Fe(110) Production Parameters

- Decision: keep `ENCUT=400 eV`; use Gamma `15 15 15` for alpha-Fe bulk. For the existing 3x3 Fe(110) family, use Gamma `5 3 1`, `ISMEAR=1`, `SIGMA=0.20 eV`, `15 A` vacuum, five layers, and two fixed bottom layers for routine relaxation and NEB.
- Reason: the routine Fe(110) mesh differs by `0.300 meV/atom` from the densest reference; `ISMEAR=1`, `SIGMA=0.20 eV` differs by `0.282 meV/atom` in extrapolated zero-smearing energy; and the 15 A vacuum differs by `0.019 meV/atom` from 22 A.
- High-accuracy branch: recompute all compared Fe(110) states with Gamma `7 5 1`, `ISMEAR=1`, and `SIGMA=0.10 eV`; do not mix energies across branches.
- Limitation: five layers is retained for compatibility with existing endpoints and NEB data. The static thickness series did not show strict surface-energy convergence through seven layers.
- Scope: do not transfer this protocol to chi-Fe5C2 or Fe3O4 without system-specific convergence, magnetism, and DFT+U decisions.

## 2026-06-23 - Stage DFT-to-Kinetics Modules by Dependency

- Decision: define the kinetic data schema first, then thermochemistry/reaction network, baseline MKM, coverage MKM or KMC, reactor simulation, and uncertainty analysis.
- Reason: downstream models cannot be valid without balanced reactions, consistent units, free-energy barriers, and provenance.
- Consequence: downstream modules are registered as `Blocked` until their specific inputs exist.

## 2026-06-23 - Use Guarded Git Snapshots

- Decision: version project state, scripts, curated inputs, structures, and concise reports while excluding licensed `POTCAR`, credentials, large VASP runtime output, and temporary diagnostics.
- Reason: the repository should preserve reproducibility and handoff history without becoming a calculation-output archive or exposing restricted files.
- Consequence: task-close commits use `scripts/git_snapshot.ps1`; off-machine backup remains blocked until a private remote is approved.

## 2026-06-23 - Grade TS Candidates Before Kinetic Use

- Decision: classify every NEB/CI-NEB/DIMER TS candidate as A, B, or C using frequency count, mode assignment, geometry sanity, and bidirectional IS/FS connectivity.
- Reason: saddle-search convergence alone does not prove a first-order saddle on the intended reaction coordinate.
- Consequence: only Grade A may enter the validated kinetic database or feed MKM/KMC; Grade B requires manual review and Grade C is excluded while its failure evidence is retained.
- Unresolved parameters: numerical thresholds for a clear imaginary frequency and a small soft mode are **Needs confirmation**.

## 2026-06-23 - Select Alpha-Fe Bulk Smearing

- Decision: use `ISMEAR=1`, `SIGMA=0.10 eV` for alpha-Fe bulk relaxation and `ISMEAR=-5` for final static bulk energies at Gamma `15 15 15`.
- Reason: all eight tested schemes are within `0.6 meV/atom` of the tetrahedron reference in zero-smearing energy, while `ISMEAR=1`, `SIGMA=0.10 eV` keeps the absolute entropy term to `0.239 meV/atom`; `SIGMA=0.20 eV` gives `1.323 meV/atom`.
- Magnetic check: the two-Fe-cell moments span `4.4712-4.4884 mu_B`, so no smearing case changed the ferromagnetic state materially.
- Consequence: bulk and slab use separate validated smearing choices; consistency means using one protocol within each energy comparison, not forcing dissimilar Brillouin zones to share one SIGMA.

## 2026-06-23 - Interpret Fe(110) Literature Thickness

- Decision: treat four to five layers as the common literature range for routine Fe(110) adsorption models and seven to eight layers as the conservative range for C insertion or CO dissociation finite-size validation.
- Evidence: six of eight representative primary studies checked used four or five layers; Jiang and Carter used seven layers for C adsorption/diffusion, and Chakrabarty et al. used eight layers for Fe(110) CO adsorption/dissociation calculations.
- Consequence: keep the current five-layer NEB for path development and dataset continuity. Validate publication-level IS/TS/FS energy differences with a seven- or eight-layer model before accepting the final barrier.

## 2026-06-23 - Require Complete Data Provenance

- Decision: never invent database values; register every job status and every calculation input/output; trace every result to its evidence; keep automated checks separate from scientific judgment.
- Reason: long-term catalyst-agent workflows must remain auditable across VASP, TS validation, thermochemistry, MKM, KMC, and reactor stages.
- Consequence: the `calculation-registry` module is required upstream of the kinetic schema. Large or licensed files receive metadata/checksum/path records and are not forced into Git.
- Unresolved implementation: database backend, storage location, raw-file/object-store policy, and historical backfill scope are **Needs confirmation**.

## 2026-06-23 - Separate Every Scientific Stage into a Repository Module

- Decision: maintain independent repository modules for convergence, adsorption/endpoints, NEB, DIMER, TS vibration, thermochemistry, reaction network, MKM, coverage MKM, KMC, reactor simulation, and uncertainty analysis.
- Reason: historical evidence, execution rules, validation gates, and downstream eligibility must not be mixed across scientific stages.
- Consequence: each module owns a README with inputs, gates, outputs, database handoff, and boundaries; `docs/06_MODULE_MAP.md` owns status/dependencies only.

## 2026-06-23 - Start the Registry with a Provisional Local SQLite Schema

- Decision: use a versioned SQLite schema and standard-library initializer as the first local registry implementation.
- Reason: it is self-contained, inspectable, requires no external service, and can represent unknown values without inventing data.
- Consequence: `calculation-registry` moves from `Blocked` to `Active`; scientific data insertion and historical backfill remain separate reviewed tasks.
- Limitation: raw-file/object-storage and remote backup policy remain **Needs confirmation**.

## 2026-06-23 - Preserve a Concrete Fe Convergence Reference Package

- Decision: keep the validated alpha-Fe and five-layer Fe(110) structures, production inputs, convergence evidence, provenance, and checksums in `modules/fe_convergence_baseline/`.
- Reason: future adsorption and pathway tasks need a reproducible system baseline, not only prose parameter summaries.
- Consequence: the concrete package is `Completed` after its validator passed; the broader convergence workflow remains `Active` because strict Fe(110) thickness convergence and new material families remain unresolved.
- Exclusion: licensed POTCAR content and large VASP runtime files remain outside Git, with metadata retained.

## 2026-06-23 - Establish GitHub Remote Backup

- Decision: configure `https://github.com/q2214299493/sbq.git` as `origin` and push local `main`.
- Verification: local and remote `main` matched commit `43d25d52a427bae05931d4aafdc36251b7300024` after the initial push.
- Safety: POTCAR, large runtime outputs, credentials, temporary diagnostics, and the generated SQLite database remain excluded.
- Limitation: GitHub reports the repository as `public`; automatic future pushes are paused pending private visibility or explicit public approval.

## 2026-06-24 - Make the NEB Module Literature-Informed and Closed-Loop

- Decision: replace the former short NEB procedure with one canonical module workflow that adapts existing literature-search output, generates IDPP-based candidates, diagnoses geometry, parses outputs, and issues review-only replanning decisions.
- Reason: path generation and failure diagnosis need structured evidence without duplicating literature search or blindly submitting expensive calculations.
- Boundary: DIMER and vibrational validation own their settings and execution; the NEB module only hands off reviewed candidates.
- Consequence: pure reactive-atom endpoint interpolation, automatic submission, automatic TS acceptance, and silent file overwrite are prohibited. Active Fe(110) endpoint settings override generic templates.

## 2026-06-24 - Centralize INCAR Tuning in One Custodian Layer

- Decision: normalize the supplied `fe_vasp_incar_tuning` ZIP into the valid skill `fe-vasp-incar-custodian` and make `modules/incar_custodian/` the sole cross-cutting INCAR recommendation layer.
- Reason: the source contained a 1331-line repeated specification and nine non-functional skeleton scripts that duplicated NEB, DIMER, VFA, and material rules.
- Boundary: scientific modules own structure/path/mode validity; the custodian layer owns structured INCAR read/write, minimal diagnosed changes, validation, and reports.
- Consequence: the prior NEB INCAR renderer and generic NEB templates were retired. Fe110 project overrides and surface-family magnetic defaults now live in `configs/incar_custodian/project_profiles.yaml`.
- Safety: strict scan of the normalized skill passed with INFO-only license metadata; upstream license is unknown and was not invented.

## 2026-06-24 - Assign One Authority per Workflow Rule and Command

- Decision: each executable behavior has one canonical owner: `AGENTS.md` for startup/closeout, `docs/01_METHOD_PROTOCOL.md` for submission, `docs/12_WORKFLOW_ARCHITECTURE.md` for stage order, the NEB module for path commands, `docs/10_TS_VALIDATION_PROTOCOL.md` for TS grades, `docs/11_DATA_PROVENANCE_PROTOCOL.md` for registry rules, and the INCAR skill for tuning commands/outputs.
- Reason: duplicate instructions caused longer context and allowed stale calculation-package commands to look current.
- Consequence: job-specific monitor/precheck scripts were replaced by two parameterized utilities; obsolete submission entry points were removed; superseded unique NEB scripts were moved to `archive/legacy_neb_scripts/`.
- Preservation rule: calculation directories, imported packages, migrated evidence, and reports remain immutable provenance and are not current command sources unless explicitly promoted by `tasks/current_task.md`.

## 2026-06-24 - Use One Whitelist Retrieval Gate Before New Calculations

- Decision: replace automatic general-literature lookup with `catalysis-data-retrieval` before any new calculation or externally seeded structure/path choice.
- Allowed sources: Catalysis-Hub/CatApp, OCP OC20/OC22, OC20NEB/CatTSunami, Materials Project Catalysis Explorer, Materials Cloud Archive, ioChem-BD, and NOMAD Catalysis, limited to the exact URL scopes in the skill manifest.
- Ranking: combine BM25 keyword matching with a real sentence-embedding cosine rank and return at most five provenance-complete results. Lexical-only output is diagnostic and cannot pass the production gate.
- Image rule: convert images into reviewable visible features plus confidence-qualified interpretations before retrieval; image appearance alone does not establish elements, sites, or scientific validity.
- Boundary: official VASP/VTST documentation remains allowed for software syntax/method behavior, and verified local project files remain valid. Global academic-search skills are excluded from this project's automatic calculation flow but are not uninstalled from other projects.
- Integration: delete the NEB-specific literature adapter/rules and make scientific modules consume the shared retrieval output.
- MCP decision: no MCP is currently required; direct official APIs/downloads are simpler. A custom MCP may be considered only if unified credential/tool management becomes necessary.

## 2026-06-24 - Make Repository State Primary and Separate Current Code from Provenance

- Decision: ordinary continuation starts only from `AGENTS.md`, current project/state/task files, relevant module README, calculation output, and live scheduler evidence. Chat history and `.codex` session/memory files are not ordinary state sources.
- Code layout: reusable tools live under `scripts/` or repository-backed skills; one-off generators, downloaded pages, and historical review artifacts live under `archive/`; calculation directories remain immutable provenance snapshots.
- Quality gate: `pyproject.toml` owns Python dependencies, Ruff, formatting, complexity, and pytest. Root-layout and retired-interface tests prevent stale code from returning.
- Deduplication rule: remove duplicate current code and non-authoritative downloads, but retain byte-identical structures/settings/evidence when multiple source paths are required for scientific provenance.
- Consequence: future threads read less ambiguous context, current code has one dependency/configuration surface, and historical evidence remains traceable without acting as executable guidance.

## 2026-06-24 - Separate Calculation Retrieval from Scholarly Literature Work

- Decision: make `configs/skill_routing.yaml` the routing authority and keep `catalysis-data-retrieval` as the sole pre-calculation external-data owner.
- Reason: the legacy global VASP skill still invoked five overlapping general literature skills and old memory before calculations, contradicting the whitelist and repository-first rules.
- Consequence: VASP, adsorption-builder, and NEB-path-builder skills are now repository-backed consumers with no independent search. General academic-search, paper-reading, and literature-review skills remain available only for explicit scholarly requests and cannot seed calculations without whitelist admission.

## 2026-06-26 - Add CATKINAS and Zacros 4.0 to Post-Processing Flow

- Decision: use CATKINAS as the preferred local post-processing tool for baseline and coverage-dependent mean-field MKM, and use Zacros 4.0 as the preferred local engine for surface-reaction KMC.
- Evidence: local CATKINAS files were found under `C:/Users/86177/Desktop/app/CATKINAS`, including `CATKINAS.p`, `ReadMe.m`, quickstart files, and deployment notes. Zacros 4.0 files were found under `D:/Zacros4.0`, including `Zacros_Shell.cmd`, `bin/Zacros.exe`, `manual/ZacrosManual.pdf`, examples, and work folders.
- Follow-up evidence: CATKINAS quickstart `result_single/log1` ran under MATLAB `25.2.0.2998904 (R2025b)` and generated a single-case run log; Zacros 4.0 `example_100/general_output.txt` reached `Normal termination` at KMC time `25.0000381` after `185977` events.
- Boundary: both tools are downstream consumers of validated kinetic data. They must not receive unregistered DFT values, replace TS A/B/C validation, or bypass reaction-network and thermochemistry gates.
- Consequence: paths and expected inputs/outputs are recorded in `configs/postprocessing_software.yaml`; `baseline_mkm`, `coverage_mkm`, `surface_kmc`, `kinetic_data`, and workflow architecture documents now include the CATKINAS/Zacros handoff.
- Remaining confirmation: no project-specific CATKINAS MKM input package or Zacros Fe/CO KMC model has been generated from validated kinetic records.

## 2026-06-26 - Make Routine Progress Updates Chat-Only

- Decision: routine progress checks should be answered in chat only and should not create new checkpoint report/log documents unless the user explicitly asks for a saved report or document.
- Reason: automatic report generation consumed extra tokens and created unnecessary repository files for ordinary status requests.
- Consequence: future monitoring responses should include the requested per-image force status and classification directly in the conversation. Repository updates should be minimal, limited to state/decision/error/task files when continuity genuinely requires them.

## 2026-06-28 - Accept True Fe(110) Structures and Separate Routine/Reference Thickness

- Decision: accept all corrected 4-8-layer clean Fe(110) geometries; use seven layers for routine adsorbate development and eight layers as the high-accuracy clean-surface reference.
- Evidence: all relaxations converged below `0.016 eV/A` on free atoms, all static stages terminated normally, and no slab developed lateral slip, layer rumpling, or fixed-layer drift.
- Structural convergence: the top interlayer spacing changes from `1.9766 A` at seven layers to `1.9774 A` at eight layers.
- Energy limitation: surface excess changes by `0.0106 J/m2` from seven to eight layers, marginally above a strict `0.01 J/m2` threshold.
- Consequence: five layers is limited to low-cost clean-surface screening. Publication-level CO adsorption, reaction energy, and barrier claims require matched seven- and eight-layer IS/TS/FS comparisons before choosing whether a full eight-layer NEB is necessary.

## 2026-06-28 - Lock the Balanced True Fe(110) Production Protocol

- Decision: use a seven-layer 3x3 Fe(110) slab with Gamma `5x5x1` for routine relaxation and ordinary NEB; use Gamma `7x7x1` static recomputation for all compared seven-layer energies.
- Accuracy controls: `ENCUT=400 eV`, 15 A vacuum, two fixed bottom layers, `EDIFF=1E-5`, `EDIFFG=-0.02 eV/A`, `ISMEAR=1`, and `SIGMA=0.20 eV` for relaxation; `EDIFF=1E-6` and `SIGMA=0.10 eV` for final statics.
- NEB force staging: ordinary NEB uses `EDIFFG=-0.05 eV/A` for efficiency; accepted CI-NEB/TS refinement uses `-0.02 eV/A`.
- Validation branch: recompute matched clean/IS/TS/FS states with eight layers. Seven-layer production is accepted when adsorption/reaction changes are `<=0.03 eV` and the barrier change is `<=0.05 eV`.
- Reason: seven- and eight-layer surface geometry differs by only `0.0008 A`, while using seven layers avoids the cost of making every adsorption and NEB job eight layers.
- Authority: `configs/true_fe110_production.yaml`.

## 2026-06-28 - Add a Five-Layer Screening Branch Without Shrinking the Lateral Cell

- Database evidence: Catalysis-Hub Fe(110) system `62b69abc3d2db3f157d0547d4d64b41f` contains 28 Fe atoms as seven layers with four Fe per layer and three fixed layers. Its low atom count comes from a smaller lateral cell.
- Decision: retain the 3x3 lateral cell for CO-dissociation finite-size control, but use five layers (45 Fe) for adsorption-site screening, initial relaxation, and reaction-path exploration.
- Boundary: five-layer energies are not final results. Promote candidates to seven layers for production energies and barriers; use matched eight-layer states for publication validation.
- Reason: this reduces routine cost without adopting the database record's higher-coverage lateral cell.

## 2026-07-04 - Supersede the Seven-Layer/7x7x1 Fe(110) Production Branch

- User decision: the active Fe(110) production dataset uses the five-layer 3x3
  slab and Gamma `5x5x1` throughout.
- Scope: clean slab, adsorption relaxation, adsorption final static, endpoints,
  ordinary NEB, and later matched energy comparisons.
- Supersedes: the 2026-06-28 seven-layer routine-production and `7x7x1`
  final-static decision for the active dataset.
- Compatibility rule: do not mix historical `7x7x1` static energies or
  seven-layer energies into the active five-layer/`5x5x1` dataset.
- Static settings retained: `EDIFF=1E-6`, `ISMEAR=1`, and `SIGMA=0.10 eV`;
  only the k mesh is standardized to `5x5x1`.

## 2026-06-28 - Require One Slab Thickness for the Production Dataset

- User requirement: the bulk-to-slab-to-adsorption-to-NEB project is one internally consistent dataset, not separate routine and reporting datasets.
- Decision: five- and seven-layer calculations may coexist only as convergence evidence. After a matched observable test, select one layer count for every reportable clean slab, adsorption state, endpoint, reaction, and NEB result.
- Selection gate: compare matched five- and seven-layer CO initial and C+O final states. Select five layers if adsorption/reaction differences are `<=0.03 eV`; otherwise select seven layers.
- Clarification: method consistency does not require identical numeric k meshes for bulk and slab. It requires the same functional, POTCAR family, ENCUT, spin treatment, and comparable reciprocal-space density, followed by the same final-energy protocol for every compared state.

## 2026-06-27 - Make Monitoring and Startup Token-Efficient

- Decision: use minimal repository startup reads and compact parsed monitoring output by default.
- Reason: repeated full state/protocol reads and raw eight-image SCF/force tails consumed context without improving routine decisions.
- Implementation: `AGENTS.md` now routes routine continuation through the current task, relevant current-state section, and owning module. `check_neb_job.sh` emits one line per image and requires explicit `--detail` for raw histories.
- Consequence: detailed logs remain available on request, while routine checks avoid duplicate commands, documents, and unchanged state commits.

## 2026-06-29 - Lock Cross-Project Adsorption-Energy Compatibility

- User requirement: future bulk, Fe(110), and adsorption calculations must form internally comparable parameter branches.
- Global locks: use `GGA=PE` (PBE), one approved PAW-PBE POTCAR family, and `ENCUT=400 eV` for every energy component.
- Spin correction: use `ISPIN=2` for Fe-containing magnetic systems. Gas-phase closed-shell CO uses `ISPIN=1` with no `MAGMOM`; it is not forced into the magnetic Fe spin branch.
- Stage consistency: keep `EDIFF`/`EDIFFG` and `ISMEAR`/`SIGMA` identical within a compatible system group and workflow stage. Final reported energies require matched static recomputation; exploratory `EDIFFG=-0.05 eV/A` results are not final adsorption energies.
- Bulk-reference boundary: the accepted alpha-Fe `ISMEAR=-5` static remains a convergence benchmark. If bulk total energy is used in a slab/adsorption thermodynamic cycle, recompute it with that dataset's matched Fe-metal final-static branch.
- Group exception: metals and oxides may use separately converged smearing, magnetic, and DFT+U branches. No adsorption, reaction, or barrier energy may mix branches.
- Slab consistency: within one surface family and coverage branch, keep the lateral cell, selected layer count, vacuum, fixed-layer rule, dipole policy, and slab k-mesh identical.
- Supersession: the historical `ISMEAR=0`, `SIGMA=0.5` generic relaxation template is no longer a production default. Convergence-backed system-group protocols take precedence.

## 2026-06-29 - Prepare Whitelist-Grounded Alpha-Fe Bulk for Surface Construction

- Structure decision: use conventional bcc alpha-Fe Fe2, space group `Im-3m`, with sites `(0,0,0)` and `(0.5,0.5,0.5)`.
- External gate: reviewed NOMAD whitelist records support the pure-Fe2 bcc/VASP/PBE structure family. Database single-point parameters are not transferred.
- Local authority: use the validated alpha-Fe baseline start `a=2.8665 A`, `ENCUT=400 eV`, Gamma `15x15x15`, and its accepted magnetic/smearing relaxation branch.
- Remote preparation: inputs were placed in `sunboquan-codex:~/sbq/c_fe` and verified by hashes. Status remains `PREPARED_NOT_SUBMITTED` pending user inspection.
- Scientific gate: because high-symmetry bcc ionic forces may vanish independently of cell stress, final slab construction requires residual-pressure/stress review and preferably a bounded EOS/volume confirmation.

## 2026-06-29 - Establish the Fe(110) Remote Project Root and Clean-Slab Reference

- Bulk basis: job `9556519` completed normally with cubic `a=2.8269483674 A` and residual external pressure `1.50 kB`.
- Directory policy: all new true Fe(110) work will be organized under `sunboquan-codex:~/sbq/Fe110`; the current clean slab is under `~/sbq/Fe110/fe110`.
- Prepared model: true bcc Fe(110), primitive-surface `3x3`, five layers, 45 Fe, `15 A` vacuum, and bottom two layers fixed, following the user's correction.
- Numerical branch: Gamma `5x5x1`, `GGA=PE`, `ENCUT=400 eV`, `ISPIN=2`, `ISMEAR=1`, `SIGMA=0.20 eV`, `EDIFF=1E-5`, and `EDIFFG=-0.02 eV/A`.
- Boundary: five layers is the user-selected model for this input. Seven layers remains a convergence reference, and this correction is not proof that the five-versus-seven-layer observable gate is complete.
- Submission: after explicit user approval, the five-layer clean-slab relaxation was submitted as job `9557161`.

## 2026-06-29 - Make Fe(110) Adsorption Sites Species-Independent

- Decision: generate adsorption sites only from the clean relaxed slab's highest-z Fe layer; adsorbates enter only through anchor and internal-geometry metadata.
- Site definitions: top is a top-layer Fe projection; short and long bridge use the first two distinct top-layer Fe-Fe distance classes; true hollow is the centroid of an adjacent three-Fe triangle and must not coincide with any Fe-Fe midpoint.
- Implementation: `scripts/adsorption/build_fe110_adsorption.py` owns site generation and placement; `configs/fe110_adsorbates_step12a.yaml` owns species metadata.
- Validation: the current slab gives nine top-layer Fe atoms, short/long classes `2.448316/2.826934 A`, and four distinct projections. The rebuilt Step 12A set contains six correctly classified structures for each site type.
- Consequence: adding an adsorbate must not modify site-generation logic. Add only atom order, anchor, relative geometry, orientation, and Fe-anchor-distance metadata.

## 2026-06-30 - Add AdsMind Lite as a Rule-Based CARE-to-VASP Gate

- Decision: add `adsmind_lite` as a compact engineering module between CARE-generated species and VASP adsorption calculations; do not build a multi-agent planner/validator/analyzer system.
- Implementation: configuration under `configs/adsmind_lite/`, CLIs under `scripts/adsmind_lite/`, and module/data/memory boundaries under `modules/adsmind_lite/`.
- Validated scope: metallic Fe, with robust Fe(110) top, distinct short/long bridge, and true hollow detection plus capped anchor-based candidates.
- Staged scope: iron carbide and iron oxide classes are represented from the beginning, but lattice C/O identity, vacancies, hydroxylation, Fe oct/tet labels, and C2+ multidentate states remain explicit-label or `needs_review` gates.
- Analysis boundary: chemical slip, dissociation, duplicate, confidence, and export recommendations are screening signals only. They do not prove a global minimum, final adsorption energy, stable endpoint, or kinetic suitability.
- Runtime policy: compact JSONL and tables only; no automatic VASP/NEB/DIMER/MKM/KMC execution or submission.

## 2026-06-30 - Stage AdsMind Lite Beyond Fe(110)

- Decision: retain Fe(110) as the robust benchmark, then enable deterministic metallic Fe(100) and Fe(111) exposed-layer site detection under the same `metallic_fe` family.
- Carbide/oxide boundary: support their requested site taxonomies only through exact-slab `site_manifest.yaml` records. Automatic high-confidence detection remains disabled until real Fe5C2/Fe2C and Fe3O4/FeOx fixtures are labeled and scientifically validated.
- Identity gate: non-metal structures carry explicit slab/adsorbate index maps after VASP element grouping. Slab carbon and oxygen must be labeled as lattice or adsorbate roles; ambiguity yields low confidence, `needs_review`, and `lattice_adsorbate_atom_confusion`.
- Vacancy gate: `oxygen_vacancy` requires `site_role: vacancy_O`, explicit risk tagging, and explicit validation. Hydroxylated surfaces remain low/review unless validated.
- Export policy: recommended high-confidence and validation-selected medium-confidence structures export by default. Low-confidence or review-required records remain report-only unless explicitly overridden.

## 2026-06-30 - Consolidate Fe(110) Site Rules and Re-audit Step 12A

- Single authority: `scripts/adsorption/build_fe110_adsorption.py` owns Fe(110) generation and nearest-class classification; AdsMind Lite imports it. Numerical tolerances come from `configs/adsmind_lite/site_rules.yaml` and `analysis_rules.yaml`.
- Removed redundancy: delete the unused `site_generation` block from `configs/fe110_adsorbates_step12a.yaml`, the unused reverse site mapping, the obsolete hollow-neighbor threshold, and the duplicate relaxed-site classification algorithm.
- Classification rule: derive topology and pair classes once from the clean relaxed slab, compute lateral distance to every symmetry-equivalent top, short bridge, long bridge, and true hollow candidate, then select the nearest class only when it lies within tolerance. Do not recluster pair classes independently on an adsorbate-distorted slab.
- Step 12A evidence: all 24 submitted POSCARs started in the intended class. At the 17:20 checkpoint, all 11 completed adsorption CONTCARs retained their classes; the four RUN structures also remained in class provisionally, while nine PEND tasks still had only initial POSCARs.

## 2026-07-12 - Freeze the H2/CHx/CHO Adsorption Test Set and Register Results

- User decision: store all existing H2, CH, CH2, CH3, CH4, and CHO adsorption
  results in the project database and do not add further adsorption tests for
  these species without new explicit authority.
- Registered scope: 20 H2/CHx relaxations and four CHO relaxations on
  `true_fe110_5layer_5x5x1`.
- Scientific preservation: dissociated H2 states are `RECLASSIFY`; weak or
  near-desorbed H2/CH4 and nonconverged CHO O-end/top are `NEEDS_REVIEW`;
  duplicate CH, CH2, CH3, and CHO states retain explicit duplicate groups.
- Energy boundary: stored relaxation TOTEN values are interim provenance, not
  final adsorption energies. Dataset promotion remains blocked pending matched
  final statics and the dataset compatibility gate.

## 2026-07-13 - Authorize Two Targeted H2/CHx Completion Screens

- User decision: add exactly two screening relaxations despite the prior finite-set
  freeze: CH2 from a true hollow start and CH3 from a true top start.
- Submission: `9622413` (CH2/hollow) and `9622414` (CH3/top), both under
  `~/sbq/Fe110/adsorption/pilot_h2_chx_completion_20260713` on
  `sunboquan-codex`.
- Input gate: active Fe45/PBE/Gamma `5x5x1` branch, bottom 18 Fe fixed,
  `NSW=80`, `EDIFFG=-0.02 eV/A`, `NPAR=4`, verified Fe/C/H PAW-PBE order;
  both initial structures passed geometry and site-class audits.
- Boundary: these are screening-only and are neither final adsorption energies
  nor formal spreadsheet rows until completed, converged, and scientifically
  reviewed.

## 2026-07-14 - Replace the Symmetric CH2/Hollow Screen with a Tilted 300-Step Run

- User decision: do not keep CH2/hollow as an 80-step screen; use `NSW=300`
  directly, preserve the other parameters, and introduce a bent, asymmetric CH2
  orientation with one H closer to the surface.
- Replacement: stop `9622413` after five ionic steps without accepting a result;
  submit `9622444` in `CH2/hollow_tilted_nsw300`. CH3/top `9622414` is unchanged.
- Structure gate: C remains at true hollow with `0.0296 A` lateral offset;
  C-Fe is `1.947 A`, H-C-H is `109.459 deg`, C-H distances are
  `1.1393/1.1394 A`, and the H height difference is `0.3231 A`.
- Input gate: only `NSW` changed from 80 to 300; the geometry audit and strict
  preflight passed, and the remote Fe/C/H PAW-PBE POTCAR order was verified.
- Boundary: `9622444` is a submitted relaxation, not a converged adsorption
  result or spreadsheet row.

## 2026-07-14 - Purge Valueless Local VASP Attempt Artifacts

- User decision: remove local raw records from adsorption/NEB attempts that have
  no remaining scientific or workflow value.
- Deleted scope: ignored runtime diagnostic snapshots, superseded local NEB
  POTCAR copies, one obsolete NEB path XYZ, and one obsolete convergence-submit
  helper. No remote calculation directory was changed.
- Retention boundary: accepted/negative/duplicate scientific results and the
  distilled reusable failure lessons remain. The stopped CH2 precursor is hidden
  from current state and retained only as minimal provenance for job `9622444`.

## 2026-07-14 - Submit the User-Selected Five C/C2/O Fe(110) Motifs

- User decision: calculate exactly five reviewed motifs rather than a fixed
  four-site sweep: `C*+O*/C@lb+O@h_adj`, two C₂O modes
  (`κ-Cα/lb_tilted` and `η²(Cα,Cβ)/h-lb-h`),
  `C₂/η²(C,C)/h-lb-h`, and the same C₂ motif plus `O@lb_adj`.
- Numerical decision: use `NSW=300` directly for all five; all other active
  Fe45/PBE/Gamma `5x5x1` relaxation settings remain unchanged.
- Evidence boundary: no exact whitelist Fe(110) C2/C2O/C2+O match exists.
  Catalysis-Hub supports intact terminal-C CCO connectivity, while local Step
  12A C-long-bridge and O-high-coordination behavior determines Fe(110) anchors.
- Submission: jobs `9622455-9622459` under
  `~/sbq/Fe110/adsorption/pilot_c_c2_o_20260714`; initial geometry, species
  order, MAGMOM, KPOINTS, POTCAR, and remote strict preflight passed.
- Boundary: these are submitted relaxation candidates, not converged adsorption
  results, adsorption energies, or spreadsheet rows.

## 2026-07-14 - Expand C/C2/O Only with Six Missing User-Specified Candidates

- User decision: reconcile the concrete 11-candidate list against registered
  and active jobs, then submit only missing candidates; apply this missing-only
  rule to future concrete lists and never resubmit duplicates.
- Deduplication: jobs `9622455-9622459` already covered five requested motifs
  and were left unchanged. `C2-3`, blind four-site variants, and any structure
  outside the supplied list were not added.
- Submission: jobs `9622460-9622465` under
  `~/sbq/Fe110/adsorption/pilot_c_c2_o_missing_20260714` cover the remaining
  C+O/lb-lb, C2O/C2-2-derived, C2-2-diagonal, and three missing C2+O variants.
- Input gate: Fe45/PBE/Gamma `5x5x1`, bottom 18 Fe fixed, `NSW=300`, geometry
  audit, species/MAGMOM/POTCAR order, LSF syntax, and remote strict preflight
  all passed.
- Boundary: all six are submitted relaxation candidates, not converged results,
  adsorption energies, or spreadsheet rows.

## 2026-07-14 - Adopt Whitelist-First, Authoritative-Literature Fallback for Adsorption Sites

- Method: search approved catalysis-data whitelist sources first. If a usable
  matching adsorption motif exists, stop and do not run literature retrieval.
- Fallback: only `NO_WHITELIST_MATCH` permits primary-research retrieval from
  authoritative chemistry/materials/catalysis journals. Verify DOI, publisher,
  journal authority, exact surface/facet and adsorbate, geometry, and direct
  stability evidence before accepting a motif.
- Candidate count: generate all and only unique stable configurations supported
  by accepted evidence. Two supported configurations mean two calculations;
  four are generated only when four are supported. Nominal top/bridge/hollow
  classes never determine the count by themselves.
- Implementation: `configs/adsmind_lite/evidence_gate.yaml` and
  `scripts/adsmind_lite/evidence_gate.py` own the decision. Candidate generation
  now requires an evidence-gated plan; legacy fixed 4/6/8 caps and the direct
  all-site batch path were removed.
- Boundary: external evidence is used only for motif selection, relative
  stability ordering, and reviewed initial geometry such as sites, bond
  lengths, angles, heights, and orientation. Its energies cannot enter local
  results, the registry, or Excel. Every generated structure still requires
  local geometry, convergence, and compatible final-static validation.

## 2026-07-17 - Unify NEB and DIMER in Transition-State Strategy Engine V3

- User decision: NEB and DIMER are no longer separate workflow modules. They
  are strategy-selected methods inside one transition-state search lifecycle.
- New order: endpoint/mapping guard, reaction fingerprint, TS-template
  retrieval, rule fallback, strategy composition, reviewed path initialization,
  NEB/CI-NEB, optional DIMER refinement, TS validation, and learning storage.
- Template gate: only successful Grade-A records with a registered TS structure
  and barrier may transfer waypoint/NEB/DIMER strategy. Failed or Grade-B/C
  cases store failure constraints and correction advice only.
- Implementation: `modules/transition_state_search/`,
  `scripts/ts_strategy_engine/`, and
  `configs/ts_strategy_engine/families.yaml` are the unified authority.
  Existing `scripts/neb_agent/` remains only the numerical backend.
- Removed scope: separate NEB/DIMER module authorities, the standalone DIMER
  wrapper, the superseded NEB orchestration CLI, and two unreferenced duplicate
  precheck/geometry scripts. No calculation result or remote task was deleted.

## 2026-07-17 - Make V3 Evidence-Bound End to End

- Superseding rule: the historical fixed-eight-image NEB default is retired.
  Start from the family/template-supported minimum and add images only for
  displacement, curvature, or resolution evidence.
- Contract gate: reactant/product identity, full identity atom map, indexed
  bond changes, endpoint IDs, and exact material, facet, slab, XC, POTCAR,
  ENCUT, k-mesh, magnetic, and coverage branch are hard requirements.
- Path gate: executable reviewed waypoints or accepted constraints are required
  for bond-changing paths. Generated paths, `dist.pl`, `nebmovie.pl 0`, NEB
  analysis, DIMER, and VFA are linked by content hashes; altered or missing
  evidence stops advancement.
- Validation gate: DIMER needs negative curvature and force convergence but is
  not a validated TS. Grade A additionally requires exactly one intended
  imaginary mode, reviewed positive/negative connectivity, confirmed evidence
  files, source-saddle binding, and the same reaction/method contract.
- Energy gate: the NEB/DIMER energy profile is diagnostic only. Forward,
  reverse, and reaction energies are reportable only from one registered
  matched-static IS/TS/FS chain.
- Configuration gate: `configs/true_fe110_production.yaml` is the sole Fe(110)
  numerical authority; the custodian profile only maps stages to it.

## 2026-07-17 - Submit Two Failure-Informed `[C]O[CH][CH]` Screening Poses

- User authorization: submit the previously built terminal-CH C/top pose and
  one new user-specified `h-lb-h`-like dual-end pose together.
- Geometry gate: both preserve the exact C3H2O molecular graph and bottom 18
  fixed Fe atoms. The new pose has C46-Fe/C47-Fe/O49-Fe/C48-Fe distances of
  `2.10/2.10/2.21/3.20 A` and keeps C47-O49/C46-C47 at `1.366/1.415 A`.
- Submission: jobs `9629858` and `9629859` use the locked Fe45/PBE/400 eV/
  Gamma `5x5x1` branch with the default `NSW=80` screening stage under
  `~/sbq/Fe110/adsorption/care_c3h2o_rebuild_pair_20260717`.
- Boundary: these are screening relaxations only. Submission and scheduler
  `PEND` do not establish convergence, intact final chemistry, or stability.

## 2026-07-18 - Use AQCat25 GPU Acceleration for Adsorption and TS Work

- `work` is the orchestration, evidence-gate, review, handoff, registry, and
  scientific-acceptance authority.
- `BUCT(sbq)` / `MZ73` owns AQCat25 adsorption-candidate pre-relaxation/ranking
  and TS endpoint relaxation, IDPP/BA-Sella candidate generation, and
  force-only fine-tuning. Its outputs are predictions only; it does not run or
  submit VASP.
- `sunboquan-codex` owns all adsorption VASP relaxations/final statics and all
  project VASP/VTST TS calculations. Returned calculation evidence still
  requires the owning module's validation.
- Every adsorption GPU candidate returns to `work` with evidence-plan,
  structure, compatibility, model-checkpoint, optimizer, unit, and
  domain-status provenance. Every TS GPU candidate additionally carries the
  reaction-contract and atom-map bindings. Direct GPU-to-VASP transfer and
  automatic submission are forbidden.
- AQCat cannot replace the whitelist-first external-evidence gate, remove an
  evidence-required adsorption motif by itself, establish a final adsorption
  site/global minimum, replace VASP energies/forces, or pass Grade-A vibration
  and bidirectional-connectivity gates.
- Machine-readable authority: `configs/execution_backends.yaml`.

## 2026-07-18 - Enforce AQCat25 Contract, Species Generality, and Domain Gate

- Contract: every AQCat25 transfer uses schema v2 in
  `configs/aqcat25_handoff.schema.json` and executable bound-file validation in
  `scripts/aqcat25_handoff.py` on both `work` and MZ73.
- Species rule: adsorbate indices, anchors, connectivity/separation limits, and
  monitored pairs are manifest data. A runner may not require a fixed C/O
  composition or emit a molecule-specific verdict for all species.
- Calibration: the active checkpoint passed the predeclared force gate on 13
  compatible, converged Fe45 adsorption structures. Its accepted scope is
  near-relaxed Fe45 adsorption containing Fe/H/C/O with 2--6 adsorbate atoms.
- Uncertainty boundary: one checkpoint supplies empirical reference-set force
  error, not per-candidate predictive uncertainty. TS/path/saddle geometry is
  explicitly uncalibrated and cannot receive an in-domain verdict from this
  adsorption set.
- Scheduler boundary: every GPU job must write a hash-bound producer exit
  record. It does not become scheduler authority; durable `sacct` terminal
  state requires an MZ73 administrator to enable Slurm accounting.

## 2026-07-19 - Lock the DFT Basis Across TS Stages and Register Final Barriers

- All TS calculations in the active true-Fe(110) production branch use one
  fixed DFT basis: the accepted five-layer Fe45 slab, bottom two layers fixed,
  endpoint-contract cell/coverage/vacuum, PBE (`GGA=PE`), the approved PAW-PBE
  Fe/C/O POTCAR family and order, `ENCUT=400 eV`, Gamma `5x5x1`, spin/MAGMOM
  convention, atom order, Selective Dynamics, symmetry, and dipole policy.
- Stage algorithms and convergence controls may vary only through an approved
  ordinary-NEB, refinement, CI-NEB, DIMER, frequency, or matched-static
  template. Examples include `EDIFF`, `EDIFFG`, optimizer tags, `LCLIMB`, image
  count, frequency displacement/active atoms, and compute resources. Such a
  change does not create permission to alter the fixed DFT basis.
- Any exception to a fixed field requires an explicit method decision and a
  separate compatibility branch; its energies cannot be mixed with the active
  branch.
- AQCat25 predictions and exploratory NEB image energies remain diagnostic.
  A reportable barrier requires a Grade-A TS, vibration and bidirectional
  connectivity validation, then matched `final_static` IS/TS/FS calculations
  with one compatibility fingerprint.
- Before promotion into the project dataset, register the accepted IS/TS/FS
  structures, energies, hashes, compatibility fingerprint, validation state,
  and provenance in `data/project_registry.sqlite3`.

## 2026-07-20 - Implement the Full AQCat25 TS Sequential Active-Learning Loop

- Implement the full reviewed sequence: AQCat25/BA-Sella candidate ->
  `sunboquan-codex` static VASP force label -> exact-structure AQCat25 force
  comparison -> force-only fine-tuning on MZ73 when thresholds fail -> BA-Sella
  rerun with the new checkpoint -> repeat or hand off to VASP refinement.
- A VASP label is trainable only after LSF `DONE`, normal OUTCAR completion,
  electronic convergence before `NELM`, an exact structure hash, and a complete
  atom-aligned force block. It is marked `force_label_only`, not a final energy.
- Active-learning convergence means model-force agreement only. It does not
  establish a TS, a barrier, vibration validity, or endpoint connectivity.
- ML energies/forces and VASP force-label energies are never promoted into
  final energy tables. Final results consume only completed, converged,
  scientifically validated VASP evidence.
- The barrier registry additionally requires accepted `sunboquan-codex` LSF
  job evidence for all matched-static IS/TS/FS values, plus Grade-A vibration
  and bidirectional-connectivity validation.
- GPU force-prediction, ASE training-data, and force-only fine-tuning runners
  are deployed only under `/home/sbq/sbq/aqcat25_ts_pilot/`; deployment does
  not authorize or imply a submitted GPU or VASP job.

## 2026-07-22 - Make TS-Domain Calibration Trigger-Based

- Do not require a new five-point TS calibration set for every reviewed NEB
  path. Bootstrap the uncalibrated TS domain once, then revalidate only after a
  checkpoint/compatibility change, an out-of-domain or novelty failure, or a
  scheduled audit.
- A path using the exact calibrated checkpoint and compatibility branch may
  reuse calibration only when it is inside the reviewed reaction domain and
  passes the novelty/uncertainty gate.
- Independent calibration uses at least five unique held-out structures across
  rising, near-saddle, and falling path regions. Their structure hashes may not
  overlap any TS training round or adsorption replay set.
- Existing VASP force labels may replace a new static job only when exact
  structure and compatibility hashes, normal completion, electronic
  convergence, complete atom-aligned forces, and scheduler evidence all pass.
  A stored energy without forces is not a calibration label.
- This policy affects AQCat25 acceleration readiness only. Final barriers still
  require the complete converged and validated VASP workflow.
- Implementation: the controller now evaluates reuse through a Schema-bound
  context and requires bootstrap metrics plus an explicit calibration review;
  policy and label hashes are rechecked before every consuming stage.

## 2026-07-22 - Harden Grade-A Structure and Frequency Evidence

- Bidirectional downhill classification must match the indexed bond change,
  reaction-atom endpoint geometry, and fixed-atom stability. A matching C-O
  distance alone cannot establish IS/FS connectivity.
- Grade A requires one hash chain joining the source saddle, VFA handoff,
  frequency POSCAR/OUTCAR, displacement calculations, and connectivity report.
- DIMER technical convergence requires a valid contract-bound POSCAR/CONTCAR,
  DIMER input, electronic convergence, reviewed modes, and LSF `DONE` evidence.
- Until meaningful-imaginary and additional-soft-mode thresholds are explicitly
  configured, frequency analysis remains `Ungraded` and cannot produce Grade A
  or B.

## 2026-07-23 - Establish One Authoritative NEB Execution Gate

- `scripts/ts_strategy_engine/execution_gate.py` is the sole authority for
  continue/stop/rebuild/submission/CI-NEB/DIMER/TS/barrier actions.
- Parsers, monitors, path-quality checks, strategy composition, and workflow
  orchestration emit evidence only. The executor must verify a current
  state hash and an explicit `ALLOWED_ACTIONS` entry.
- Priority is fixed: data integrity, endpoints, electronic convergence,
  reaction-coordinate continuity, elementary-step purity, ordinary NEB,
  CI readiness, DIMER readiness, frequency/connectivity, then resource
  preflight. A later pass cannot override an earlier failure.
- Job `9631737` was stopped after the path-quality evidence persisted through
  step 86. Image 02 electronic remediation precedes the authorized full-path
  rebuild; the stopped images may be waypoints but never independent endpoints.
- `ALGO` is an approved stage-specific NEB control, not part of the fixed DFT
  basis. A production override requires a successful compatible diagnostic and
  remains recorded in the input/profile hash.
- Correction: diagnostic job `9638221` exposed that VASP output buffering can
  mimic a progress stall. Its premature stop is retained as failed process
  evidence. The superseding rule below requires `STOP_JOB` to bind the exact
  running job and current source files; a prior calculation's decision or an
  inline confirmation boolean cannot stop a new diagnostic.
- Production ordinary NEB requires a completed one-step same-path pilot.
  Pilot acceptance is rebuilt from live LSF `DONE`, per-image VASP outputs,
  path/input hashes, and the current magnetic-continuity evidence object; a
  manually assembled `passed=true` JSON cannot authorize production.
- Workflow stages write only machine-verifiable JSON and required VASP/
  structure evidence. Duplicate Markdown summaries and automatic plots are no
  longer generated. Submission uploads only the hash-bound preflight manifest;
  other directory contents are not copied merely because they share the local
  calculation directory.
- Local DIMER handoff preparation and actual DIMER execution are distinct:
  `PREPARE_DIMER_HANDOFF` may create the reviewable input, while
  `START_DIMER` remains unavailable until that exact bundle passes DIMER
  preflight.

## 2026-07-24 - Approve CO-Dissociation High-Spin Initialization Branch

- Exact-geometry diagnostic `9639279` proved that the image-06 `2.2 muB/Fe`
  cold start selected a magnetic branch `2.29958246 eV` above the converged
  adjacent-image-compatible state.
- The user approved `fe110_co_dissociation_highspin_seed_v1`, using
  `MAGMOM=2.4 muB/Fe` only for Fe(110) CO-dissociation ordinary-NEB
  initialization. All other DFT-basis and final-result gates remain unchanged.
- The branch cannot authorize production from one image alone. A one-step
  full-path pilot must prove electronic convergence and input/path identity
  before ordinary NEB submission.

## 2026-07-24 - Make Magnetic Continuity a Soft Warning

- This decision supersedes the former hard rule that rejected a pilot or
  blocked ordinary no-climb NEB solely because adjacent total magnetization
  differed by more than `2.0 muB`.
- The threshold now triggers only a magnetic-state continuity review. It does
  not independently stop a job, block ordinary no-climb NEB, or prove a
  magnetic-state switch.

## 2026-07-24 - Separate NEB Hard Failures from Diagnostic Warnings

- Remove `stop_condition_confirmed` and all inline-JSON stop authority. A real
  `STOP_JOB` decision requires the blocker-specific parser artifacts, their
  current raw-source hashes, the bound thresholds, and raw LSF query evidence.
  Underresolution also requires the path-quality artifact. The authoritative
  gate is upgraded to Schema v2; earlier decisions cannot be reused.
- One `NELM` exhaustion, early/nonpersistent high force, one-frame internal
  energy minima, one-coordinate backtracking, large endpoint motion, and
  adsorption-height heuristics are review evidence only.
- Persistent underresolution is counted by independent evidence families;
  duplicated descriptions of one gap cannot satisfy the gate by themselves.
- Incomplete frequency output is `Ungraded`. Only normally completed,
  threshold-classified significant modes may produce Grade C.
- Downhill endpoint tolerances are configurable. A tolerance miss becomes
  `NEEDS_REVIEW`; it does not independently prove failed connectivity.

## 2026-07-27 - Stop Underresolved Eight-Image CO-Dissociation NEB

- The user explicitly authorized stopping production ordinary no-climb NEB
  job `9640936`.
- Current geometry, output analysis, path-quality thresholds, raw LSF `RUN`
  evidence, and their source hashes were bound into a Schema-v2 authoritative
  decision. The gate returned `STOP_UNDERRESOLVED_PATH` and allowed only
  `STOP_JOB` and `REBUILD_PATH`.
- The sole executor issued `STOP_JOB`; LSF subsequently confirmed `EXIT`.
- Independent endpoint audit found no IS/FS corruption, atom-map error,
  fixed-mask mismatch, collision, or unphysical endpoint bond geometry. The
  blocker is the persistent image-05/06 loss of the `1.50-2.10 A` C-O
  interval, not the accepted endpoint structures.
- The gate's `REBUILD_PATH` allowance is technical authority only. The user's
  stop-and-inspect request does not authorize a rebuild or another VASP
  submission.

## 2026-07-27 - Authorize Local IDPP Path Rebuild

- The user authorized rebuilding the CO-dissociation path with IDPP.
- The authorization covers local path generation and review only. It does not
  authorize another VASP submission, CI-NEB, DIMER, frequency, downhill, or a
  barrier claim.
- The rebuild must use the accepted full IS/FS, omit relaxed images from the
  two failed NEB paths, and explicitly sample the previously missing
  `1.50-2.10 A` C-O interval before any submission decision.
- The first 12-interior-image candidate sampled that interval under
  minimum-image geometry but failed raw periodic-coordinate continuity at
  06/07 and 12/13. It is retained as failed local evidence and is not approved
  for `dist.pl`, `nebmovie.pl 0`, input preparation, or submission.
- The user then authorized continuous-branch correction. The replacement
  candidate uses sequential minimum-image unwrapping, exact image-00
  coordinates for every fixed Fe, and a raw-coordinate continuity gate.
  Local geometry passes, but this does not authorize VASP submission.

## 2026-07-27 - Submit Continuous-Branch CO-Dissociation Pilot

- The user explicitly approved submitting the corrected continuous-branch
  path. Its contract-bound 14 POSCAR files are byte-identical to the approved
  candidate; `dist.pl`, `nebmovie.pl 0`, geometry review, and input preflights
  passed.
- The first NP=192 submission attempt was rejected by LSF before job creation
  because the request exceeded the account's job-slot limit. No calculation
  ran under that attempt.
- Resource count was reduced to NP=96 while preserving every scientific input
  and path coordinate. A new hash-bound gate returned `READY_FOR_NEB_PILOT`
  and allowed only `SUBMIT_DIAGNOSTIC_VASP`.
- The sole executor submitted one-step ordinary no-climb NEB pilot job
  `9645737`. It was `PEND` at the 2026-07-27 16:10 checkpoint. Production
  submission remains conditional on this exact-path pilot passing.

## 2026-07-27 - Reduce Reviewed Path from 12 to 9 Internal Images

- The user rejected the projected cost of carrying 12 internal images through
  ordinary NEB and CI-NEB and authorized a local nine-image rebuild.
- The reduction is reaction-coordinate-aware rather than uniform decimation.
  Source images `02,04,05,06,07,08,10,11,12` are retained from the reviewed
  continuous path. All five images in the previously lost C-O
  `1.50-2.10 A` neighborhood remain represented.
- The new path preserves endpoints, atom order, Selective Dynamics, the exact
  bottom-18-Fe coordinates, raw periodic continuity, reaction-contract hashes,
  and endpoint `dist.pl`. Its geometry gate passes and `nebmovie.pl 0`
  completed.
- This local rebuild does not authorize submission or stopping job `9645737`.
  The existing job remained `PEND` at the latest checkpoint.

## 2026-07-27 - Replace Queued 12-Image Pilot with Nine-Image Trial

- The user explicitly instructed Codex to cancel queued pilot `9645737` and
  run the complete nine-internal-image path as a one-step trial.
- A file-bound user stop authorization and current raw LSF `PEND` evidence
  produced `STOP_USER_REQUESTED` with only `STOP_JOB` allowed. The sole
  executor cancelled the job; LSF confirmed `EXIT` before VASP ran.
- The exact nine-image path passed geometry, `dist.pl`, `nebmovie.pl 0`, both
  input preflights, remote POTCAR verification, and the diagnostic submission
  gate. Pilot `9646067` was submitted with `NSW=1`, NP=72, and remained `PEND`
  at the latest checkpoint.
- Formal ordinary NEB is authorized only after the pilot proves normal SCF,
  evaluates the `1.5 eV/A` atomic-force warning threshold, preserves ordered
  C-O progression without endpoint collapse, shows no independent O-site jump
  at image 06/07, and keeps Fe motion local with all bottom-18 Fe fixed.

## 2026-07-27 - Stop Nine-Image Pilot and Restore the Missing Local Waypoint

- The user rejected image 07 and explicitly instructed Codex to pause the
  calculation. Current file-bound user and scheduler evidence produced
  `STOP_USER_REQUESTED` with only `STOP_JOB` allowed. The sole executor stopped
  job `9646067`; LSF confirmed `EXIT`. The heartbeat monitor was paused.
- Because no ionic step completed, empty CONTCAR files prevent force and
  relaxed-geometry validation. `nebmovie.pl 1` was attempted and failed for
  this documented reason.
- Input geometry proves that the nine-image reduction omitted source image 09
  and merged two approximately `0.309 A` O moves into one `0.617189 A` move.
  The preferred local repair is the already generated ten-image candidate,
  which restores source image 09 and passes the geometry gate.
- The stopped output also identifies an independent magnetic SCF instability
  at the `C-O=2.514489 A` geometry. Restoring a waypoint is not accepted as an
  SCF fix. No whole-path pilot or formal NEB is authorized before a separate
  low-cost exact-geometry static branch-continuation preflight.

## 2026-07-28 - Authorize Sequential Image-07 to Image-08 Static Branch Test

- The user authorized only two sequential `NSW=0` diagnostics: converge
  repaired image 07 while saving CHGCAR/WAVECAR, then initialize repaired
  image 08 from those files only if image 07 passes EDIFF and magnetic
  stability checks.
- Image 07 passed the structure, INCAR, generic-input, executor-preflight, and
  hash-bound gate checks. The sole executor submitted job `9646608` at 32
  cores; remote inputs and POTCAR hashes match.
- Image 08 and every whole-path NEB stage remain unsubmitted. Image 08 may
  proceed only after image 07 is scheduler `DONE`, normally completed,
  electronically converged, magnetically stable, and has non-empty restart
  files.

## 2026-07-28 - Advance Validated Image-07 Branch to Image 08

- Image-07 job `9646608` passed every user-approved advancement condition:
  LSF `DONE`, normal completion, no fatal output, EDIFF at DAV 62, final
  magnetization `105.3424372 muB`, last-12 span `0.3493404 muB`, agreement
  with the stable neighboring branch, unchanged structure, and non-empty
  hash-bound CHGCAR/WAVECAR.
- Image 08 uses the exact repaired-path POSCAR and changes only the restart
  identity (`ISTART=1`, `ICHARG=1`) plus its SYSTEM label. Its manifest inputs
  and image-07 restart files were remotely hash-verified before submission.
- The current authoritative gate allowed only `SUBMIT_DIAGNOSTIC_VASP`; the
  sole executor submitted job `9646670` with `--reuse-uploaded`. VASP confirms
  the WAVECAR is read. No NEB, CI-NEB, DIMER, frequency, or barrier action was
  authorized.

## 2026-07-28 - Complete Image-07 to Image-08 Electronic Branch Preflight

- Image-08 job `9646670` is LSF `DONE`, normally completed without fatal
  output, read the image-07 WAVECAR, and met EDIFF at DAV 24.
- Its final total magnetization is `105.4450488 muB`; the last-12 span is
  `0.0570777 muB` and the maximum difference from the stable neighboring
  references is `0.0754488 muB`. The exact structure and bottom-18 Fe are
  unchanged within numerical output precision, and final CHGCAR/WAVECAR are
  non-empty and hash-bound.
- This completes only the static electronic-branch preflight. It validates
  restart continuity from repaired image 07 to 08 but does not prove force/path
  convergence, endpoint non-collapse, or authorize a whole-path NEB.
## 2026-07-28 - Seed only repaired images 07/08 in the full-path pilot

- For the authorized ten-internal-image `NSW=1` pilot, preserve the validated
  magnetic/electronic branch only on repaired image 07/08 by placing their
  hash-verified WAVECARs in the corresponding NEB directories.
- Do not add unapproved `ISTART`/`ICHARG` overrides and do not copy either
  restart state to unrelated geometries. VASP therefore selects `ISTART=1` on
  image 07/08 and falls back to `ISTART=0` elsewhere; the runtime OUTCAR files
  confirm this exact split.
- The pilot gate allows only `SUBMIT_DIAGNOSTIC_VASP`. Its result cannot
  authorize or substitute for a production NEB without the full scientific
  validation and a new hash-bound gate.

## 2026-07-28 - Replace CI-Only DIMER Eligibility with a Local Hard Gate

- DIMER may refine candidates from either ordinary no-climb NEB or CI-NEB.
  `LCLIMB` and full-path final convergence are not DIMER hard requirements.
- `START_DIMER` now requires a hash-bound local triad and MODECAR hard gate:
  matching structure contracts, internal adjacent images, complete electronic
  results with readable energies/forces, continuous reaction-center mapping,
  accepted site/mechanism/mode review, fixed-mode zeros, and a finite,
  normalized reaction-aligned mode.
- Full parent-path convergence, a strict local peak, reduced peak-triad forces,
  no real intermediate, and an between-basin candidate remain recommended
  evidence. They guide selection but do not override or replace the hard gate.
- DIMER technical convergence now also requires Torque not exceeding the
  configured `DFNMin`. Final TS acceptance remains exactly one valid
  reaction-aligned imaginary mode plus hash-bound bidirectional IS/FS
  connectivity.
- A coarse ordinary NEB with stable non-peak internal images and a persistently
  stalled highest-energy image is now a DIMER handoff recommendation. The
  configured trigger requires at least 20 peak ionic steps, peak force
  `>=0.5 eV/A` with plateau/oscillation, and all other internal-image forces
  `<=0.5 eV/A`. It permits handoff preparation only; DIMER submission still
  requires every local hard-gate condition.

## 2026-07-28 - Test Image 07 as a Local Dissociation Endpoint

- The user approved independently relaxing the old 203-step ordinary-NEB
  image 07 to test whether it is a locally stable dissociated product.
- Route this structure explicitly as `TS_ENDPOINT`, not as the global stable
  adsorption product. Retain all large-displacement warnings; they do not
  become endpoint acceptance merely because the intended C-O break and
  reviewed Fe-C/O site-coordination changes are present.
- Submit only one compatible endpoint relaxation. A successful result must
  remain dissociated, retain the local C/O adsorption basin, converge
  electronically and ionically, and pass post-relaxation endpoint validation
  before it may replace the global product as the FS of a shortened
  dissociation-only NEB.
- This decision does not authorize NEB, CI-NEB, DIMER, frequency, or barrier
  work.

## 2026-07-29 - Accept Relaxed Image-07 Product as a Local TS-Endpoint Candidate

- Job `9647798` is LSF `DONE`, normally and electronically/ionically
  converged, with final maximum force `0.016035 eV/A`.
- The original old-NEB image 07 is not itself the endpoint: independent
  relaxation moves O continuously from a long-bridge-like boundary into a
  local hollow. The final structure is C@long-bridge + O@hollow with C-O
  `3.1131 A`.
- This settling belongs to the intended dissociation endpoint event, not an
  additional independent O-diffusion event: the 61-step trajectory has
  maximum single-step O motion `0.1666 A`, no periodic jump, and no unexpected
  bond/site change.
- Retain the validator's global reactive-displacement warning. Accept the
  final CONTCAR only as a locally stable `TS_ENDPOINT` candidate. Do not use it
  for production NEB until a shortened IS-to-candidate path passes mapping,
  geometry, reaction-event, and path-connectivity review.
- No NEB, CI-NEB, DIMER, frequency, database write, or barrier action is
  authorized by this decision.

## 2026-07-31 - Clarify NEB Persistent-High-Force Warning

- `1.5 eV/A` is an NEB-force warning line, not a convergence target or an
  early-step failure threshold.
- The first five ionic steps are an allowed startup window. High force after
  that window with no decreasing trend is warning evidence only.
- Persistent high force becomes path-failure evidence only after at least ten
  ionic steps without a decreasing trend, or when high force is accompanied by
  independently verified abnormal displacement, periodic-image jump, or
  magnetic discontinuity.
- An `NSW=1` pilot may test electronic convergence, restart behavior, magnetic
  continuity, runtime completeness, and immediate geometry sanity, but cannot
  establish ionic force convergence.
- A warning alone remains non-blocking. Continue/stop/rebuild/production
  actions require the current hash-bound authoritative execution gate.

## 2026-08-01 - Permit Hash-Bound Selective Electronic Restart for Ordinary NEB

- `ISTART` and `ICHARG` are permitted ordinary-NEB initialization controls;
  they do not alter the locked DFT basis or final-energy convention.
- Selective restart is allowed only when the restart files are nonempty,
  hash-bound, cell/order compatible, and already validated on the target
  electronic branch.
- For the rebuilt seven-image CO-dissociation pilot, only image05 receives the
  validated job-9652245 CHGCAR/WAVECAR. With root `ISTART=1`, `ICHARG=1`, VASP
  falls back to `ISTART=0`, `ICHARG=2` for images lacking a valid WAVECAR;
  image05 must explicitly prove that its WAVECAR was read.
- This decision authorizes electronic initialization only. Geometry, path,
  pilot, and execution gates remain mandatory.

## 2026-08-01 - Treat First-Step Magnetic Discontinuity as a Trend Warning

- The user clarified that image07 reaching `82.0736 muB` after only the first
  ionic step must not independently block the coarse ordinary NEB.
- This matches `MAGNETIC_CONTINUITY_RULE`: adjacent total-magnetization changes
  above `2.0 muB` remain `SOFT_WARNING` evidence and require trend review; they
  do not alone prove a physical magnetic transition or path failure.
- The exact-path seven-image coarse run may proceed after all nonmagnetic
  pilot, geometry, restart, preflight, and execution gates pass. Review SCF,
  magnetic, force, and geometry trends at ionic steps 3, 5, and 10.
- Persistent magnetic separation becomes blocking only with supporting SCF,
  local-moment/energy, or independently verified geometry/path-discontinuity
  evidence. This decision does not authorize CI-NEB, DIMER, frequency, or a
  barrier claim.

## 2026-08-01 - Revalidate Exact Path After Doubling NEB MPI Ranks

- The user requested doubling the coarse ordinary-NEB allocation from 56 to
  112 MPI ranks. Pending job `9654159` was stopped before VASP began.
- `script.lsf` is a hash-bound shared pilot input. Therefore the completed
  56-core pilot cannot be reused to authorize 112-core production even though
  the geometry and INCAR are unchanged.
- Run one same-path 112-core `NSW=1` diagnostic pilot first. Only its successful
  electronic, output, magnetic-warning, and geometry review may authorize the
  same-path 112-core `NSW=50` coarse ordinary NEB.

## 2026-08-03 - Stop Divergent Nine-Image Pilot and Audit Prior One-Step Paths

- The user explicitly paused job `9655921`. A current file-bound user
  authorization and raw LSF `RUN` evidence produced `STOP_USER_REQUESTED` with
  only `STOP_JOB` allowed; the sole executor stopped it and LSF now reports
  `EXIT`.
- The job completed zero ionic steps. Image09 exhausted `NELM=200` with
  repeated BRMIX and runaway electronic energies. All internal CONTCAR files
  are empty, so `nebmovie.pl 1` cannot produce a post-run trajectory and no
  force or relaxed-geometry conclusion is available.
- The prior one-step audit separates two cases. Jobs `9650404` and `9654860`
  contain one or more `NELM=200` images but also large magnetic-branch changes,
  so they are not preferred reusable paths. Jobs `9640399` and `9647154` have
  electronically normal one-step outputs and continuous total moments, but
  use the older full-product endpoint and retain their documented path/force
  limitations.
- No replacement NEB or downstream TS calculation is authorized by this
  audit. Any reuse must first create a local current-endpoint candidate and
  repeat mapping, geometry, `dist.pl`, and `nebmovie.pl 0` review.

## 2026-08-03 - Reject Exact Resubmission of the 9640399 Eight-Image Path

- The user selected one-step pilot `9640399` and requested a direct high-core
  coarse ordinary NEB. Hash comparison proves all 00--09 pilot POSCAR files
  are identical to the initial POSCAR files of production job `9640936`.
- Job `9640936` already ran this exact path at 128 MPI ranks for 203 ionic
  steps. Its electronically normal trajectory developed a persistent and
  increasing image05/image06 reaction-coordinate gap and separate-basin
  behavior.
- The current execution gate recomputed from the stopped-job geometry,
  analysis, path-quality, thresholds, and terminal scheduler evidence returns
  `STOP_UNDERRESOLVED_PATH`. Only `REBUILD_PATH` is allowed;
  `SUBMIT_VASP` is explicitly forbidden.
- No duplicate coarse NEB was prepared or submitted. Reusing the pilot
  CONTCAR files would define a different path and would require fresh path
  review and a new one-step same-path pilot before production.

## 2026-08-03 - Use the 9640399 Image04 Local Peak as a Dimer Candidate

- The user accepted a low-cost Dimer refinement based on source images
  `03/04/05` from completed one-step ordinary-NEB pilot `9640399`, rather than
  resubmitting its known-underresolved full path.
- The triad was relabeled locally as `00/01/02` and normalized only onto one
  continuous periodic branch. Source hashes prove that no physical geometry,
  atom order, cell, or Selective Dynamics mask changed.
- Local image `01` (source image `04`) is a strict energy maximum. Its C-O
  distance is `1.744 A`, bracketed by `1.298 A` and `2.006 A`; all three source
  calculations completed normally and electronically converged.
- The accepted MODECAR is generated only from the two neighboring structures,
  has zero components on the fixed bottom 18 Fe, and places `90.1%` of its norm
  on C/O. This authorizes Dimer refinement only; it is not TS acceptance.
- The exact 32-core bundle passed the Dimer hard gate and submission preflight.
  Job `9656664` was submitted through the sole executor. Frequency,
  connectivity, matched-static, and barrier actions remain unauthorized.

## 2026-08-05 - Separate Dimer Hard Convergence from Force/Torque Review

- Dimer-to-frequency hard convergence now requires normal/electronic VASP
  completion, maximum atomic force meeting `EDIFFG`, negative curvature,
  contract/provenance evidence, and accepted initial/final mode reviews.
- DIMCAR Force and Torque are soft diagnostics. A miss cannot silently pass:
  frequency handoff requires a SHA-256-bound human review acknowledging the
  exact warnings.
- `allow_frequency_handoff` authorizes only a diagnostic frequency run;
  `accept_for_ts_validation` is the stronger decision needed before those
  residuals can contribute to Grade-A eligibility. Frequency and connectivity
  validation remain independent requirements.
- Old Dimer job `9656664` passes the hard VASP force and negative-curvature
  checks but misses both soft metrics. The user-authorized diagnostic C/O-only
  VFA was submitted as job `9694935`; it is not a validated TS claim.

## 2026-08-05 - Stop Tight-Force Dimer Continuation and Fix OUTCAR Force Rule

- The user explicitly stopped Dimer continuation job `9694894`; the
  hash-bound stop gate allowed only `STOP_JOB`, and LSF now records `EXIT`.
- Future Dimer force handoff checks use the final complete
  `FORCES: max atom, RMS` line in `OUTCAR`. The first value (`max atom`) must be
  at most `abs(EDIFFG)`; the RMS value is retained as evidence but cannot hide
  an individual high-force atom.
- This changes only the Dimer force-convergence component. Electronic/normal
  completion, negative curvature, structure/mode provenance, frequency-mode
  assignment, and bidirectional connectivity remain separate requirements.

## 2026-08-05 - C/O-Only Diagnostic VFA Completed

- Job `9694935` completed normally and electronically converged with no fatal
  error; local and remote POSCAR/CONTCAR/OUTCAR/OSZICAR/vasp.out/vasprun.xml
  hashes match.
- The partial Hessian contains five real modes and one imaginary mode at
  `537.451689 cm^-1`. C/O are the dominant atoms, and the relative C/O motion
  projects `98.37%` onto the C-O bond direction.
- This supports the intended CO-dissociation mode but remains `Ungraded`:
  only C/O were active, active-set convergence is untested, frequency
  thresholds are not configured, and bidirectional connectivity is absent.
- The real VASP frequency-vector rows omit atom indices. The parser now uses
  their row order as atom order and has a regression test; scheduler evidence
  Schema now accepts the explicit `vfa` stage.

<!-- state-handoff:start task_decision_events -->
## Managed Decisions

<!-- state-handoff:end task_decision_events -->

## 2026-08-06 - Remove Connectivity from Dimer Acceptance

- Dimer TS acceptance now requires Dimer technical convergence, negative
  curvature, accepted target-mode assignment, exactly one meaningful imaginary
  mode under configured frequency thresholds, geometry acceptance, and bound
  provenance.
- Positive/negative downhill connectivity is retained only as optional
  diagnostic evidence for Dimer. It cannot pass, fail, or block Dimer grading.
- Existing connectivity files and historical records are preserved. NEB/CI-NEB
  connectivity policy is unchanged.

## 2026-08-07 - Adopt Converged SIGMA=0.20 TOTEN as the Fe(110) Formal Energy

- By explicit user decision, the active five-layer Fe(110) branch no longer
  requires a separate matched single-point calculation for adsorption,
  reaction, or barrier energies.
- The formal surface-state convention is the final `OUTCAR` `TOTEN` from a
  compatible, electronically converged and ionically/method-converged VASP
  calculation with `ISMEAR=1`, `SIGMA=0.20 eV`:
  `fe110_converged_toten_sigma0p20_v1`.
- For a barrier, IS and FS must be accepted converged endpoint relaxations and
  TS must be an accepted saddle-search structure. All three energies require
  one compatibility fingerprint and hash-bound source outputs. A DIMER result
  still requires its independent technical and frequency acceptance.
- Existing `SIGMA=0.10 eV` matched statics remain historical/optional
  convergence evidence. They cannot be mixed with the active `SIGMA=0.20 eV`
  energy chain.
- `energy(sigma->0)` may be retained as supplementary evidence, but the active
  difference convention is final `TOTEN`, matching the existing Topic-1 table's
  F-energy and relative-energy convention.

## 2026-08-07 - Use Contract-Defined Local Partial Hessians for TS Frequencies

- By explicit user decision, future TS frequency validation uses a
  contract-defined local finite-difference partial Hessian by default, not a
  full Hessian over every movable slab atom.
- Every reaction atom must be active. Directly coordinated surface atoms may be
  included when required by the reviewed local mechanism; fixed slab atoms may
  not be activated silently.
- The active set is expanded only when the principal mode is ambiguous, local
  surface-mode coupling remains unresolved, or the user explicitly requests a
  larger scope. A full Hessian is not a default acceptance requirement.
- Frequency and thermochemistry reports must identify the partial-Hessian
  method. IS, TS, and FS must use the same reviewed local active-set definition
  when ZPE or thermal corrections are compared.

## 2026-08-07 - Separate TS Strategy Reuse from Result Reuse

- Similar validated reactions may reuse method strategy when their reaction
  family and bond/site event match the configured similarity threshold.
- Strategy reuse is limited to waypoint, interpolation, NEB, DIMER, and local
  frequency choices and always requires review before execution.
- Result reuse remains exact-fingerprint only and permits referencing the
  existing registered result, not copying it into a new calculation.
- Endpoint coordinates, atom indices, MODECAR, CHGCAR/WAVECAR, image numbers,
  energies, and barriers are never transferred by reaction similarity.

## 2026-08-18 - Use a Reviewed Active-Learning Loop and Automatic Result Registration

- Fe(110) adsorption and hydrogen-transfer work should accumulate compatible
  VASP structures and atom-aligned force labels for AQCat25. Fine-tuning is
  triggered by reviewed force error, novelty, or domain status; it is not run
  mechanically after every calculation.
- The GPU active-learning loop is shared infrastructure, not a fixed TS search
  recipe. Its role is candidate acceleration and force-model improvement; it
  does not prescribe ordinary NEB, CI-NEB, Dimer, image count, or path splits.
- For each new TS, the intended acceleration product is a complete,
  hash-bound GPU path carrying every image structure, predicted energy/force,
  reaction-coordinate value, periodic-branch mapping, model/checkpoint, and
  domain or uncertainty status. The strategy engine reviews this complete path
  rather than selecting a VASP method from one isolated ML saddle candidate.
- After GPU path review, the strategy engine recommends the least-cost VASP
  route that can supply decisive evidence: further active-learning labels and
  a GPU rerun, a bounded ordinary-NEB pilot, ordinary NEB, CI-NEB, a
  VASP-validated local-triad Dimer handoff, or splitting a multi-peak path.
  A complete GPU path may satisfy the parent-path portion of the Dimer gate
  only after its exact local candidate triad has compatible, converged,
  hash-matched VASP static energy/force labels and the configured local force
  agreement or calibrated TS-domain route passes. GPU evidence alone cannot
  authorize VASP or satisfy final Dimer/TS acceptance.
- The VASP/VTST branch is selected separately for every reaction from endpoint
  mapping, periodic continuity, reaction-coordinate resolution, energy/force
  trends, number of peaks, and local three-image geometry. An invalid or
  under-resolved path is rebuilt or densified; a continuous unresolved path
  starts with ordinary non-climbing NEB; a smooth single-peak chain may advance
  to CI-NEB; a reviewed local peak triad may instead be refined by Dimer when
  whole-chain convergence is inefficient; a genuine intermediate or multiple
  peaks require splitting into elementary steps.
- Neither CI-NEB nor Dimer is mandatory. The execution gate must choose the
  next VASP action from current hash-bound evidence, and a lower-priority
  convergence signal cannot override a periodic, geometry, or resolution
  failure.
- A changed checkpoint requires independent held-out validation before it can
  be reused for acceleration. ML predictions remain candidate evidence and
  never replace VASP energies, TS validation, or barrier acceptance.
- Every technically complete adsorption calculation is registered with its
  scheduler, files, convergence, geometry, identity, site, duplicate role,
  energy convention, and scientific status. Accepted A/job9715450 and
  C/job9715455 already satisfy this registry requirement.
- The two completed adsorption calculations named by the user are
  A/job9715450 and C/job9715455. Both are already present in the calculation
  registry with `DONE` status evidence, 14 file records, accepted compatible
  final TOTEN, and three scientific reviews each.
- Independently, every accepted Grade-A TS is atomically registered with its
  compatible IS/TS/FS electronic barrier and transferable method-only strategy
  template. The stored template records the successful evidence-driven branch
  and decision conditions, not a universal fixed sequence.
- Excel promotion remains a separate hash-bound gate. An adsorption row is
  promoted only after its compatible adsorption-energy reference chain is
  complete; a TS row is promoted only after Grade-A validation and an accepted
  compatible barrier. Missing reference energies are never inferred.
- On 2026-08-19 the complete-path implementation was added as
  `scripts/aqcat25_ml_neb.py`. It uses one shared AQCat25 calculator serially
  across every ASE image, ordinary ML-NEB before optional readiness-gated
  ML-CI-NEB, resumable checkpoints, and a review-required complete-path
  manifest. GPU output cannot self-assign the accepted Dimer-parent status;
  `work` must bind an explicit path review through
  `scripts/ts_strategy_engine/ml_neb_path.py`, after which the exact VASP triad
  and local force/domain evidence remain mandatory.

## 2026-08-25 - Route AQCat25 and MatRIS by Calculation Domain

- By explicit user decision, retain both Fe-C-O-H models and assign their
  primary/secondary roles by the calculation domain rather than selecting one
  universal model.
- For adsorption candidate pre-relaxation and geometry ranking, AQCat25 is the
  primary model. MatRIS evaluates the exact same structures as a secondary
  cross-check and disagreement-ranking model; it cannot remove an
  evidence-required motif or override VASP acceptance.
- For transition-state path generation, MatRIS is the primary ML-NEB/optional
  ML-CI model. AQCat25 evaluates the exact fixed MatRIS path as the secondary
  model; it must not independently relax different images for the comparison.
- The routing is supported by the 2026-08-25 same-structure benchmark: AQCat25
  has the lower adsorption force-vector RMSE (`0.0652` versus `0.0962 eV/A`),
  while MatRIS has the lower TS-path force-vector RMSE (`0.0929` versus
  `0.1100 eV/A`) and lower tested TS relative-energy errors. The benchmark
  contains 13 adsorption structures, 21 TS-path structures, and five current
  reaction endpoints, so it supports routing but not a universal accuracy
  claim.
- Cross-model energy comparisons use within-model relative profiles for one
  identical-composition path; raw AQCat25 and MatRIS absolute energies are not
  subtracted. Force disagreement is computed only on identical, hash-bound
  atom-aligned structures.
- AQCat25-MatRIS disagreement is a sampling and review score until disjoint
  VASP labels calibrate it against actual force error. It must not be called
  quantitative uncertainty, and neither model can establish a TS or barrier.
- The exact C2HO*+H* -> C2H2O* internal path currently has endpoint VASP labels
  but no accepted internal-path label set. Its MatRIS-primary route therefore
  remains uncalibrated and must return through work-side geometry, chemistry,
  exact-structure VASP-label, and TS-validation gates.
- This decision approves the routing policy. Production MatRIS-primary ML-NEB,
  temporary internal-coordinate preconditioning, and AQCat25 fixed-path
  secondary wiring remain implementation and smoke-test prerequisites before
  a new GPU path submission.

## 2026-08-26 - Register Reviewed Adsorption Completions Without a Separate Reminder

- A completed VASP adsorption or coadsorption relaxation is registered during
  the same completion workflow after normal termination, electronic
  convergence, ionic/force convergence, compatibility, and chemistry-aware
  final-geometry acceptance have all passed.
- This append-only, idempotent result registration uses the canonical
  `registry-write plan/apply` interface and is durably authorized; it does not
  require the user to request database registration again.
- Failed, incomplete, incompatible, duplicate, or unreviewed calculations keep
  their truthful status and provenance but cannot be marked as accepted
  results.
- Registration of the final VASP structure, `OUTCAR` `TOTEN`, force, and review
  does not create a formal adsorption energy. Reference-state completion and
  Excel promotion remain separate scientific gates.

## 2026-08-26 - Keep Reaction-Held-Out MatRIS Fine-Tunes Experimental

- MZ73 job `1319` tested a predeclared three-fold leave-one-complete-reaction-out
  protocol over all 21 existing TS-path VASP structures. Each fold tuned only
  the MatRIS energy head for 12 epochs against movable-atom VASP forces from
  the other two reactions; no held-out reaction image entered that fold's
  training set and no new VASP calculation was run.
- Aggregate held-out force-vector RMSE improved from `0.09291` to
  `0.08023 eV/A`, P95 improved from `0.17565` to `0.16061 eV/A`, and all three
  held-out reactions improved in RMSE. This is evidence that bounded transfer
  learning can improve force generalization for the tested TS domain.
- The aggregate maximum force error worsened from `0.43609` to
  `0.49474 eV/A`. Force-only tuning also worsened every held-out relative-energy
  RMSE, most strongly for CO dissociation (`0.09095` to `0.21093 eV`). The
  three returned checkpoints therefore remain experimental and are not
  promoted for production ML-NEB, final energies, TS, or barrier use.
- On the exact eight CO-dissociation `NSW=1` structures, the existing VASP/VTST
  job used `4601.021 s` wall time on 128 MPI ranks. MatRIS used a median
  `0.78891 s` for the same eight energy-and-force predictions on one MZ73 GPU,
  or `5832x` warm wall-clock acceleration; including `0.39919 s` model loading
  and the `0.80206 s` cold batch gives `3830x`. These ratios apply only to the
  exact fixed-structure batch and do not waive VASP validation.
- Any next fine-tuning experiment must add a relative-energy-preserving loss
  or replay constraint and keep the same complete-reaction blind-test gate.
  Promotion requires simultaneous force-tail and relative-energy improvement,
  not mean-force improvement alone.

## 2026-08-26 - Require a Complete Dual-Model VASP-Calibrated TS Active-Learning Loop

- A MatRIS/AQCat25 GPU path run by itself is path generation, not active
  learning. Active learning begins only when identical path structures receive
  compatible VASP single-point energies and complete atom-aligned forces and
  both model errors are evaluated separately.
- For TS paths, MatRIS remains the path primary. Prefer a real committee of
  three to five independently trained and accepted checkpoints of the same
  MatRIS architecture; AQCat25 is an optional exact-structure external auditor,
  never a MatRIS committee member. Until the committee passes disjoint VASP
  calibration, disagreement is ranking evidence rather than quantitative
  uncertainty. If fewer than three accepted MatRIS checkpoints exist, fall
  back to MatRIS plus optional AQCat25 audit and actual VASP error.
- Sampling preserves the last geometry-valid point and first geometry-valid
  failure point, then ranks committee force/relative-energy disagreement,
  descriptor novelty, TS proximity, failure proximity, and reaction-coordinate
  backtracking. Select a clustered, deduplicated set of at most seven that also
  covers TS-like and rising/falling regions. Peak neighbors are not universal
  labels; the exact peak triad belongs to VASP refinement or the Dimer gate.
- With a real committee, use the disagreement-versus-VASP-error four-quadrant
  decision. Low-disagreement/high-error points are blind spots and mandatory
  training targets; high-disagreement/low-error points primarily calibrate
  conservatism. Geometry-invalid paths and VASP-invalid labels never enter
  training.
- A failed MatRIS VASP screen requires energy-and-force-aware fine-tuning with
  prior-TS and adsorption replay. A new checkpoint must have a different hash,
  rerun the complete path, preserve force tails and relative-energy profiles,
  and pass a disjoint VASP TS held-out set before the workflow may report
  `active-learning acceleration calibrated`.
- GPU-to-VASP automatic submission remains forbidden. Each bounded VASP label
  batch requires work-side review and explicit authority; model calibration
  does not replace the NEB/Dimer/frequency/final-barrier scientific gates.
  Geometry classification, snapshot preservation, prediction/committee request
  preparation, scoring, clustering, VASP-package preparation, post-return error
  assessment, and next-stage package preparation run automatically when the
  active-learning trigger passes.

## 2026-08-27 - Keep DIMER Bidirectional Connectivity Diagnostic

- DIMER Grade A acceptance requires technical DIMER acceptance plus a validated
  reaction-coordinate vibrational mode; bidirectional downhill connectivity is
  optional diagnostic evidence and is not a DIMER TS-acceptance gate.
- NEB and CI-NEB retain their existing bidirectional-connectivity policy. This
  correction does not relax their source-method validation requirements.
- `configs/execution_backends.yaml` now expresses the source-method distinction
  explicitly, and the runtime contract loader rejects attempts to restore
  bidirectional connectivity as a DIMER Grade A hard requirement.

## 2026-08-28 - Backfill Step 12A and Audit Workflow-Status Corrections

- Register the 23 missing Step 12A adsorption relaxations from hash-audited
  remote VASP files; retain the existing CO/top record and never infer expired
  LSF job IDs or scheduler terminal states.
- Accept compatible final relaxation `TOTEN` only for the 18 new unique final
  structures. Keep five duplicate final-site relaxations as provenance-only;
  missing reference tuples continue to block adsorption energies and Excel
  promotion.
- Route mutable `calculations.workflow_status` corrections through the
  hash-bound registry gateway. Each change must name its expected old status
  and append an immutable `calculation_workflow_status_history` row in the same
  transaction.
- Correct the accepted CH+H frequency record and accepted C+H DIMER/frequency
  records to `energy_accepted`; their Grade-A validations and formal barriers
  were already present and unchanged.

## 2026-08-28 - Complete Step 12A Direct Gas/Atomic Reference Tuple

- Use one directly calculated isolated reference for each Step 12A adsorbate:
  closed-shell CO and H2O, doublet H and OH, and triplet O and C. All use the
  locked PBE/PAW-PBE/`ENCUT=400 eV`, cubic `20 A`, Gamma-only,
  `ISMEAR=0`/`SIGMA=0.05 eV` gas branch with explicit open-shell `NUPDOWN`
  where required.
- Define the electronic adsorption energy as
  `Eads=E(Fe45+X)-E(Fe45)-E(X_gas/atom)`; negative is exothermic. Surface terms
  use `fe110_converged_toten_sigma0p20_v1`. Do not mix this direct-reference
  dataset with a stable-molecule chemical-potential cycle without creating a
  separately named convention and recomputing every affected value.
- Accept 19 unique Step 12A adsorption energies only after every adsorbed,
  clean-slab, and gas/atomic term passes its owning convergence, geometry,
  spin, and compatibility gates. Retain five migrated final-site duplicates as
  provenance-only.
- Treat scheduler `DONE` as insufficient evidence: OH job `9733113` had a
  truncated final OUTCAR and was rejected for energy use. Same-method
  continuation `9733121` from its final CONTCAR supplied the accepted OH
  reference without changing the INCAR method.

## 2026-08-28 - Promote the 19 Unique Step 12A Adsorption Energies

- Keep the canonical adsorption workbook as one eight-column worksheet and
  retain every existing data row. Reuse its legacy H column for the formal
  electronic adsorption energy because adding a second workbook, sheet, or
  column would violate the active adsorption-table contract.
- Rename H to `吸附能 Eads (eV)`, remove the superseded same-species relative
  values, and populate only the 19 registry-accepted unique Step 12A states.
  The five duplicate final states remain blank rather than receiving copied or
  independently reportable adsorption energies.
- Use a hash-bound existing-row promotion: A-G must match the reviewed workbook
  values before H is written from an
  `accepted_compatible_adsorption_energy` registry result. Record one SQLite
  and JSON receipt per row, then append an immutable
  `energy_accepted -> excel_promoted` workflow-status change.
- Preserve the pre-promotion workbook and database as safety backups. No VASP
  calculation, scheduler operation, or scientific energy convention changes.

## 2026-09-01 - Active-Learning-First Review for Eligible GPU TS Failures

- Correct the failure-response ordering: do not route an eligible GPU
  TS/path failure directly to VASP micro-NEB without first presenting both the
  active-learning diagnostic and direct VASP choices.
- Prefer active-learning diagnosis when a hash-bound geometry-valid reference
  and first persisted failure boundary pass
  `configs/dual_model_ts_active_learning.yaml`. Use exact-structure MatRIS,
  AQCat25, and compatible VASP static energy/force evidence to decide whether
  MatRIS needs fine-tuning.
- A MatRIS VASP-error failure prepares replay fine-tuning and a
  new-checkpoint complete-path rerun. A MatRIS pass retains the checkpoint and
  routes to path repair or local VASP micro-NEB. No branch receives submission
  authority from this decision alone.

## 2026-09-04 - Make the Ordinary-NEB Pilot Optional

- By explicit user decision, remove the universal one-step same-path pilot
  prerequisite from ordinary-NEB submission. A reviewed path may proceed
  directly through ordinary-NEB preflight, authorization, and the authoritative
  execution gate.
- Retain `neb_pilot` as an optional diagnostic selected only for unresolved
  runtime, electronic, magnetic, restart, parallel-layout, or immediate-
  geometry risk. Do not insert it automatically into every NEB workflow.
- If a formal bundle includes `neb_pilot_result.json`, continue to validate its
  live scheduler, exact-path, electronic-input, and file-hash bindings. Invalid
  supplied pilot evidence remains a preflight failure; missing pilot evidence
  is not a failure.

## 2026-09-05 - Add Reviewed Rough-Path Local Sella Entry

- By explicit user request, add a separate entry from a saved, geometry-valid
  rough MatRIS path. Global NEB convergence and a global single peak are not
  prerequisites for this optional entry; each bounded request requires its
  own reviewed local segment and one strict local peak.
- Keep the original automatic converged-single-peak Sella branch and all
  geometry, work review, VASP, checkpoint promotion and TS acceptance gates.
  Save failure states and valid iterates; a new checkpoint requires renewed
  segment review. No remote search, training, VASP change or Git publication
  is authorized by this engineering change.
- Entry and limitations: `modules/transition_state_search/SELLA_LOCAL_PEAK.md`.

## 2026-09-06 - Automatic Local Closeout for Failed VASP TS Paths

- After a completed VASP NEB/CI-NEB path fails convergence or geometry review,
  automatically collect its bounded evidence, register the hash-bound failed
  strategy attempt and outcome, and block exact-input retries without waiting
  for another user reminder.
- If an exact final structure can be paired with its VASP force block, compare
  MatRIS and optional AQCat25 predictions on that same structure. Do not infer
  model error from NEB failure alone. A MatRIS error-screen failure prepares
  training-eligible static labels; a pass retains the checkpoint and prepares
  path repair or local VASP refinement.
- The automatic scope ends after local preparation, validation, and a fresh
  execution gate. Remote GPU/VASP submission, fine-tuning, NEB/Dimer/frequency
  execution, and final scientific acceptance remain explicit authorized
  actions.

## 2026-10-21 — Fe110 REICO pilot300 scope

- User selected the existing Fe(110) adsorption domain, approximately 300 deduplicated atomic configurations for a proposal, and conditional later expansion to thousands after a good C2/C3 speedup result. This is proposal-preparation authority only.
- Method proposal: random adsorbate configurations on fixed Fe45, bounded optimization-trajectory sampling, surface-aware deduplication, compatible DFT single-point energy/force labels and conservative NequIP A/B training. Numeric quotas, timing caps and the draft 20% per-group VASP core-hour signal are proposed values, not approved execution or scientific gates.
- Existing raw candidates/labels and observed heldout exclusions remain intact. Historical C3H2O candidate08 fragmentation is not an intact-C3 reference. No calculation was run and no acceleration established.
- Evidence and outstanding preflights: `docs/reviews/fe110_reico_pilot300_20261021/README.md`, `pilot_spec.json`, `source_inventory.json`.

## 2026-10-22 - Fe110 REICO CPU geometry pilot

- Direct user authority covers the first local random-generation step and replacement of the uniform1.5A cutoff with pairwise draft collision guards. It does not authorize GPU,DFT or training.
- Preserve the verified Fe45 slab/cell/order and18 fixed bottom Fe; randomize C/O/H coordinates. Config configs/fe110_reico_pilot/geometry_v1.json is the sole numeric generation specification. These are off-equilibrium training environments,not accepted adsorption minima or fixed molecular identities.
- Freeze100 trajectory families and partitions before generation; cap20 attempts per family. Retain99 candidates and the failed C3 training family without padding; later3-frame-per-family cap implies at most297 selected frames from this pool.
- Record raw coordinates/rejections and immutable hashes. Basic distance checks do not establish model-domain validity,SCF/magnetic convergence,stability,final symmetry/SOAP deduplication or measured acceleration.
- Review: docs/reviews/fe110_reico_geometry_step1_20261022/README.md and geometry_review.json.

## 2026-10-22 - DFT-reference-first random-sampling pilot

- User accepted executing the preceding DFT-reference-first recommendation. Scope concretized as six exact-geometry static probes,threeC2/threeC3,within the original300-label pilot. This stage binds six jobs;Remaining new-configuration label cap is294,not an authorized next batch.
- Geometry-only composition/contact-quantile selection uses training families exclusively;no independent final-test or full-domain validation claim. Preserve the original coordinates,ISPIN2 magnetic initialization and active SIGMA0.20/TOTEN branch;require electronic/coordinate/force/magnetic checks before label admission.
- Six successful canonical submissions and scheduler evidence recorded;registry150 INSERT/zeroUPDATE includes jobs/provenance only,not accepted energies or adsorption states. Existing VASP jobs,checkpoints and production method remain unchanged.
- No ML optimization is needed to establish these references. Exact frozen-model predictions are prepared only;model-domain suitability and any later DFT short-optimization/training package depend on the measured forces.
- Evidence: docs/reviews/fe110_reico_probe6_20261022/README.md,input_review.json,execution_status.json,user_authorization.md.

## 2026-10-22 - Six random-probe force comparison

- User requested completion,SCF/magnetic review and exact frozen-model force comparison. Six statics passed normal/electronic/coordinate/raw-force checks;12 CUDA predictions completed on unchanged checkpoints,without relaxation/training/new VASP.
- Six-probe adsorbate vectorRMSE is0.28461eV/A(original) and0.27165eV/A(control),zero reversed adsorbate forces. Overall improvement4.55%;C2 combined RMSE essentially unchanged. This supports a bounded short-trajectory sampling trial recommendation,not measured acceleration or production promotion.
- Magnetic moments are complete and all Fe local moments positive;no multi-initial-state magnetic ground-state proof. Six training-domain probes are not an independent test or full99-family validation. Next suggested six-seed10-20-step trial remains unexecuted;no automatic expansion beyond the existing300-label cap.
- Evidence: docs/reviews/fe110_reico_probe6_20261022/force_review.md and force_review.json.

## 2026-10-22 - Six-family bounded ML sampling

- User approved continuing the short sampling pilot. Reused the six reviewed local train-family seeds and frozen control cfcac123...1e523;LBFGS at most20steps,maxstep0.05A,ML fmax0.10eV/A,with unchanged Fe45 order/cell and18fixed Fe. No new external motif or production-method change.
- Actual CUDA producer exit0;5cases20steps,0052guard stop at8 with C-Fe1.594649A below draft1.60A. Retain114frames,113within guards,107newunlabeled. Boundary failure is preserved and does not prove DFT invalidity. 0007model fmax rises3.960to4.479eV/A;no converged geometry or measured acceleration claim.
- Six predetermined-family sampled frames prepared for DFT,including0052last-valid7;canonical static andINCAR checks PASS. No newDFT/training submitted;exact six-job submission approval is pending separately.
- Evidence: docs/reviews/fe110_reico_sampling6_20261022/. All trajectory frames stay in train;no automatic99-family/300-label expansion.

## 2026-10-22 - Six sampled-frame DFT submissions

- User replied “可以” to the concrete six-new-frame submission scope. Frozen sampled inputs,source hashes,remote POTCARs and six execution decisions verified;canonical executor returned LSF9919076-9919081,32cores each. First exact scheduler check at11:35:30-31Z is PEND for all six. No retry,training,additional sampling or protocol change.
- Preserve original batch_request.json as the prepared snapshot;submission_summary.json and per-case receipts establish actual submissions. Registry plan b3e78865b8075c2c7e34cf3e53c1c244ce36366823d93c91f4c1fdceb5e70b28 applied:151 INSERT,zero UPDATE,only calculation/job/status/file provenance.
- Require normal termination,SCF,coordinate/raw-force and total/local-moment checks before using labels;fixed-geometry statics do not require ionic convergence. Compare exact-coordinate frozen-model forces before any sampling expansion;12/300 configurations only if all six new labels qualify.
- Evidence: docs/reviews/fe110_reico_sampling6_20261022/dft_submission_status.json and dft_submission_authorization.md. Managed state sync remains blocked by the existing PKG-INFO classification hash conflict.

## 2026-10-22 — Collect off-equilibrium data before judging the new model

- User explicitly rejected old-model minimum/convergence accuracy as a prerequisite for gathering data and replied“可以的继续”. Execute bounded geometry-only sampling and selection;keep high-force/nonconverged/changed-connectivity candidates,subject to existing draft geometry/numeric safety guards. Require electronic rather than ionic convergence for later DFT single-point labels.
- Freeze original99-family partitions. Reuse6completed trajectories;run only remaining93 with the same control checkpoint and20step/0.05A bounds. Actual process exits0;preserve all1995frames and7guard boundaries. Do not promote prediction/stability/acceleration claims.
- Select up to3perfamily using frozen0.10A vector RMSD,XY periodicity/equal-element matching and movableFe context;no model-energy/error/convergence filtering. Final292frames include12existinglabels;280newcompatible32corestatic inputs prepared only. New DFT submission scope and training resources remain separate concrete execution decisions.
- Source registry transaction aa5043371bf7dc3ca3c348ba3905807d5fd31493bf7b79fc5f66664aff70d1a1 applied:1549INSERT/6workflowupdates;no newjobs or accepted science results. Current evidence:docs/reviews/fe110_reico_sampling93_20261022/.

## 2026-10-23 — Authorized280 statics;204 submitted before server rejection

- User explicitly selected“分批提交全部280个（推荐）”after disclosure of32cores/job,128accountcores and rough4433-7272allocatedcorehours. Bind all280 to frozen batch117bdce2fdbd2220a48412976db7e1a295151b1ff0b48c7a869a47dff2f6ec08;reuse12labels. No parameter change,extra structure or new training.
- All280canonical input/gates pass. Canonical executor returned204unique matching receipts. Exact account recheck at2026-10-22T16:36:22Z:3RUN/201PEND,96runningcores;new scientific outputs unreviewed.
- Server esub refused6requests for too many jobs;another SSH submission timed out after300s. Preserve all7unknown reservations/receipts. No additional matching recent/active job or submission process observed;one timeout outcome remains unconfirmed. Exact configured job-count threshold needs confirmation.
- Remaining76=69untouched+7requiring recovery review. Keep original280authority;confirm current server submission allowance and reconcile reservations before supplementing only unsubmitted inputs. No automatic retry/background supplement and no existing calculation stopped.
- Reviewed registry plan da03fe0318c435ea956ee810f64bf2d5e1dd1c8fe8652a04ee01fad5093941a1 applied:3881INSERT/0UPDATE,204real jobs and provenance only;zero accepted results. Evidence:docs/reviews/fe110_reico_sampling93_20261022/dft_submission_status.json.

## 2026-10-23 - Reuse six late10_B frames as an isolated legacy force supplement

- User requested extraction,per-frameSCF/magnetism and isolation checks before admission;no newDFT.Closed job9848812 steps264/272/280/288/295/296 all pass source/raw-force/SCF/intactC2H3 checks and full clean-face symmetry/equal-element isolation;4fmax<=0.05eV/A.
- Retain6as LEGACY_TOTAL_MAGNETIZATION_ONLY force-only supplement under the existing20261019 trajectory review scope.TotalM105.9810-105.9993muB,maxadjacentlatechange0.0034muB;localFe moment signs and magneticgroundstate unverified.No claim of local-moment-complete newstatic QC or energy-training admission.
- Keep10_Awhole-job heldout and every frozen package unchanged;future combined package must preserve job isolation and this review tier.NoDFT/GPU/training/modelpromotion or pausedC3 restart.
- Evidence:docs/reviews/fe110_10b_lowforce_20261023/README.md;6real frames independently verified and replayed identically in the release checkout.

## 2026-10-23 - Assemble combined force data only; do not train

- User explicitly requested a new package including6late10_B frames while preserving partitions and magnetic grades,and prohibited training;later continue did not lift that limit.
- Freeze reviewed137random statics plus legacy248/60/46 and16quarantined observed-heldout sources.New v2data package:366train(248+112+6),78dev(60+18),53heldout(46+7),16quarantined.No sample repartitioned;48894applicable real-surface-symmetry/permutation checks against513reserved geometries found0conflicts.
- Keep force-only objective and existing uniform-control frame/atom recipe;renormalize train sampling to1/366.Preserve legacy source review grade,positive-localFe static grade,and10_B LEGACY_TOTAL_MAGNETIZATION_ONLY in manifest andDBs.No energy-training or magneticgroundstate acceptance.
- Native source and444DBrow integrity checks pass,including release adapters;51primary/44release tests pass.Original frozen packages/checkpoints unchanged;no heldoutDB,model/configuration execution request,GPU,DFT or training.No automatic submission or modelpromotion.
- V1failed only at final coverage-summary legacy-family mapping;all original data and failure/source snapshots retained.V2is successful and inventory-bound.Next prepare a bounded experiment design and resource budget before separate runtime authority.
- Evidence:docs/reviews/fe110_combined_force_package_20261023/README.md.

## 2026-10-23 - Joint coverage of the frozen366 training frames

- User authorized existing-data composition/local-environment/force audit only.Fixed original233SOAP thresholds;training-only366labels and1597random traingeometries;254local descriptors added,original caches immutable.
- Current296missing contact-joint types include109fillable by original selected inputs;121trainselected labels remain outside package.Conditional all121pass review:187residual groups,75with all-cutoff missing examples;SOAP451to1is conditional geometry coverage,not actual admission/model improvement.
- C2H3lowforce4frames are1job/1joint type;C3H2O54frames havefmax>=0.659eV/A.No newrandom DFT budget supported now;first review existing selected labels,then address task-relevant low/mid-force gaps if separately authorized.No fixed supplemental count.
- Keep all366samples/weights/partitions/magnetic grades;1043near-pair comparisons show realforcevariation,including24pairs below0.10Awithadsorbate deltaRMSE>1eV/A.Independent counts,freshSOAP,18permutationpairs and conditional sets pass;33tests pass in each checkout.No training/newDFT/GPU or pausedC3 restart.
- Evidence:docs/reviews/fe110_joint_coverage_20261023/README.md;current local output joint_coverage_20261023_v3.

## 2026-10-24 - Recover existing selected labels before supplemental DFT

- User authorized collection/QC and a small targeted candidate list only.No newDFT/training or pausedC3 restart.InitialSSH/TCP failure retained;after user restored connectivity,query79exact outstanding success-receipt jobs once:19DONE/4RUN/56PEND at00:10:48Beijing.65of121unadmitted traininputs lack successful receipts;not treated as pendingjobs.
- Collect114source files for19DONE results;all19staticSCF/rawforce/localFe-moment QC PASS(12train/2dev/5test).Total selectedlabels156PASS(124train/20dev/12test);reserved physicalQC never enters adaptive coverage.12newtrain labels pass1824full-symmetry comparisons against513reserved geometries.
- Auditview378labels reducesjoint gaps296to284 andfixed-prior-thresholdSOAP gaps451to366;original366trainingpackage/weights/partitions/magneticgrades unchanged.C3H2O59stillno fmax<=0.05;C2H3fourlowforce labelsstill1source/type.
- Keep05/07C3prepared sources paused as priority lowforce-source proposals;family0039step006 and0086step014 remain force-unknown geometry backups,isolated in280comparisons.No immediate newrandom high-energy DFT recommendation;first consume44existingRUN/PEND trainingjobs when complete.Neither187conditional gaptypes nor2backups imply a DFT budget.
- 42tests pass in eachcheckout;19real staticlabels replay identically in each;378force-bin/directset counts and4candidate hashes pass.Evidence:docs/reviews/fe110_reico_followup_20261024/README.md.

## 2026-10-24 - Complete original selected static submissions

- User authorized the remaining original batch,then explicitly confirmed "确认16份无重复，提交新尝试" for exact recovery proposal2bf820480302be93c320bbd2311b57fc775bc925722a522ff39411c3c3363779.
- Continue69never-reserved inputs:60successes,9SSH-unknown outcomes;combine9with prior7for16fresh canonical directory attempts after human confirmation.Preserve old markers/records/locks,original scientific inputs,32cores/job and128account slots.
- Actual new76success receipts complete280unique logical jobs(264original+16fresh);12reused labels remain separate.At15:07:51Beijing:new7613DONE/4RUN/59PEND.Scientific output QC pending;no training/pausedC3 execution.
- Reviewed exact registry plan58e4f8991b1bf639a24c8c77dd151dbad9ce20813b2197fb2fd043096f295857 and applied1453INSERT/0UPDATE,status/provenance only.Evidence:docs/reviews/fe110_reico_remaining_20261024/README.md.

## 2026-10-24 - Batch review completed original static labels

- Explicit user request:对已经结束的开始分批处理.Use280receipt directory map(including16fresh attempts),skip156reviewed labels,and freeze136job query at16:48:16Beijing:84DONE/4RUN/48PEND.Collect/QC84in20/20/20/20/4batches after one-case smoke.
- Native static scientific thresholds unchanged:82PASS(62train/7dev/13test);family0028step000 requires localFe-moment review;family0086step000 hits200of200SCF boundary despite OUTCAR EDIFF marker.Both remain excluded,no auto retry or tuning.
- Cumulative240reviewed/238PASS.62newtrain labels pass9018full-symmetry comparisons against513reserved geometries,zero conflicts;none has movable fmax<=0.05eV/A.Keep366trainingpackage/378auditview and all magnetic grades/partitions unchanged;no model/newDFT execution or jointSOAP update.
- Review/apply registry plan7c0a9ede646f26815ea1841d89c9424f0384ae7b9279471f291c473a1acb6f18:765native INSERT,71DONEprojection UPDATE with immutable history;no accepted energies/endpoints.43related tests pass per checkout.Evidence:docs/reviews/fe110_completed_label_qc_20261024/README.md.

## 2026-10-24 - Refresh joint coverage using isolated PASS training labels

- User explicitly authorized composition/local-environment/force coverage update.Extend only prior378auditwith62isolatedPASS trainlabels,retaining all original rows,magnetic grades and partitions;440referenceframes,1597training queries.No newdescriptors,threshold fitting,training DB mutation,GPU or DFT.
- Keep originalSOAP composition/element p95,threecontact scales andforcebins.Jointmissing284to229;SOAPthreshold-exceeding366to68.C2H3SOAP0still40discrete gaps;neither metric proves modelprecision.
- Separate229remaining groups:40canbe addressed by45unreviewed original traininglabels,2only by currently quarantined selectedlabels,187have no originalselected representative.Conditionally admitting45afterQC leaves189types;do not retain old187projection that assumes bothquarantinespass.No unknown DFTforce is imputed.
- C3H2O84trainlabels stilllackfmax<=0.05(min0.659006);C2H3fourlowforce labels stillonejob/type under total-onlymagnetic grade.32tests plus440rawforce-bin counts and8cachedSOAPdistance checks pass in eachcheckout.Evidence:docs/reviews/fe110_joint_update_20261024/README.md.

## 2026-10-24 - Review remaining45 gap-linked original training inputs

- User explicitly authorized the45unreviewed original training inputs linkedto40joint gaps.Exclude development/final-test and both oldquarantines.Query exact45once at20:00:51Beijing:16DONE/3RUN/26PEND;no submissions or livejob changes.
- Prefer one DONErepresentative per gap,then retain all remaining DONElabels;16collected/QCPASS,16isolated against513reserved geometries in2557comparisons,zero conflicts.Existing scientific rules and magnetic grades unchanged.
- New16candidates can fill13of40groups(C2HO1/C2H2O9/C3H2O3);27pending-linked groups remain.Cumulative256reviewed/254PASS,202train/27dev/25test.No newlowforce.Candidates not merged into440audit or366package;229to216is conditional contribution,not re-computed SOAP.
- Native registry plan140ee18e840621c83a5631d3912d49c099e62a0811a5d923a28d24bd10cc7b4e reviewed/applied:153INSERT,16DONEprojectionUPDATE with immutable histories;no accepted endpoints or reported energies.45tests and16real-label replays pass percheckout.Evidence:docs/reviews/fe110_train45_review_20261024/README.md.

## 2026-10-24 - Recover completed results from the remaining29 training jobs

- User requested continuation of exact29 unreviewed original training submissions;query once at20:34:06Beijing:1DONE/4RUN/24PEND.Recover only job9921426 family0076step010,C3H2O;SCF73/200,45positiveFe local moments,native staticQC PASS;210applicable full-symmetry comparisons against513reserved geometries,zero conflicts.
- Cumulative257reviewed/255PASS(203train/27dev/25test),two earlier quarantines preserved.New1could fillone additional type;prior16+new1could cover14of40pending-linked types,conditional jointgaps229to215,26pending-linked types remain.No SOAPrecompute/package merge/newDFT/training or pausedC3restart;fmax4.990634eV/A does not supply a lowforce source.
- Review/apply native registry plan75ab30d55691487bc122dc623958d223b061f77e3daafcb7d0baca4d748e306e:18INSERT(17files+1status),1DONEprojectionUPDATE with immutable history,no accepted results.49tests andone real-label replay pass percheckout.Evidence:docs/reviews/fe110_train29_review_20261024/README.md.

## 2026-10-24 - Recover completed results from the remaining28 training jobs

- Exact28 query at21:36:25Beijing:5DONE/3RUN/20PEND.All5C3H2Olabels collected/nativeQCPASS,SCF60-77/200steps,45positiveFe local moments each;1050applicable symmetry comparisons against513reserved geometries,zero conflicts.
- Five candidates add4types;family0076step020 shares an already-covered type and is not counted twice.Prior17+new5could cover18of40pending-linked types,conditional229to211gaps;22pending-linked types remain.Cumulative262reviewed/260PASS(208train/27dev/25test);two oldquarantines preserved.No lowforce/SOAPrecompute/package merge/newDFT/training or pausedC3restart.
- Native plan617419e9078dcb1e05d356419502d4262bf6d48e6bb1d3cd2d5e7af2d561bb12 reviewed/applied:54INSERT(49files+5statuses),5DONEprojectionUPDATE with immutable history,no accepted results.52tests and5real-label replays pass percheckout.Evidence:docs/reviews/fe110_train28_review_20261024/README.md.

## 2026-10-25 - Complete final30 original-label QC

- User requested审核 after exact30DONE snapshot at10:56:42Beijing.Reuse its original bytes and native receipts;one-case smoke then20/10batches.All30nativeQCPASS(train23/dev3/test4),SCF59-105/200,45positiveFe local moments each.Train23isolated in4270comparisons against513reserved geometries,zero conflicts;reserved forces/energies never used for training coverage.
- All292selected labels now reviewed,290PASS(train231/dev30/test29),two oldquarantines preserved.Final23add22types;all45post-audit candidates could cover40pending-linked types,conditional229to189gaps(2quarantine-only+187unselected).No lowforce addition,SOAPrecompute,366package/440audit mutation,newDFT,GPU,training or pausedC3restart.
- Native registry plan96d191144635868a8c5cae6865b2daff6c12aab4bc862912dd77193b588dde72 reviewed/applied:279INSERT(249files+30statuses),30DONEprojectionUPDATE with immutable history;no accepted results.55tests and30native real-label replays pass percheckout;180raw/90input hashes match.Evidence:docs/reviews/fe110_final30_qc_20261025/README.md.

## 2026-10-25 - Refresh complete eligible-training joint coverage

- User authorized training-only coverage update with unchanged isolation/magnetic grades and no training.Combine45PASS candidates from16/1/5/23batches with prior440;reuse4hash-bound isolation audits(8087prior comparisons,513reserved geometries,0conflicts),preserve prior440exactly and new45force/moment grades.New485auditview is not a training package;original366package remains frozen.
- Against1597training-pool frames,fixed forcebins/radius scales/SOAPthresholds give189missing jointtypes(vs229),187unselected+2quarantine-only;no unreviewed selectedtrain labels.SOAPexceeding frames68to4,threefromfamily0028 with step000magnetic quarantine.C3H2O113stillminfmax0.659006/no<=0.05;C2H3lowforce4stillonejob/type under unchanged total-only magnetic grade.
- Reuse1851bound cached descriptors,0newdescriptors.Eachcheckout43tests PASS/1DScribe-dependent skip;485raw-force bins and8SOAPdistance examples independently verified.No heldout force/energy use,newDFT,GPU,training or pausedC3restart.Residual189types are diagnostics,not a DFT budget.Evidence:docs/reviews/fe110_joint_update_20261025/README.md.

## 2026-10-25 - Prepare a small targeted supplement shortlist

- User requested a few candidates with a reason for each before deciding label count.Select existing labelled connected target-graph sources0099step020(C3,3.312794eV/A)and0023step020(C2H3,2.116751eV/A,outside10_B);initial single-points already exist.Future lowforce sampling requires separately authorized optimization,not duplicate single-points.C3minimum0.659006 frame is4components;do not call it an intact C3 anchor.
- Add existing0028step000magnetic review(Fe40=-0.953muB,SCF83)without admitting/changing its grade.Conditional backups:paused07C3graph absent in485train/1597pool,and0028step002off-equilibrium geometry.No newlabels,DFT,inputs,training or paused-source execution;label count remains undetermined.
- Five direct geometry checks and910native reserved comparisons against513geometries pass,zero conflicts;source splits/magnetic grades preserved.40tests and5independent geometry replays pass percheckout.Initial replay path-alias mismatch resolved by identical original-geometry SHA256 and equality of all numerical/structural fields;failure record retained.Evidence:docs/reviews/fe110_targeted_shortlist_20261025/README.md.

## 2026-10-25 - Reduce189gaps to a bounded representative proposal

- User approved grouping and prioritizing all189types before deciding label count;no calculation execution authorized.187unselected types become138greedy complete-link SOAP clusters with exact composition/graph boundaries and unchanged per-element internal thresholds;2oldquarantine types remain separate.
- Propose12connected/persistent-cluster representatives(C2HO3/C2H2O3/C2H31/C3H2O5),2SOAP-only reserves and2already-labelled optimization sources.12clusters involve17originaltypes approximately;124clusters/167types deferred,not declared covered.Each new single-point labels only its actual geometry;minimum/sufficient budget and force equivalence unproven.
- 189unique dispositions,138cluster diameter checks,16independent native geometry audits and2384reserved comparisons pass;5direct tests percheckout and6scientific outputs identical between code copies.First publication replay cwd failure preserved;rerun publication code from evidence cwd succeeds without changing bindings.Original485audit/366package/splits/magnetic tiers and paused05/07 remain unchanged.No newDFT/GPU/training or executable inputs.Evidence:docs/reviews/fe110_grouped_supplement_20261025/README.md.

## 2026-10-25 - Prepare exact12single-point and2optimization inputs without execution

- User approved local input preparation and resource estimates for the grouped shortlist.Reuse exact reviewed POSCAR bytes and canonical builders:12NSW0statics plus2screening-stageNSW80optimizations,32cores each,LORBIT11,unchangedPBE/400eV/Gamma551/SIGMA0.20/Fe2.2magnetic initialization.2reserves unprepared;old05/07paused unchanged.
- Both template smoke cases and all14native preflights/Custodian reviews pass;all14geometry hashes preserved.Primary25/publication21related tests pass;different baseline suite counts reported separately.SourcePOTCAR metadata was read-only verified after initial SSH timeout/freshconnection diagnosis;no POTCARcontents copied or taskinputs uploaded.
- Six matched static elapsed records imply219.98-287.35coreh for12;two historic80-step C3runs imply647.80-735.40coreh for2optimizations,with documented composition/NPAR/LORBIT differences.Total867.78-1022.75coreh is an analogy envelope,not a cap or calibrated interval;currency price unknown.OUTCAR-tail step-count rejection preserved and corrected using hashed continuous OSZICAR1..80summaries.
- No execution authorization/gate,submission,continuation,training or scientific-result admission.TargetPOTCAR andlivequota checks remain mandatory after exact expensive submission scope is confirmed.Evidence:docs/reviews/fe110_grouped_inputs_20261025/README.md.

## 2026-10-25 - Submit exact14grouped supplement jobs and register provenance

- User replied1提交 to the exact14job/cost question;freeze the human quote and12+2scope in user_authorization.md.Recheck unchanged72input files,livePAW_PBE species/SHA,runtime,MAX128account and14fresh directories;native gate/executor used once percase.12statics jobs9922611-9922622 and2NSW80optimizations9922624/9922625 now have14successful receipts;no unknown attempt/retry.
- Exact-ID LSF snapshot23:44:46Beijing has2RUN/12PEND;separate scheduler state from SCF/ionic/geometry/magnetic/scientific validity.No additional reserves,paused05/07sources,continuation or training.14input hash/native receipt checks PASS;old485audit/366package/splits/magnetic tiers unchanged.
- Reviewed canonical metadata-only registry plan ad6d8b1e028bc4b3844605012c8fc4c673a156993c5fbf369ad57f52e18e77cd applied288INSERT/0UPDATE:14calc/14job/14status/246files,including14remote-only licensed POTCAR metadata rows.All288rows read back;0scientific result rows.Initial readback CLI-vs-canonical receipt key mismatch retained and corrected without repeating apply.
- Primary119related gate/submission/scheduler tests and publication4new task tests pass;syntax/Ruff pass.Submission authority consumed;next user-requested checkpoint may recover completed labels/optimizationframes for native QC without auto-training.Evidence:docs/reviews/fe110_grouped_submission_20261025/README.md.

## 2026-10-26 - Review grouped14 labels without requiring parent relaxation convergence

The user authorized recovery and SCF/local-moment/coordinate-force audit only, with no continuation or training. Audit all160 ionic frames independently; parent NSW80 termination is not force-label rejection or endpoint acceptance. Retain171/172physical labels, exclude0021step004 atNELM200, and exclude2already-labelled starts from169candidate rows. Propose27first-round additions (11statics and8per trajectory), keep142backup, preserve513reserved geometries and all magnetic tiers. No newtraining package, model execution, retry, accepted energy or endpoint. Evidence: docs/reviews/fe110_grouped_qc_20261026/README.md and checkpoint_v3.json.

## 2026-10-27 - Assemble the complete512-frame force dataset without training

The user explicitly chose485reviewed training frames+27recommended frames. Build a new local package from original366+119previously reviewed statics+27recommendations;keep78development/53heldout/16observed-heldout quarantine identities,order,physical labels and magnetic tiers. Preserve the existing force-only uniform policy,renormalizing train probabilities to1/512. Reuse hash-bound source isolation proofs with unchanged geometry bytes. No newDFT/GPU/continuation,heldout loader,executable training request,checkpoint selection or model promotion. New source/ASE dataset verification passed659/590rows;original366package and485audit remain immutable. Next update jointcoverage separately. Evidence: docs/reviews/fe110_force_package_20261027/README.md.

## 2026-10-27 - Check512-frame jointcoverage and prepare one bounded C3continuation

Keep the512-frame package immutable while auditing only training geometry and qualified training labels with fixed485-view SOAP thresholds,contact cutoffs and force bins. Jointtype gaps189to178 and SOAPoutliers4 do not prescribe178newDFT jobs or prove acceleration. C3H2O has no<=0.05eV/A frame. Prepare one continuation from9922624CONTCAR,32cores/maximum300additional ionicsteps,unchangedEDIFFG-0.02 and other physical settings;NSW80to300 only. Existing80step authorization does not cover this new budget,so request explicit cost confirmation before execution. Historical full-cap reference1526-2595corehours/48-81hours plusqueue is not a cap;no automatic continuation. No upload,submission,training or magnetic-tier promotion. Evidence:docs/reviews/fe110_joint_update512_20261027/README.md and docs/reviews/fe110_c3_continuation_20261027/README.md.

## 2026-10-27 - Submit exactly one authorized C3continuation

After the new300step/32core budget was presented,the user replied 提交. Preserve the frozen preparation and512frame package;create a same-name execution copy with identical bundle bytes and fresh source/account/runtime/POTCAR/target checks. A new canonicalSUBMIT_VASP gate and executor produced exactly one successful receipt9924387. FirstexactIDquery is PEND at04:34:19UTC,not a convergence or scientific-acceptance claim. Record26metadata rows/26readbacks andzero scientificresults. No automatic retry,subsequent continuation,parameter change,training or magnetic-tier promotion. Primary207/publication192tests pass;initialreadonlySSHtimeout and publication missing-test selection failure remain preserved. Next only requested status/completion recovery and frameQC. Evidence:docs/reviews/fe110_c3_submission_20261027/README.md.

## 2026-10-27 - Advance the paper-inspired512-frame pilot to one bounded training proposal

User requested 按照文献继续推进. Prepare one initial force-only candidate from theoriginalAQCat25base andimmutable512train/78dev/53reserved package;preserve uniform sampling,physical labels,magnetic tiers andwhole-family isolation. Propose2epochs/1024iterations,oneGPU30min/4CPU/32GiB;not converged-training evidence. Keep development-only checkpoint selection andexplicit46historically evaluated reserved frames;freeze candidate SHA before separate fixed inference.178diagnostic gaps andunfinishedC3lowforce continuation do not block trial preparation. Native source/DB/namespace/budget checks andremoteCPUcheckpoint architecture/hash checks pass;GPU1occupied atprobe. Specific new budget/deployment confirmation requested;no rootpolicy exception,authorization,upload ortraining created. Singlearm support requires explicit matching policy hashes;legacy defaulttwoarm contracts unchanged.44tests each checkout pass. Evidence:docs/reviews/fe110_training512_20261027/README.md.

## 2026-10-27 - Authorize and deploy one512-frame trial while preserving the GPU start gate

The user repeated 提交/再来/提交 after the exact30minute request review;interpret this as confirmation of onefbc1request,not3attempts orunknown-result retries. Verify the frozen preparation before adding one bounded backend exception;retain exactpreviouspolicybytes andprove no existing settings changed. Bind directrequest6167f4f87a1383f492fcd22f9bd0f133d6b7c46938f4644c6b02e4b69bb3bfca,upload1994files andcomplete nativeCPU/CLI/checkpoint/namespace preflight without CUDA. GPU1insufficientfreememory/existingprocess prevents launch;no launchreservation,marker,trainingPID orfake schedulerID. User budget authority remains valid;next idleGPU checkpoint can use the same request without reconfirmation. No automaticwaiter/retry,other-job stop,heldoutinference orVASP.50tests each checkout pass. Evidence:docs/reviews/fe110_training512_submit_20261027/README.md.

## 2026-10-27 - Complete the oneGPU0shared trial andfreeze its candidate

User explicitly replied 用吧 toGPU0sharing after residentservice/20,935MiB disclosure. Bind exact8PID/UID/starttick/script identities and16384MiB allocator cap while keeping historicalexclusive requests unchanged. Preserve data/loss/sampling/model/budget;only4armartifacts change(3runtime+paths). Retire oldunstartedGPU1 authorization in bothlocations withbytespreserved;newGPU0nativepreflight passes andone bounded producer completes2epochs/1024iterations in143.193248s withactualCUDA and2backwards/updates proof. Return13hash-verified files andfreeze candidate513decf4ebd823cf8f87a79e787fdbd543b657fd582184f2ab23845d281d6aeb.65tests eachcheckout PASS;8residentidentities remain/postrunresourcecheck passes,service latency not measured. DevroleMAE0.06152845is selection evidence,not fixedold/new orheldoutvalidation;no extraGPUinference,DFT orpromotion. LocalCPUOpenMP metadata failure resolved via native remoteCPU only;rawfailure retained. Next formal fixed comparison on this frozen candidate. Evidence:docs/reviews/fe110_training512_gpu0_20261027/README.md.


### 2026-10-27 — Frozen53 force comparison completed, candidate remains unpromoted

User explicitly requested 固定结构上的新旧模型力误差对照. Run exactly159forcepredictions using three previously frozen checkpoints onunchanged53reserved frames,under existingGPU0shareconditions and600s cap;no fitting,optimization,reselection orpromotion. All53CHOvectorRMSE improves12.97% vsoldcontrol,46historical improves6.73%,7REICO improves16.06%;42frames improve/11worsen. Herror andadsorbate directioncos/opposedcounts regress;C3test4framesallhighforce>2eV/A.No claimof53newblindframes,statisticalgeneralization,energyaccuracy orDFTspeedup. Preserve512/78/53splits/magneticgrades;942independent scalarreplays and50primary/33publicationtests PASS. Next smallsame-startC2/C3optimizationcomparison requires ownreviewedscope;not executed. Evidence:docs/reviews/fe110_fixed53_comparison_20261027/README.md.


### 2026-10-27 — Same-start C2/C3 ML comparison and four bounded DFT preparations

Execute theuser requested same-start comparison asfour frozencontrol/new512 LBFGS runs using10_A andexistingreviewedCARE05,80steps/0.10eV/A;no result-driven extension,seedchange ormodelpromotion. All247frames passsource/cell/fixed/force checks. C2takes47/48steps andremainsintact;C3old68steps,new80cap0.228697eV/A,andbothloseC-Cconnection toCO+C2H2. Preserve thisnegative intact-C3 result;DFTjobs fromthese endpoints areexplicitfragment diagnostics. InitialCAREplacementheight isnot afinal-relaxationgate;v1 retained,v2 source-boundpostrelaxationreview usesconfigured collision/reconstruction andactualsurfaceposition checks,notstabilityacceptance. Preparefour matched32rank/80step/LORBIT11/0.02DFTinputs withcurrentproductionprofile;fourcustodian/canonicalpreflight passes,24hashes andindependent247framereplay,47primary/38publicationtests PASS. Request exactDFTbudget1669-1892corehourreference(notcap) underusercostconfirmationrule;notyetuploaded/submitted. PriorpausedC3DFTdirectories untouched,no newtraininglabels/splitchanges. Evidence:docs/reviews/fe110_pair2_20261027/README.md.


### 2026-10-27 — Exact four paired DFT submissions authorized and completed

Human selected 提交全部4项（推荐，完成C₂/C₃配对诊断） afterreviewof32ranks/max80steps/0.02DFTforce and1669-1892corehourhistoricalreference(notcap). Preserve four sourcebundles andoriginalMLnegativeC3results;C3jobsremainCO+C2H2diagnostics. FreshremotePOTCARfamily/order/SHA/MAX128/targetfreshness checks andfourcanonicalSUBMIT_VASP gates pass;nativeexecutor returns9925060,9925062,9925063,9925065,allPEND atclient14:20:52Z.Firstreadonly55sSSHtimeout producednoremotewrites;successfulphasedsnapshot reusedwithin600s,notacomputationretry. Registerexact88metadataINSERT/0UPDATE/0results aftersavedplanreview;88readbacks and24inputhashes pass.153primary/136publicationtests PASS.No newGPU/training/modelpromotion orautomaticcontinuation;noSCF/force/chemistry/actualcost claim. Next on-demand four-job checkpoint. Evidence:docs/reviews/fe110_pair2_submission_20261027/README.md.

### 2026-10-28 — Judge acceleration by actual DFT convergence and remaining cost

User explicitly requested comparison after clarifying small ML residual force is insufficient. Recover only four already-authorized jobs;preserve failed/unconverged cases and C3 product classification. ThreeDONE jobs exhaust80without0.02;newC3RUN25auditedprefix. C2old/new handoffML0.090451/0.088025 corresponds toDFT0.239860/0.226764 onexactcoordinates;both80steps,849/871SCF,433.812/577.779allocatedcorehours. Lowerfinalforce isnot achievedacceleration. All265SCF/local-positiveFe associations,4rawhandoff replays and40scalarchecks pass;47relatedtests PASS. Preserve magnetic grades and512/78/53isolation;no newtraining,continuation,modelpromotion orscientificacceptance. Subsequent proposals should first diagnose near-equilibrium movableFe/adsorbate errors using existing train/dev data;keep these evaluation trajectories isolated. No pureDFTbaseline/same-minimum orintactC3claim. Evidence:docs/reviews/fe110_pair2_cost_comparison_20261028/README.md.

### 2026-10-28 — Prepare a bounded scratch-versus-finetune force-model trial

Human authorized beginning the proposed existing512-frame comparison. Prepare smallNequIP random initialization and originalAQCat25 fresh fine-tuning;force-only,unchanged512/78/53+16isolation/magneticgrades. Preserve uniform train weights and originalrole-weighted development objective;neither energy fitting nor a generalFeCHOmodel claim. NativeCPU smoke2updates andfine-tune nativeCLI pass;590lossless replays and48tests PASS. Propose exclusiveGPU1 sequential arms,each<=1800seconds,total<=3600seconds,zeroautomaticretries;NequIP100epochs/12800updates,FT20epochs/10240nativeiterations. No concreteGPUbudget confirmation yet;canonical backend policy unchanged,exceptions are drafts only. Existing2epoch/defaulttraining gates remain unchanged except a frozen512-bound20epoch preparation contract. CPUcheckpoints remain diagnostics;no newDFT/training admission/modelpromotion. Need fresh hash-bound authorization and currentGPUgate before formalGPUtraining. Evidence:docs/reviews/fe110_scratch512_20261028/README.md.

### 2026-10-28 — Exact two-arm GPU budget confirmed and sequence started

Human chose 启动两项训练，总计≤1 GPU小时（推荐）. Bind unchanged NequIPcd0fadb4 andFT87a20cb4 modelrequests toexactnewscoped canonical exceptions;sequentialGPU1/exclusive/1800seconds each/3600GPUseconds sum/no retry/noDFT/no promotion.2013production filehashes andfreshnativepreflight pass;one canonical-backed sequence launch,PID1363554/sequenceSHA dde58bdc7d1eae203b7a9ca1f7dd002ed2348e67b2c7b69e4387bfca6fc67c79. NequIP1363559proves216736CUDAparameters onphysicalGPU1,CPUaffinity0-3;secondarm usesexisting canonicalFTlaunch afterfreshgate. No completions oraccuracy/speedup claim. Preserve512/78/53+16isolation andmagneticgrades. Evidence:docs/reviews/fe110_scratch512_20261028/README.md;user_authorization.md inthatdirectory.

### 2026-10-28 Scratch512 terminal candidate review

Both arms ended21:26Beijing:NequiPnormalexit,FTwalltimebudgetstop before20epochs,no retry/resume/promotion.23terminalfiles returnedwithSHAverification,actualGPU1 andfinitecheckpointstate confirmed.CPU-only recovery;no newinference orDFT.78dev roleweightedforcevectorMAE0.3190777691/0.05564634551eV/A;partialFTisbetterinthisconfiguration/budget,not proofuniversalarchitecture superiority oractualacceleration.NequiPbest/last saveepoch33/globalstep4352 do not establishfinalepoch/stopreason;FTlastcomplete saveepoch9/4608iterations,bestepochunknown.Sequence2711.264202s<1GPUhour,FTrecorded1802.071767s includingbudgetdetection/exit.No automaticextensionfromremainingtotalbudget.512/78/53+16isolation/magtiers unchanged.Nextscopedexisting-development Fe/adsorbate lowforce/direction diagnosis;notstarted.Evidence:docs/reviews/fe110_scratch512_20261028/README.md;calculations/.../scratch512_20261028_v1/terminal_review_20261028.json.

### 2026-10-28 Same-start scratch512 speed pilot preparation

Human quotedtheactualsame-start MLthenDFTbenchmark asnextobjective;preparetwocandidatesontheexisting10A/C3_05originswithoutreselection.4MLruns/600sGPU1exclusiveproposal,23artifacthashes/nativeCPUinterfaces/52testsPASS.Canonicalpolicyunchanged/authfalse;engineeringrule13 requiresconfirmationoftheconcreteGPUbudgetbeforelaunch.NoGPU/DFTstarted.EachmodelusesexplicitprovenPython;sameASE3.29.0/Torch2.4.1/E3nn0.6.0interfaces.CPUfixedforcechecksarenotaccuracyvalidation.FirstFTCPUconfig-wrapperfailurepreservedandcorrectedwithoutweightchanges.DirectDFTneededforexactspeedbaseline:historical9848811POSCARdiffers,114stepsnotamatchedreference.Futuremax6DFT/32core/300steps/0.02onlyafterMLgeometryreviewandseparatecostconfirmation;historical9386-10640corehourreferenceisnotacaporprediction.C3priorfragmentationremainschemicaldiagnostic,nointactsuccessclaim.Originaldataisolation/magnetictiersunchanged,bothoriginsobservedratherthannewblindtest.Developmentlowforce/directiondiagnosisdeferredratherthanlost.Evidence:docs/reviews/fe110_scratch512_speed2_20261028/README.md.

### 2026-10-28 Authorized four-path ML comparison completed

Human explicitly chose启动4次ML优化，合计≤10 GPU分钟（推荐）.Preserveunauthorizedv2draft;activateonlyexactscopeandnewauthorizedrequestce9d2fd5d34389824a01947d77879da9c8a9c5608074822d9387cce2a36a4e2d.Native24inputhash/exclusiveGPU1preflightPASS,onecontroller1413223/producer1413238,bothexit0at57.622616s.NequiPC2/C3=34/41stepswithMLfmax0.094231/0.094423;FT60/65with0.069361/0.077344.C2initialgraphretained,bothC3fragmentCO+C2H2;notintactC3success.C2/C3MLpairadsorbateRMSD0.816039/0.944118A,notDFTbasinequivalence.29files/204frames/fixedmask/rawforces/source/finalPOSCARauditPASS,55testsPASS.GPU1postrun24065MiBfree/nocompute,ownedidentitiesgone,checkpointSHAunchanged.No training,DFT,autocontinuation,retry,promotion,magneticgradeupgradeorlabeladmission.ConsumedGPUbudgetnottransferred.NextprepareC2three-armDFTinputs/concretecost;C3remainsdiagnostic;actualDFTforces/convergence/same-minimum/accelerationunverified.Evidence:docs/reviews/fe110_scratch512_speed2_20261028/README.md anduser_authorization.md.

### 2026-10-28 C2 three-arm DFT input preparation only

Human explicitly requestedC2directDFT/NequiPthenDFT/FTthenDFTinputswith0.02eV/Astandard.Prepare3freshproductiondirectoriesusingcurrentcanonicalbuilder,all32cores/NSW300/LORBIT11/MAGMOM45x2.2+5x0/fixedFe0-17.PreserveoriginalPOSCARbytesforpureDFTandbothreviewedMLfinalbytes;no historical114stepbaseline substitution.3INCARreadonlyaudits/3canonicalpreflights/18corehashes/direct-noML/methodidentity/55testsPASS.CC1.415052/1.676277/1.433798A,C2pairRMSD0.816A;keepNequiPelongationasdiagnostic,notsameDFTminimumproof.Historical5742-6504corehourlinearreferenceisnotcaporprediction.Onlypreparationauthorized,noupload/submission/SUBMIT_VASPaction;actualremotePOTCARandquotaunchecked.Futuresubmissionrequiresconcretebudgetandfreshgates.NoC3/GPU/training/labeladmission/magneticgradechanges.ActualDFTconvergence/magnetism/speedupunverified.Evidence:docs/reviews/fe110_c2_three_arm_dft_20261028/README.md;plan/input_verificationunder scratch512_speed2_20261028_v2/c2_three_arm_dft300_v1/.

### 2026-10-28 C2 three-arm DFT submission and metadata registration

Human latest提交 authorizesexactprepared3C2relaxations,32ranks/max300steps/0.02,noautomaticretry/continuation.Noextra confirmationorchangedinputs.NativeFe/C/HPAW-PBEPOTCARfullSHAbd39c0eb.../runtime/3freshdirs/32of128accountusage+96newgatesPASS;canonicalSUBMIT_VASPexecutorreturned9926805direct,9926806NequiP,9926807FT.InitialLSFcheckpoint2026-10-28T15:41:38ZallPEND/Gkn_normal;notSCForionicprogress.18submittedinputhashesunchanged.Registryschema/integrity/FKpreflightPASS;saveandreviewexactplan c5a03f1fe5947a9c7d7f71dfc05e2c7f13308a0732928848ef1e67d61a4ef22b,approve_plan asCodex underhumanjobauthority,apply66INSERT/0UPDATE(3calculations/3jobs/3history/57files),66readback/0scientificresults.33scope+24canonicalexecutortestsPASS,syntax/RuffPASS.NoC3/GPU/training/otherjobstop/labeladmission/magneticgradeupgradeorautomaticmonitor.ActualSCF,moments,firstDFTforces,0.02convergence,sameDFTminimumandcostspeedupunverified;nexton-demandcheckpoint.Evidence:docs/reviews/fe110_c2_three_arm_submission_20261028/README.md anduser_authorization.md.


### 2026-10-29 C2 two-control cancellation and three-structure comparison

User explicitly cancelled only9926805direct and9926806NequiP,then requested all3laststructures andconformationcomparison.Two current hash-bound STOP_JOBgates andnativeexecutor receipts,LSFEXIT/EXITconfirmed;9926807FTremainsDONE.Alloutputsretained,norestart/resubmit/delete,otherjobsuntouched.Direct75steps/1497completeSCF+16interrupted/fmax0.401579;NequiP93/1212+6/0.061108;FT69/586/0.0183064.ThreeoriginalCONTCARreturned/hashverified,bothstoppedcoordinate-forcechecksPASS;allC2H3connectivityandmainFebindingneighborsretained.36cleanslabsymmetries+sameelementpermutations:FT-relativeadsRMSDdirect0.244716/NequiP0.209133A;movableFe0.119203/0.012686A.Geometrydiffersbutdifferentconvergedminimanotestablished;2stoppedcontrolsarecensored,notfinalconvergedbenchmarks.Registryexactplan3e1b1d9e...reviewed/applied23INSERT+3workflowchanges,allreadbacks/0scientificresults.EXITmaps toexistingworkflowfailedwith explicitUSER_REQUESTED_CANCELLATIONnotes,notSCFfailure.Nofulltrajectoryacceptanceormodelpromotion.Evidence:docs/reviews/fe110_c2_three_arm_stop_20261029/README.md.
