# Scientific Workflow Modules

This directory separates the catalyst-agent workflow into bounded modules. Each module owns its inputs, scientific gates, outputs, database handoff, status, and done criteria.

`configs/skill_routing.yaml` is the canonical machine-readable map for routing,
ownership, and the location of each enforced rule set. Module READMEs explain
procedures but cannot override those configs; skills only route into modules.

The canonical workflow order and stage boundaries are in `docs/12_WORKFLOW_ARCHITECTURE.md`.

`configs/execution_backends.yaml` owns execution authority. The shared compute
pool contains three GPU servers (`BUCT(sbq)` / `MZ73`, `BUCT2`, `BUCT3`) and one
CPU server (`sunboquan-codex`, LSF). For every new compute task run
`python -m scripts.gpu_resources --include-cpu` before host selection; the
existing command without that option checks the three GPU servers only.
Prepared runtime paths and verification limits are in `docs/COMPUTE_POOL.md`.
The probe is read-only and reports SSH/work-directory checks, GPU/NVML and
Slurm resources where available, plus compact LSF host states and queues.
A failed or incomplete check leaves availability unknown; a snapshot does not
verify task software or reserve resources.

GPU files stay under each server's `/home/sbq/sbq/`. CPU files stay under the
configured account boundary or an existing reviewed task path. Before any job,
verify the task's software, model/input hashes, canonical write paths, scheduler
allocation, CUDA/GPU UUID inside that allocation, and host-bound execution gate.
Pool membership does not migrate a host-specific authorization or permit
submission, duplication, cancellation, or a change in scientific protocol.
General VASP/VTST remains on `sunboquan-codex`; explicitly authorized GPU-VASP
cases retain their own scoped backend. All results return through `work` and
the owning scientific gates.

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
