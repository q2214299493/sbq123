# Scientific Workflow Modules

This directory separates the catalyst-agent workflow into bounded modules. Each module owns its inputs, scientific gates, outputs, database handoff, status, and done criteria.

`configs/skill_routing.yaml` is the canonical machine-readable map for routing,
ownership, and the location of each enforced rule set. Module READMEs explain
procedures but cannot override those configs; skills only route into modules.

The canonical workflow order and stage boundaries are in `docs/12_WORKFLOW_ARCHITECTURE.md`.

`configs/execution_backends.yaml` separates execution authority. AQCat25 on
`BUCT(sbq)` accelerates both adsorption screening and TS-candidate work;
`sunboquan-codex` alone runs VASP/VTST. All transfers return through `work` for
the owning module's gates.

`calculation_registry`, `kinetic_data`, and `incar_custodian` are cross-cutting
modules. `state_handoff` owns repository task/history lifecycle events and
managed views; `git_versioning`, `memory_migration`, and project state files
provide continuity but do not make scientific decisions.

`catalysis_data_retrieval` is the single external-data owner before any new
calculation or externally seeded structure/path/parameter. It searches the
approved whitelist first and, for adsorption motifs only, may use
authoritative-journal literature after `NO_WHITELIST_MATCH`. Scientific modules consume its reviewed output and
do not implement independent literature/web search.

`fe_convergence_baseline` contains the validated alpha-Fe bulk package.
Corrected true Fe(110) work is owned by `convergence_workflow`.

`transition_state_search` owns the continuous endpoint-to-validation strategy.
NEB, CI-NEB, and DIMER are method choices inside that module; numerical NEB
helpers under `scripts/neb_agent/` are not a separate scientific authority.
TS endpoint implementation lives under `scripts/ts_endpoint/`; the historical
root-level `modules.ts_endpoint_*` and `modules.structure_purpose_manager`
imports are compatibility aliases only. New production code must follow the
`scripts.ts_endpoint` dependency direction.

Module status is authoritative only in `docs/06_MODULE_MAP.md`.
