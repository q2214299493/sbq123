# User Preferences

This document stores durable user workflow preferences. One-off task instructions and transient calculation states do not belong here.

## Migration Status

Batch `MM-001` completed on 2026-06-23. Current project files remain authoritative when legacy memory conflicts with this document.

| Category | Status |
|---|---|
| Server selection and command patterns | Migrated in `MM-001` |
| VASP/VTST input templates | Migrated in `MM-001` |
| Naming and directory conventions | Migrated in `MM-001` |
| Structure review and reporting preferences | Migrated in `MM-001` |
| Monitoring and failure-response rules | Migrated in `MM-001` |
| Retrieval and evidence requirements | Migrated in `MM-001`; superseded by the 2026-06-24 whitelist decision where noted |
| Module and task-management behavior | Migrated in `MM-001` |

## Source Register

- `S1`: `C:\Users\86177\.codex\memory\sessions\active-session.md`, stable preferences and later corrections.
- `S2`: `modules/memory_migration/archive/PROJECT_CONTEXT_MEMORY.md`, duplicate and correction cross-check.
- `S3`: `C:\Users\86177\.codex\skills\vasp-catalysis-workflow\SKILL.md`, workflow and server-tool rules.
- `S4`: current `AGENTS.md` and `docs/01_METHOD_PROTOCOL.md`, authoritative project rules.
- `S5`: read-only live server checks on 2026-06-23.

## Active Preferences

| ID | Category | Durable Rule | Source | Status |
|---|---|---|---|---|
| `UP-001` | Continuity | Resume from project state files and verified outputs; legacy memory is supporting evidence, not the live source of truth. | `S1,S4` | Active |
| `UP-002` | Task management | Keep one thread-sized current task, preserve displaced work in the backlog, and update affected state/module files at task close. | `S4` | Active |
| `UP-003` | Server | Use only SSH alias `sunboquan-codex` unless the user explicitly requests another server. | `S1,S2,S4,S5` | Active |
| `UP-004` | Server | Use `~/sbq/agent/jobs` as this project's remote calculation root. Do not use the absent legacy root `~/sbq/Fe_agent_demo`. | `S1,S2,S4,S5` | Active |
| `UP-005` | Commands | Prefer local scripts/files plus `scp` and short SSH commands; avoid fragile heredocs, nested quoting, and remote `awk`/`sed` embedded in PowerShell. | `S1,S2,S3,S4` | Active |
| `UP-006` | PowerShell | Do not assume `New-Item -LiteralPath` works; use `New-Item -Path` or `.NET Directory.CreateDirectory`. | `S1,S2` | Active |
| `UP-007` | Submission | Submit LSF jobs with `bsub script.lsf`, never `bsub < script.lsf`. | `S1,S2,S4` | Active |
| `UP-008` | Server tools | Verified defaults: `~/vasp541std.lsf`, `~/vasp541vtst.lsf`, `/home_gkx/Soft/vaspkit/vaspkit.1.2.1/bin/vaspkit`, and `~/bin/PBE`. Recheck before reuse if the environment changes. | `S1,S2,S3,S5` | Active |
| `UP-009` | Artifacts | Keep remote folders for calculation inputs/outputs. Keep structure-review artifacts locally under `C:\Users\86177\Desktop\结构`; keep this repository's reports under `reports/`. | `S1,S2,S4` | Active |
| `UP-010` | Relaxation template | Historical `INCAR-basic` template with `ISMEAR=0`, `SIGMA=0.5`. It is no longer a production default; use the convergence-backed group protocol in `UP-029`. | `S1,S2`; superseded by user instruction 2026-06-29 | Superseded |
| `UP-011` | Magnetism | Generate `MAGMOM` from POSCAR species order and counts. Keep zero-moment species segments separate; for Fe C O = 45 1 1 use `45*2.2 1*0.0 1*0.0`, not `45*2.2 2*0.0`. | `S1,S2` | Active |
| `UP-012` | Endpoint consistency | Match endpoint INCAR/KPOINTS/POTCAR families before NEB. The corrected true Fe(110) active production branch uses Gamma `5x5x1`; old non-current endpoint records must not be mixed into this branch. | User correction, 2026-06-27; updated 2026-07-09 | Active |
| `UP-013` | Evidence | Before any new calculation or external structure/path choice, use only the approved catalysis-data whitelist with BM25 plus semantic Top-5 retrieval; official software documentation remains allowed for method syntax. Superseded by the controlled fallback in `UP-033`. | User decision 2026-06-24; superseded 2026-07-14 | Superseded |
| `UP-014` | Iteration | Combine accepted whitelist retrieval, validated local calculations, and documented failures. Reuse the closest validated local structure and make the smallest chemically justified change. | User decision 2026-06-24 | Active |
| `UP-024` | Continuity | New threads must read the repository startup/state/task files first. Memory files are handoff-only and must not be read during routine work; consult them only for an explicit handoff, migration, or recovery task. | User decisions 2026-06-24 and 2026-06-28 | Active |
| `UP-015` | NEB path | Do not use pure C/O endpoint interpolation for dissociation. Preserve chemically meaningful molecular, tilted/lying, TS-like, and dissociated states; a C-O near `2.05-2.12 A` is TS-like, not the final state. | `S1,S2,S4` | Active |
| `UP-016` | NEB gates | Before submission run and save `dist.pl POSCARis POSCARfs`, a geometry table, and `nebmovie.pl 0`; after completion or stopping run `nebmovie.pl 1` before interpreting the path. | `S1,S2,S4` | Active |
| `UP-017` | Input audit | Before submission verify structure origin, atom order, Selective Dynamics, POSCAR/INCAR/KPOINTS/POTCAR/LSF presence, POTCAR order, MAGMOM length, and core/image compatibility. | `S1,S2,S3,S4` | Active |
| `UP-018` | Monitoring | Default to a parsed summary: scheduler state, completed steps, electronic verdict, latest per-image atomic/NEB force and trend, geometry verdict, and main problem. Print raw SCF/force histories only when explicitly requested. Query each live source once per checkpoint. | User instruction, 2026-06-27 | Active |
| `UP-019` | Failure response | Do not blindly resubmit parameter variants or continue a structurally invalid path. Diagnose the failure, preserve useful outputs, record the lesson, and do not delete/rename calculation folders without explicit approval. | `S1,S2,S3,S4` | Active |
| `UP-020` | Approval | Technical prechecks and review are always required. Whether every submission also requires a fresh explicit user approval, versus task-level delegated autonomous submission, is unresolved. | `S1,S2,S3,S4` | Needs confirmation |
| `UP-021` | TS validation | Grade TS candidates A/B/C using saddle convergence, imaginary-frequency count, target-mode assignment, geometry sanity, and IS/FS connectivity. Only Grade A enters the validated database or feeds MKM/KMC; Grade B requires review and Grade C is excluded. | User instruction, 2026-06-23 | Active |
| `UP-022` | Data governance | Do not invent repository data or replace scientific judgment. Every result must be traceable, every job must have status, and every calculation input/output must have a database record. | User instruction, 2026-06-23 | Active |
| `UP-023` | Repository architecture | Keep adsorption, NEB, DIMER, TS frequency, thermochemistry, kinetics, KMC, reactor, and uncertainty stages as separate repository modules with explicit boundaries and handoffs. | User instruction, 2026-06-23; superseded by `UP-035` | Superseded |
| `UP-025` | Reporting | Routine progress is chat-only and concise. Do not generate reports or update repository state when nothing materially changed; replace the compact current snapshot only for meaningful status, evidence, decision, blocker, path, or next-action changes. | User instruction, 2026-06-27 | Active |
| `UP-026` | Error reflection | When Codex makes a mistake or hits a recurring workflow problem, create or update a concise error-reflection record in the repository so the issue is not repeated. This is for agent/process errors, not routine progress. | User instruction, 2026-06-26 | Active |
| `UP-027` | Dataset consistency | Treat the optimized-bulk to slab, adsorption, endpoint, and NEB workflow as one production dataset. Use convergence tests to select one slab thickness, then keep that thickness and one compatible numerical protocol for every reportable state; do not mix routine/reporting layer counts. | User instruction, 2026-06-28 | Active |
| `UP-028` | Memory retention | Store only durable decisions, scientific boundaries, workflow rules, and stable preferences in continuity memory. Exclude failed-task logs, transient scheduler states, per-step force/energy histories, and full chats unless a reusable lesson is explicitly promoted. | User instruction, 2026-06-28 | Active |
| `UP-029` | Adsorption-energy compatibility | Across future bulk/surface/adsorption work, lock `GGA=PE` (PBE), the approved PAW-PBE POTCAR family, and `ENCUT=400 eV`. Use `ISPIN=2` for Fe-containing magnetic systems, but use `ISPIN=1` with no `MAGMOM` for closed-shell gas-phase CO. Keep `EDIFF`/`EDIFFG` and `ISMEAR`/`SIGMA` identical within compatible workflow stages; metals and oxides may use separate convergence-backed groups, but one energy difference cannot mix groups. For one surface family, keep lateral cell, slab thickness, vacuum, fixed-layer rule, and slab k-mesh identical. | User instructions, 2026-06-29 | Active |
| `UP-030` | Adsorption spreadsheet | Use the current accepted `课题一吸附_最终.xlsx` as one canonical worksheet and the existing eight-column visual template as the only format. Append registered adsorption records directly; do not create extra sheets, sections, columns, or workbook copies. Preserve existing rows. When a final site cannot be expressed by `top`/`hollow`/bridge alone, use concise standard notation such as `η²(C,O)/t-lb-t` or `η²(C,O)/h-lb-h`. Enter only compatible, converged, geometry-valid, final-site-classified results as formal adsorption-energy data; deduplicate structures that converge to the same final state. | User instructions, 2026-07-04 and 2026-07-13 | Active |
| `UP-031` | Fe(110) k mesh | Use Gamma `5x5x1` for the active five-layer Fe(110) production dataset, including clean slab, adsorption relaxations, adsorption final statics, endpoints, and NEB. Do not introduce `7x7x1`; every energy difference must use the same `5x5x1` branch. | User instruction, 2026-07-04 | Active |
| `UP-037` | Fe(110) formal energy | Use the final `OUTCAR` `TOTEN` from compatible converged `ISMEAR=1`, `SIGMA=0.20 eV` Fe(110) production/DIMER calculations as the formal surface-state energy. Do not require a separate single-point; retain `SIGMA=0.10 eV` statics only as optional provenance/convergence checks and never mix them into the active energy chain. | User instruction, 2026-08-07 | Active |
| `UP-032` | Submission deduplication | For a user-supplied concrete candidate list, reconcile it against the calculation registry and live scheduler records, then generate and submit only missing candidates. Never resubmit an already registered or active duplicate. | User instruction, 2026-07-14 | Active |
| `UP-033` | Adsorption-site evidence | Search the approved whitelist first and stop if it contains a usable matching adsorption motif. Only `NO_WHITELIST_MATCH` permits fallback to authoritative peer-reviewed chemistry/materials/catalysis primary literature. Generate exactly the unique stable configurations supported by accepted evidence; never pad to a fixed four-site list. | User instruction, 2026-07-14 | Active |
| `UP-034` | External adsorption evidence scope | Use whitelist or fallback-literature adsorption evidence only to select and rank plausible configurations and to initialize reviewed geometry such as sites, bond lengths, angles, heights, and orientations, reducing calculation cost. External energies are relative-order references only and must never enter local adsorption energies, the registry, or Excel. | User instruction, 2026-07-14 | Active |
| `UP-035` | Unified TS strategy | Treat NEB and DIMER as methods inside one Transition-State Strategy Engine V3. The unified flow is endpoint/mapping guard, reaction fingerprint, accepted-template retrieval, rule fallback, waypoint/path initialization, NEB, optional DIMER refinement, TS validation, and successful/failed experience storage. Remove separate NEB/DIMER workflow authorities and redundant wrappers; only Grade-A success may transfer as a TS template. | User instruction and V3 specification, 2026-07-17 | Active |
| `UP-036` | Deliverables | Generate only files explicitly requested by the user or strictly required as usable task outputs. Do not leave optional previews, reports, manifests, prescreen plans, intermediate exports, duplicate versions, or other explanatory artifacts. Run internal checks in chat or temporary storage and remove temporary artifacts after validation. Safety-required backups and workflow-mandatory persistent files remain allowed only when genuinely necessary. | User instruction, 2026-07-17 | Active |
| `UP-038` | Automatic registry completion | When a VASP adsorption or coadsorption relaxation reaches normal termination and passes electronic convergence, ionic/force convergence, compatibility, and chemistry-aware final-geometry review, register its scheduler evidence, final structure/output files, compatible final `OUTCAR` `TOTEN`, final movable-atom force, and acceptance review in `data/project_registry.sqlite3` during the same completion workflow. This append-only, idempotent registration needs no separate user reminder or approval. Failed, incomplete, incompatible, duplicate, or unreviewed states must retain their truthful status and must not be registered as accepted results. Absolute adsorption energy and Excel promotion remain separate reference-completeness gates. | User instruction, 2026-08-26 | Active |
| `UP-039` | GPU TS failure routing | After a GPU TS/path failure, present both the active-learning diagnostic route and the direct VASP path/refinement route before selecting the next method. When a hash-bound, geometry-valid last-valid/failure-boundary pair satisfies the active-learning entry gate, prefer exact-structure MatRIS/AQCat25/VASP error diagnosis before VASP micro-NEB or Dimer. If MatRIS exceeds the registered VASP-error ceilings, prepare replay fine-tuning and a new-checkpoint full-path rerun; if it passes, retain the checkpoint and choose path repair or local VASP micro-NEB. This preference does not authorize automatic GPU, VASP, fine-tuning, rerun, or Dimer submission. | User instruction, 2026-09-01 | Active |

## Required Record Format

Each accepted preference must include:

- preference ID and migration batch
- category and concise rule
- source and last verification date
- scope or exceptions
- status: `Active`, `Superseded`, or `Needs confirmation`

When a preference conflicts with current project files, do not overwrite silently; record the conflict in the batch report and request confirmation.
