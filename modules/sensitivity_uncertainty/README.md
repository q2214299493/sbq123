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

# Sensitivity and Uncertainty

## Purpose

Propagate uncertainty in DFT energies, barriers, prefactors, coverage effects, and reactor parameters and identify the calculations that most need refinement.

## Entry Gate

- functioning kinetic or reactor model
- justified parameter distributions or ranges
- traceable baseline results

## Outputs

- sensitivity/DRC rankings, uncertainty bands, robustness checks, and prioritized next calculations

## Done Criteria

Main conclusions have uncertainty bounds and robustness checks, and influential parameters map to prioritized follow-up calculations.

## Scientific priority engine

Run these commands from a source checkout. All outputs are recommendations or read-only inventories.

```text
python -m scripts.scientific_priority benchmark OUTPUT
python -m scripts.scientific_priority inventory data/project_registry.sqlite3 OUTPUT/fe110_inventory.json
python -m scripts.scientific_priority rank PACKET.json OBJECTIVE.json OUTPUT [--registry REGISTRY.sqlite3] [--tickets H7.sqlite]
python -m scripts.scientific_priority review OUTPUT/proposals DECISION.json
```

### Data and architecture

The generic rank entry accepts reviewed records with these sections. The benchmark adapter assembles an example from published artifacts and the labelled fixture in `tests/fixtures/multiphase/priority_benchmark.json`. The adapter for this particular benchmark owns the Ni/Cu identifiers. The scorer consumes arbitrary reaction, site, facet, interface, model and phase identifiers.

| Packet section | Meaning and provenance |
|---|---|
| sources | Named JSON or YAML artifacts, each with a path relative to the packet and a SHA-256. The generic importer checks every hash and each accepted sensitivity's value_path (list of keys or array indices). For an external normalized record, its value field and scope travel together. A separate scope_record can point to reviewed metadata binding the raw value source SHA, parameter, observable, target and conditions. A raw scalar without a scope binding remains unverified. The report also binds the reviewed packet's SHA-256. |
| candidates | A unique ID, parent run, network/dataset/condition scope, physical parameter and type, reaction/species IDs, IS/TS/FS references, phase/surface/site context, target hashes by role, method protocol, model version and evidence need. The importer verifies the parent network digest and reaction, species, surface, phase, interface and site membership. Without a matching network it defers scientific attribution. A blocked candidate may retain null scientific fields. |
| metrics | Signed sensitivity, observable name and kind, parameter/type, status, target and full operating scope. Product and carbon-range selectivities require the actual target and an applicable derivative. Phase contrasts need their own observable evidence. Feed derivatives stay with their feed constraint. |
| reliability | Reviewed records keyed by model version, exact targets, parameter and protocol. Can carry held-out energy, force and barrier errors, ensemble spread, domain grade, training coverage, structure descriptor and separately justified prediction distribution. Missing fields remain null. |
| evidence, inventory_source, equivalences | Supply a reviewed operation-specific inventory and bind its source. Structure identity is exact SHA-256; other equivalence requires a reviewed pair, named rule, review digest and matching protocol. Role labels, targets and operation must agree. Include energies, geometries, force labels, frequencies, thermal records, pathways and model data under their applicable needs. A formula or a shared output filename cannot establish identity. |
| context_evidence | Auxiliary gas orders, operating constraints, network reachability and flux. A connectivity witness does not supply a selectivity gradient or quantitative pathway share. |

Registry discovery uses a read-only connection and exact `files.sha256` joins to calculation and result records. A file can be an input to a calculation. Such a hit requires assessment before a repeat recommendation. Optional `reviewed_registry_ids` records which matches were assessed in the review packet. Accepted evidence must still satisfy role, protocol and operation. Registry discovery covers indexed files; external evidence and equivalence reviews can be supplied without local calculation IDs.

`scripts.aqcat25_calibration.calibrate` reports empirical force errors, exact sample hashes, checkpoint and in/out-of-domain status. The importer consumes that existing report via `aqcat25_source`. The checkpoint and sample identity must match; force RMSE is retained in eV/Å. The same-structure MLIP benchmark and MatRIS validation report relative-energy RMSE in eV and force component RMSE in eV/Å. A reviewed normalized record can supply these fields. A force error is not converted into a barrier uncertainty. An incompatible or absent calibration leaves the parameter distribution unavailable. A descriptor comparison can supply scaled Euclidean nearest-neighbour distance over a common feature definition; its interpretation depends on training-set coverage.

The existing TS Strategy Engine's `compose_strategy` output can be supplied as `strategy_source`. For an existing path, `path_quality_source` accepts the NEB Agent's path quality evidence. Target identity and family remain necessary and an electronic or underresolved-path failure is a blocker. Priority review does not create endpoints, select images or construct a path. An approved TS proposal goes to `scripts.ts_strategy_engine.execution_gate` for a fresh decision.

The optional `spc_source` refers to the external Scientific Problem Compiler's already-imported Phase 3A ExecutionProposal. When supplied, the installed SPC model validates its planning contract; source plan, context, export, approval and capability references enter the proposal. The compiler's trust/import validation stays upstream. The existing H7 `ticket_binding` reads an optional Ticket database in read-only mode and checks the question. The Ni/Cu parent uses the published fixture Ticket. New owner preflights must establish authority for the new task. Synthetic approvals route only to fixture review.

### Scoring and decisions

Use separate objective documents with an ID, kind, observable, scope, target where applicable, positive weights, positive reference scales, common cost unit and selected reliability metric. Supply a descriptor definition when weighting novelty. Absolute kinetic derivative and flux, scoped validation error, descriptor distance, target relevance, downstream impact, information value, evidence deficiency and interfacial site-type count can be selected independently. A benefit score is min(raw / scale, 1); a cost benefit is scale / (scale + cost). One unit and resource basis must be used within a comparison. The reliability dimension selects a specific error, calibrated energy spread, ensemble spread, or an explicit grade-to-score policy. The final score is the weighted mean. Normalized scores, raw values, contributions, missing-dimension bounds and Pareto layers accompany each result. A missing weighted or critical dimension defers the candidate. Changing the policy may make a partial record usable for a different objective.

For an energy parameter with a calibrated Gaussian prior, a documented expected posterior variance and squared error loss in log observable, local expected value of sample information is (sensitivity / kBT)² × (prior variance − expected posterior variance). Units are squared log-observable. This calculation assumes a locally linear response, one uncertain parameter and the specified decision loss. No monetary utility, joint covariance or selectivity distribution is inferred. In the synthetic demonstration the distribution, expected reduction, costs and prioritization weights are explicitly hypothetical.

A candidate can specify ordered evidence needs; the first uncovered need selects the operation. The scoring preference for missing evidence is relative to the supplied inventory. The benchmark also includes an already covered geometry and produces a reuse decision. A SHA-256-named proposal links the parent, structures, objective, cost, rationale and review. A decision supplies `proposal_id`, `reviewer`, `reason` and `decision` (approve, reject, defer or modify). A modification refers to a separately scored replacement for the same candidate. Resolve a deferred review with `after_defer` set to the first receipt's canonical hash. Each decision is immutable. Approval creates a non-runnable handoff for the owning workflow; native submission requires independent gate approval.

[Benchmark results and scientific limits](../../reports/multiphase/phase3_2_3/completion.md)
