# Scientific data intake and scoped human acceptance

A researcher can supply a local calculation, external platform result, literature or database record, measurement, structure, correction or an explicit assumption. Start with a reaction ID and any observations available. Incomplete records can be saved and inspected. Upload further JSON documents with the same reaction ID and unique record IDs. An identical repeated record is idempotent. A changed record needs a new ID. Conflicting usable records remain visible for reconciliation.

Run from the checkout or the installed Python package. The command reads input JSON and writes a missing-data report to stdout.

```text
python -m scripts.scientific_intake reports/multiphase/ch_co_intake_20261119.json --operation thermochemistry
python -m scripts.scientific_intake base.json endpoint-upload.json --operation zpe
```

## Source policy and human acceptance contract

Each record has a state, property kind, typed value and evidence mode. The modes are FULL_VALIDATION, USER_PROVIDED, LITERATURE_EXTERNAL and USER_APPROVED_ASSUMPTION. The mode describes how evidence entered the project. Review and use depend on the following independent records. The machine-readable acceptance contract is `$defs.acceptance` in the [intake schema](../../configs/kinetics/scientific_intake.schema.json).

| Record | What to supply | Effect |
|---|---|---|
| provenance | Known source type, reference (such as DOI, accession, path or platform record), original calculation ID if available, SHA-256, supplier and source date | Unknown source details are omitted and reported. No local task ID, registry row or OUTCAR is needed. |
| validation | Scientific status, exact property kinds reviewed, method, compatibility and limitations | A validated property needs a named method and compatible context. Rejection or known incompatibility excludes the evidence. An upload carries a review assertion. Its authenticity remains the responsibility of the reviewing workflow. |
| acceptance | Pending, accepted or rejected. A decision records who, operation scope within this reaction, reason and time with timezone | Accepted unverified evidence can inform the specified assessment with explicit limitations. It retains AVAILABLE_BUT_UNVERIFIED. An assumption always requires the decision and limitations. A scoped human rejection excludes use in that scope. |
| uncertainty | Available error estimate with units, range or source description | Unknown uncertainty is reported separately. |

Example decision for a user-supplied site assignment (illustrative only):

```json
{
  "acceptance_status": "accepted",
  "accepted_by": "example-reviewer",
  "acceptance_scope": ["site_mapping"],
  "acceptance_reason": "Use the proposed multiplicity for this sensitivity case.",
  "acceptance_timestamp": "2026-11-19T10:00:00+08:00"
}
```

Record automatic projections as `site_inference`. A confirmed `site_mapping` separately names species, site types and positive multiplicities, consumed and released site counts, interface assignment and reaction classification. Empty site-count lists express a confirmed absence. If there is no interface, explicitly record the reviewed single-surface assignment. Unknown fields can be omitted and remain unresolved.

## How to read a report

Each field has an evidence status, candidates with reasons, scoped usability and an operation status. AVAILABLE identifies a reviewed compatible property. AVAILABLE_BUT_UNVERIFIED covers partial or limited evidence, including a usable scoped assumption. MISSING identifies absent evidence. INCOMPATIBLE identifies conflicts, rejected evidence or a mismatch. NOT_REQUIRED_FOR_CURRENT_OPERATION leaves the underlying evidence status visible. Missing provenance and uncertainty carry record IDs.

| Operation | Inputs examined for completeness |
|---|---|
| electronic | IS/TS/FS structures and electronic energies with a common reference |
| zpe | Structures plus reviewed spectra or precomputed ZPE for each state |
| thermochemistry | Electronic inputs, temperature, standard state and one compatible route per state. Set pressure_dependent to true when the thermochemical operation depends on pressure. |
| site_mapping | Complete reviewed or scope-accepted site assignment |
| kinetic_handoff | Thermochemistry, site accounting, operating pressure and forward/reverse kinetic inputs. Explicitly irreversible reactions need only the forward rate. The existing kinetic bundle validator and execution gates own final eligibility. |

Use a stable structure identity for each state (for example a hash or an external accession), and bind energies and thermal records to it. Raw inputs include signed frequencies in cm⁻¹, zero-based mapped atoms, constraint description, expected active-mode count, method and reviewed thermal basis. Endpoints require stable modes and TS requires one assigned imaginary mode under the owning review. Do not discard soft modes on import. Precomputed corrections use eV per state for ZPE, thermal enthalpy increment and Gibbs correction, eV/K per state for entropy, kelvin and the named standard state. Document whether the thermal enthalpy increment excludes ZPE and how Gibbs and the unstable mode were treated in the method. Use the same thermal basis identifier only after reviewing active subspaces, conventions and compatibility. Complete corrections can substitute for raw spectra, including for just one state.

The generator inventories inputs. It performs no frequency integration, free-energy or rate calculation. `inputs_complete` means that the selected operation's input checklist is satisfied within its recorded review/acceptance scope. Executable MKM still requires the existing reviewed Phase 1 bundle, units, energy conventions, validated site and rate relationships and the owning execution gates. Intake cannot write the registry, launch VASP or authorize a submission.

## Inspect a research project offline

From the repository root, run the following with the project YAML first and the task YAML second. The command prints JSON to stdout. Source files, databases, project state and execution permissions are untouched.

```powershell
python -m scripts.scientific_intake --inspect-project reports/workflow_design/stage_f1_2/nicu/project.yaml reports/workflow_design/stage_f1_2/nicu/task.yaml
```

The [runnable project/task pairs](../../reports/workflow_design/stage_f1_2/completion.md) cover an electronic-energy study, an archived MKM result and a finite-lattice software fixture. The reaction CLI and its Python `report(documents, operation)` entry point retain their existing behavior.

- **Project.** Use the existing `version: 1`, `project_id`, `objective` and `system`. When the catalyst catalog has a different ID, declare `catalyst_project_id`. Set `evidence_base` explicitly when supplying named sources. A relative base is resolved against the project YAML directory.
- **Task.** Supply `task_id`. Optional `project_id` binds the task to its project. `requested_observables` and `engine_routes` are lists. Supported routes are `mkm` and `kmc`. Existing `authorized_scope` and `forbidden` entries are displayed as context. A project/task pair without evidence references still returns its context.
- **References.** Put named `sources` on the project, task or individual context. Each entry contains `path` relative to the evidence base and the SHA-256 of the file bytes. Repeating a role across levels is ambiguous. No fallback search occurs. Domain JSON roles are parsed after byte verification. Other names can inventory opaque evidence such as MAT, OUTCAR or a written review.
- **Several reactions or operating points.** Use a task `contexts` list with unique `(reaction_id, operating_point_id)` pairs. Each context can supply its own `network_version`, requested observables, routes and sources. Declare shared sources once. An operating-point label identifies the request; the bound dataset, configuration and run receipt establish its actual conditions.
- **What to read.** Each context includes catalyst ownership, species, conservation findings, operating conditions, per-role integrity, per-observable source roles, value, missing requirements and blocker, and independent engine diagnostics. `available` describes the scoped archive evidence. `input_eligible` describes offline input preparation. Execution remains unauthorized. Missing bytes, changed bytes, unsupported versions and absent scientific evidence remain distinguishable.
- **Historical provenance.** Paths and hashes quoted inside archived reviews retain their original meaning. The inspector checks the named evidence inventory, intake raw structure/energy references, and candidate input members. It checks cross-artifact identities for the requested result. Embedded remote job directories and external citations are historical metadata. A structure may have reviewed archived evidence while its raw CONTCAR is unavailable locally.
- **Exit status.** A valid inspection returns zero even when a scientific observable is blocked. Read the individual statuses for automation. A malformed project/task pair or incompatible CLI modes produce a command-line error.

| Requested observable | Primary source roles |
| --- | --- |
| `structures`, `electronic_energies` | `intake` and the bound `network` when supplied |
| `electronic_barriers` | `network` |
| `thermochemistry` | `network`, `intake` and the scoped thermochemistry already embedded in that network |
| `kinetic_parameters` | `network`, `dataset` |
| `native_rates` | `network`, `rates`. Optional named dataset and native output are checked against rate provenance |
| `tof` | `network`, `dataset`, `configuration`, `result`, `mkm_receipt` |
| `stable_drc` | TOF roles plus `drc_plan` and `drc` |
| `rate_uncertainty` | TOF roles plus `rates` and the archived CATKINAS `qualification` |
| `lattice` | Source network definition, `graph`, `observation` |
| `native_initialization` | Network definition, `graph`, `original_manifest`, `kmc_plan`, `kmc_receipt`, `kmc_validation` |
| `candidate_input` | Network definition, `graph`, `candidate_manifest` and its native input members |

A standalone `catalog` can supply a V1 bundle or a partial network definition. MKM preparation uses `configuration`; KMC preparation uses `kmc_configuration`. The archived zero-event control is a separate evidence route. It does not authorize running a corrected candidate.
