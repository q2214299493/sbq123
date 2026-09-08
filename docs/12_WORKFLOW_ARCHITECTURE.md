# Catalyst-Agent Workflow Architecture

Routing, ownership, and rule-source locations are authoritative only in
`configs/skill_routing.yaml`. This document explains the data flow and cannot
override machine-enforced configs.

## Principle

Each scientific stage is independent, evidence-gated, and traceable. Completion of one stage does not imply acceptance by the next stage.

```text
Whitelist BM25+semantic retrieval (Top 5)
  -> convergence and method definition
  -> CARE species/network handoff
  -> adsmind_lite adsorption-configuration pre-screening
  -> AQCat25 GPU adsorption pre-relaxation and candidate ranking
  -> VASP adsorption relaxations/final statics and accepted endpoints
  -> transition-state strategy engine: fingerprint and template/rule strategy
  -> GPU TS acceleration: MatRIS ML-NEB with optional standard Sella, AQCat25 checks or the separate BA-Sella branch
  -> reviewed exact-structure VASP force labels, model-error assessment, optional model update and held-out validation
  -> strategy selection from the reviewed complete GPU path
  -> VASP/VTST calculation: adaptive static force labels, optional micro/ordinary/CI-NEB, DIMER, frequency and displacement evidence
  -> source-method frequency, imaginary-mode and connectivity validation
  -> thermal and free-energy corrections
  -> balanced reaction network
  -> baseline MKM with CATKINAS
  -> coverage-dependent MKM with CATKINAS, or surface KMC with Zacros 4.0 when justified
  -> reactor simulation
  -> sensitivity and uncertainty analysis
```

The calculation registry spans every stage and records jobs, files, results, provenance, and review decisions. It never replaces scientific judgment.

The cross-cutting `incar_custodian` layer may recommend numerical input changes only after the owning scientific module passes its geometry/path/mode gate.

The cross-cutting `catalysis_data_retrieval` layer is the only external
structure/path search entry point. It is whitelist-first; adsorption motifs may
use its authoritative-journal fallback only after `NO_WHITELIST_MATCH`. It
supplies candidates and provenance but never accepts scientific transferability.

Local post-processing software is a consumer layer, not a scientific authority. CATKINAS consumes validated mean-field MKM inputs; Zacros 4.0 consumes validated surface-KMC lattice/event/rate inputs. Neither tool may receive unregistered DFT energies, replace TS A/B/C validation, or bypass the kinetic-data provenance gate.

## Execution Backends

| Layer | Machine/repository | Owns | Must not do |
|---|---|---|---|
| Orchestration | local `work` repository | evidence gates, contracts and hashes, structure/path review, handoff, registry, scientific acceptance | relabel GPU predictions as DFT evidence |
| GPU acceleration | `BUCT(sbq)` / `MZ73`, under `/home/sbq/sbq/` | AQCat25/MatRIS inference; adsorption and endpoint relaxation; ML paths; optional standard Sella or the separate BA-Sella branch; reviewed force or energy/force fine-tuning | run VASP, bypass retrieval, prove adsorption stability/global minimum, claim a TS or reportable energy |
| First principles | `sunboquan-codex` | VASP adsorption relaxations/final statics and VASP/VTST energies, forces, NEB/CI-NEB/DIMER, frequency/displacement calculations | accept an unreviewed GPU candidate or run AQCat training |

All transfers follow `configs/execution_backends.yaml`. GPU candidates return
to `work`; only a reviewed and preflight-passing package can be handed to the
VASP server. No direct GPU-to-VASP transfer or automatic remote submission is
allowed.

## Using the strategy-improvement extension

The existing transition-state engine remains the entry point. See
[`LEARNING.md`](../modules/transition_state_search/LEARNING.md) for exact CLI
inputs and [`SELLA_BRANCH.md`](../modules/transition_state_search/SELLA_BRANCH.md)
for the candidate-to-label-to-rerun handoffs.

| Practical need | Implemented behavior | Acceptance boundary |
|---|---|---|
| Start from the current workflow | Capture actual inputs, policy/code hashes and current checkpoint evidence as the baseline | A baseline is a frozen record, not a fresh model or a restarted calculation |
| Avoid repeating a known failure | Store immutable reviewed outcomes and block exact-input retries for confirmed deterministic failures | Unknown causes remain advisory; a changed input or model requires a new bound attempt |
| Improve one strategy choice | Propose one supported field change with evidence and a bounded attempt budget | Proposals cannot relax scientific gates or authorize remote execution |
| Optionally refine a path peak | Use the same MatRIS calculator with standard Sella after the complete ML path passes its prerequisites | Output is a predicted candidate; preserve the original path |
| Try Sella before full NEB convergence | Reuse a saved rough path and review one local segment/peak per bounded request; global multi-peak paths are allowed | Preserve geometry gates and the full parent; new checkpoint requires renewed segment review; see `modules/transition_state_search/SELLA_LOCAL_PEAK.md` |
| Decide whether to tune the model | Compare exact-structure predictions with accepted VASP labels, then apply existing held-out and retention gates | Path failure alone does not justify training or checkpoint promotion |

The local orchestration, failure memory and candidate handoffs are covered by
offline integration tests. Real CPU Sella tests use an analytic saddle and run
in CI via `python -m pip install -e ".[dev,neb,sella]"`; they require neither
cluster credentials nor a model checkpoint. The bounded MZ73 MatRIS/Sella
component run (job 1509) is documented in `SELLA_BRANCH.md`.

A complete Sella/VASP loop and a same-budget performance comparison on the
current Fe reaction remain unvalidated. Neither software tests nor the short
GPU component run establish improved TS success rates or reduced DFT cost.
Production use continues to require reviewed inputs, available backend/model
dependencies, explicit execution authorization and the owning module's gates.

Git versions the orchestration source, configuration, schemas and documentation.
Runtime outputs, local state events, model weights and licensed VASP inputs are
separate evidence assets; a source checkout alone is not a backup of an active
calculation. The sibling `scientific-problem-compiler` Git repository is not
part of this `work` architecture snapshot.

## Module Boundaries

| Module | Owns | Does not prove |
|---|---|---|
| Convergence | transferable numerical settings for a defined system | chemical validity |
| AdsMind Lite | geometric site dictionary, evidence-selected motifs, validation, slip/dissociation flags, deduplication, selected VASP-ready structures | global minimum adsorption states or final adsorption energies |
| Adsorption | relaxed stable states, reference energies, endpoint candidates | a reaction path or TS |
| Transition-state search | reaction fingerprint, template/rule strategy, continuous NEB path, CI-NEB/DIMER refinement, and learning record | first-order-saddle acceptance without source-method vibration validation |
| TS vibration | imaginary-mode count, assignment, geometry, and A/B/C grade; optional connectivity diagnostics | thermodynamic corrections by itself |
| Thermochemistry | ZPE, enthalpy, entropy, and Gibbs corrections | reaction-network balance |
| Reaction network | atom/site-balanced elementary steps and barriers | kinetic performance |
| CATKINAS MKM | mean-field rates, coverages, TOF, selectivity, and DRC | spatial correlations or KMC validity |
| Zacros KMC | event statistics, spatial effects, coverage evolution, and TOF | reactor conversion without a reactor model |
| Reactor | conversion and selectivity under operating conditions | robustness without uncertainty analysis |

Repository lifecycle authority belongs to immutable events under
`modules/state_handoff/events/`. `docs/06_MODULE_MAP.md`,
`docs/02_CURRENT_STATE.md`, and `tasks/current_task.md` are human-facing
projections of reviewed events. Scheduler output, calculation files, final
structures, owning scientific modules, and the calculation registry retain
their existing evidence authority; state-handoff events cannot override them.
