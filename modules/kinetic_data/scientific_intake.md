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
