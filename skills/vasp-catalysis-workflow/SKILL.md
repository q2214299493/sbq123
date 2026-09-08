---
name: vasp-catalysis-workflow
description: Route this project's VASP catalysis work through repository state and bounded scientific modules, including adsorption, unified TS strategy, frequency, job monitoring, and failure diagnosis.
---

# VASP Catalysis Workflow

Use this skill as a thin router. Do not duplicate module procedures or reconstruct state from chat memory.

## Start

1. Read `AGENTS.md`, the required project-state files, and the relevant module README.
2. Verify calculation inputs, outputs, and live scheduler state before reporting facts.
3. Follow `configs/skill_routing.yaml`.

## Execution Backends

- Follow `configs/execution_backends.yaml` for every remote handoff.
- AQCat25 on `BUCT(sbq)` may accelerate adsorption candidates and TS/path
  candidates, but its predicted values are not VASP results.
- Only `sunboquan-codex` runs adsorption VASP calculations, static force
  labels, NEB/CI-NEB/DIMER, frequencies, and displacement calculations.
- GPU outputs return to `work` for review; direct GPU-to-VASP transfer and
  automatic submission are forbidden.

## External Evidence

- `catalysis-data-retrieval` is the only pre-calculation external structure/path/data retrieval layer.
- For adsorption motifs only, `NO_WHITELIST_MATCH` may trigger the controlled authoritative-journal fallback owned by `catalysis-data-retrieval`; a usable whitelist match stops that fallback.
- Official VASP/VTST documentation may be checked for software syntax and method behavior.
- Retrieved records remain candidates until the owning scientific module accepts transferability.

## Route

- Convergence: `modules/convergence_workflow/`
- Adsorption/endpoints: `modules/adsorption_workflow/`
- NEB/CI-NEB/DIMER strategy: `modules/transition_state_search/`
- Frequencies and TS grading: `modules/ts_vibrational_validation/`
- INCAR recommendations: `modules/incar_custodian/`
- Job/file/result tracking: `modules/calculation_registry/`

Never submit, stop, rebuild, or accept a scientific result merely because a routing or helper skill ran successfully.
