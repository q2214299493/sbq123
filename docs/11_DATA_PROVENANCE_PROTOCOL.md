# Calculation Registry and Data Provenance Protocol

## Non-Negotiable Requirements

1. Do not invent data. Missing values remain null and are marked `Needs confirmation` or `Unknown` with a reason.
2. The registry does not replace scientific judgment. Automated checks and reviewer decisions are stored separately.
3. Every result must be traceable to its calculation, inputs, outputs, method, job, and source path.
4. Every job must have a recorded scheduler status and a separate scientific status.
5. Every calculation input and output must have a file record in the registry.

## Required Record Layers

### Calculations

- calculation ID and module
- scientific purpose and system
- parent calculation or source structure
- method and code/version
- input-set ID and output-set ID
- created, submitted, started, checked, and finished timestamps when known
- responsible agent/reviewer and notes

### Jobs and Status History

- job ID, scheduler, queue, server, and remote directory
- raw scheduler status such as `PEND`, `RUN`, `DONE`, or `EXIT`
- status-check timestamp and source command/output
- scientific status stored separately, such as `Not assessed`, `Converged`, `Not converged`, `Invalid path`, or `Failed`
- termination reason and restart/supersession links

`DONE` is not evidence of scientific convergence. An unavailable status is recorded as `Unknown`; it must never be inferred from an old chat or missing file.

### Files

Every input and output receives a registry entry with:

- file ID, calculation ID, job ID, role, and filename
- local and/or remote path
- file type, byte size, modification time, and SHA-256 when available
- existence and retrieval status
- provenance and source calculation
- storage mode: repository, object/archive storage, or external path reference
- license, sensitivity, and retention notes

Large runtime files and licensed `POTCAR` data still require registry entries. Their content must not be forced into Git: store approved metadata, checksums, source paths, and retention location. Exact raw-content storage and object-store policy are **Needs confirmation**.

### Results and Scientific Review

- value, unit, uncertainty, reference convention, and extraction method
- source file ID and source location within the file when available
- automated validation result
- reviewer decision, reason, timestamp, and confidence/status
- superseded or rejected result links
- downstream eligibility, including TS Grade A/B/C rules

No unreviewed or ambiguous result may silently become a kinetic-model input.

For transition states, an accepted label is insufficient by itself. The
registry must resolve it to the source saddle calculation, confirmed frequency
evidence, reaction/atom-map/method fingerprints, and a compatible IS/TS/FS
final-energy set before template reuse or kinetic use. In the active Fe(110)
branch the formal energy is final `OUTCAR` `TOTEN` from the compatible
`ISMEAR=1`, `SIGMA=0.20 eV` production/DIMER convention; no additional
single-point is required.

## Minimum Workflow

1. Register calculation and input files before submission.
2. Register the submitted job and initial scheduler status.
3. Append status checks without overwriting history.
4. Inventory generated outputs at checkpoints and completion.
5. Extract results with units and source-file links.
6. Apply scientific validation separately.
7. Mark downstream eligibility only after the relevant acceptance gate passes.

## Adsorption Result Promotion Gate

Before an adsorption result is written as final data in Excel, registry, NEB
endpoint inputs, or kinetic tables, it must pass the `dataset-compatibility-gate`
skill.

Required evidence:

- compatible clean slab, adsorbed slab, and gas/reference branch;
- same facet, slab model, layer count, vacuum, fixed-layer rule, POTCAR family,
  `GGA=PE`, `ENCUT=400 eV`, and approved KPOINTS branch;
- Fe-containing systems use `ISPIN=2`; closed-shell gas references use
  `ISPIN=1` without `MAGMOM`;
- scheduler state is recorded separately from electronic convergence, ionic
  convergence, final geometry, and reviewer decision;
- final chemical species, chemical event, and plausibility status are assigned
  through `chemical-plausibility-gate`;
- final site class is recorded separately from initial site;
- duplicate/superseded status is decided before Excel promotion;
- near-desorbed, dissociated, migrated, or weakly bound structures are labeled
  by their final chemistry, not by the starting folder name;
- source paths, job IDs, total energies, units, and extraction locations are
  recorded or marked `Needs confirmation`.

Promotion states:

- `candidate`: generated or submitted but not terminally reviewed;
- `submitted`: has job ID and remote path;
- `converged_unreviewed`: terminal and apparently converged, geometry not fully
  reviewed;
- `reviewed_valid`: convergence and geometry pass, but compatible
  energy/reference review may still be missing;
- `duplicate`: chemically the same as a selected representative;
- `rejected`: wrong branch, failed SCF, invalid geometry, or unusable reference;
- `static_needed`: legacy state for a valid relaxation whose former policy
  requested a static calculation;
- `static_accepted`: an accepted legacy/optional static and compatible
  reference chain;
- `energy_accepted`: a converged, geometry-valid calculation whose hash-bound
  final `OUTCAR` `TOTEN` passes the active compatibility convention;
- `excel_promoted`: accepted row has been written to the project Excel/registry
  output.

The active true Fe(110) branch uses the five-layer Fe45 slab, bottom 18 Fe
fixed, about `15 A` vacuum, and Gamma `5x5x1`. Historical fake-Fe(110) or
Fe(211)-like data, old failed clean statics, and incompatible KPOINTS branches
must not be promoted into this branch.

## Implementation Status

The requirements are accepted. `modules/calculation_registry/schema.sql` exists,
and the first 24 H2/CHx/CHO adsorption relaxations have calculation, job, file,
result, chemical-review, duplicate, and compatibility-gate records. Accepted
clean/gas references, including three reviewed gas isomers, are registered.
Existing compatible, converged Fe(110) relaxation energies may be reviewed as
`energy_accepted` without submitting new static calculations. Missing job,
output-hash, convergence, geometry, or reference evidence remains a blocker.
Object/archive policy and full historical backfill scope remain **Needs
confirmation**.
