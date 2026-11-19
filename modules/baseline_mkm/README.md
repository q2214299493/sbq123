---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: MODULE_CONTRACT_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Baseline Mean-Field MKM

## Purpose

Solve the non-coverage-self-consistent mean-field mechanism for coverages, rates, TOF, selectivity, and degree of rate control.

## Primary Software

- CATKINAS is the preferred local mean-field MKM tool; its verified path, runtime, and I/O contract are in `configs/postprocessing_software.yaml`.
- As of 2026-11-19 the supplied single, curve and map examples have result files. The local quickstart log dated 2026-06-26 confirms startup. Completion is unconfirmed (完成未确认). The Fe(110) model still needs a validated input and result. See the [installed-file assessment](../../reports/multiphase/external_engine_compatibility.md).

## Entry Gate

- balanced reaction network
- validated free-energy barriers and prefactors
- temperature, pressure/feed, site density, and rate-law conventions
- CATKINAS input file generated from traceable kinetic records, not manual untracked values

## CATKINAS Input Scope

- reaction mechanism equations and site notation
- activation/free-energy inputs or approved scaling/BEP parameters
- gas pressure or concentration conditions
- initial/frozen coverages when specified
- calculation mode: single, curve, or map
- optional DRC and plotting settings

## Outputs

Phase 2.5 assembles a fixed-temperature CATKINAS single point with frozen gas partial pressures. It consumes an eligible Phase 2.4 dataset, verifies the supplied parameter table, and publishes a byte-hashed input directory. Independent text readback checks stoichiometry, indices, correction switches and both rate coefficients. The installed 20230524 P-code reported expiry before accepting the synthetic model on 2026-11-19. Native reading and numerical completion remain unconfirmed. See the [field contract and assembly command](../../reports/multiphase/phase2_5_native_contracts.md) and [validation receipt](../../reports/multiphase/phase2_5/native_validation.json).

- steady-state solution and site/mass-balance residuals
- TOF, selectivity, coverage, and DRC tables
- reproducible solver settings and provenance
- CATKINAS `result_INPUT*` folder metadata and parsed outputs, when execution is enabled

## Done Criteria

The [Phase 2.5.1 compatibility record](../../reports/multiphase/phase2_5_1/catkinas_compatibility.json) distinguishes the expired installation from the authorized November distribution. The newer P-code read the exact archived reaction and sites. Its equation generator reported no overall reaction and stopped in a symbolic assignment before returning either coefficient. See the [bounded target attempt](../../reports/multiphase/phase2_5_1/catkinas_target_attempt.json).

Mass/site balances close and the CATKINAS inputs, solver settings, rates, coverages, selectivity, and DRC outputs are reproducible and traceable.

Phase 2.5.2 verified the same adsorption equation within a closed, four-step synthetic turnover at 400 K. The native MAT file contains separate directional coefficients and fluxes. Install the `catkinas` extra for the single-point result reader. The [completion report](../../reports/multiphase/phase2_5_2/catkinas_closed_cycle_completion.md) contains the CLI workflow, balance checks, capability matrix and limits on standalone use.


## Phase 3.0 single-point workflow

Run from a source checkout with the CATKINAS optional dependencies. Prepare reads an immutable Phase 2.3 network, regenerates its Phase 2.4 dataset from the reviewed models, and uses the Phase 2.5 adapter to stage the exact input. The configuration selects frozen partial pressures in bar, initial fractions and bounded solver settings. Optional `temperature_K` and `total_pressure_bar` must match the reviewed conditions. Each supported site type has its own unit fractional inventory. The verified native syntax supports reversible equations and singly bound species. Unverified forward-only syntax, unequal site-density normalization and multidentate species require further native evidence.

```powershell
python -m scripts.baseline_mkm.single_point prepare RUN NETWORK.json DATASET.json CONFIG.json H7.sqlite TICKET_ID MATLAB.exe
python -m scripts.baseline_mkm.single_point status RUN
python -m scripts.baseline_mkm.single_point execute RUN REVIEWED_DECISION.json
python -m scripts.baseline_mkm.registration RUN REVIEWER BATCH.json
python -m scripts.registry_write plan --db ISOLATED.sqlite --manifest BATCH.json --output REGISTRY_PLAN.json
```

Use a fresh RUN path. The ticket reader opens the existing H7 database read-only and requires a bound question. The development benchmark uses a labelled synthetic H7 fixture. The status projection exposes the scientific quantities, stages, missing evidence and artifact paths. Its `ticket_handoff` body fits the Supervisor's manual `/api/tickets/handoff` interface. The authenticated viewer owns publication of the note. A qualified run waits for a separately supplied explicit decision. The reviewer checks `plan.json` and the generated model, and supplies the following fields.

```json
{
  "format": "mkm-execution-approval/1",
  "DECISION": "approve",
  "ALLOWED_ACTIONS": ["RUN_CATKINAS_SINGLE_POINT"],
  "question_id": "<existing question_id>",
  "reviewer": "<reviewer identity>",
  "state_sha256": "<exact hash from AWAITING_APPROVAL.json>",
  "source": {"path": "<absolute path to approval evidence>", "sha256": "<source SHA-256>"}
}
```

Execution rechecks the ticket and the plan, snapshots, tool hashes and native bytes. A write-once READY receipt reserves a single invocation. After interruption, inspect status and preserved native files before deciding whether another run is needed. The solver has a 210-second wall limit. An accepted point has a result, a terminal receipt and hashes for the MAT, full log, input echo and console. Numerical convergence, execution, approval and scientific scope are independently reported.

For a declared turnover, supply signed integer `overall_stoichiometry` keyed by gas species ID. The validated gas rates must agree with one reaction extent. `turnover_basis="one_event_per_reference_site"` enables a TOF for that normalization. `selectivity_products` declares the molar product set. Undefined quantities remain null. Coefficient units follow gas order. Fluxes are events per reference site per second.

Registry registration uses the existing plan, reviewed approval and apply sequence. The derived scalar rows are candidates with source-bound normalized evidence. Benchmark registration belongs in an isolated database. See the [Phase 3.0 report](../../reports/multiphase/phase3_0/completion.md) for the verified example and its limits.
