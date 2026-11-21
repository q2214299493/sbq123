# Adaptive MKM/KMC and optional reactor modeling

**Status** · ACCEPTED DESIGN DIRECTION, 2026-11-21

**Project** · SBQ123 Multiphase Catalysis Agent

## Shared evidence and independent engines

CATKINAS supplies mean-field microkinetics (MKM). Zacros supplies spatial kinetic Monte Carlo (KMC). Both consume validated catalyst, phase, surface and site definitions, species and reaction networks, thermochemistry, kinetic parameter evidence and operating conditions. These inputs carry provenance and validation records. Each engine retains its native configuration, execution plan, qualification, approval, execution receipt, result validation and recovery. Either can run on its own.

## Planning and cross-validation

The Scientific Problem Compiler (SPC) selects a route using the research objective, requested observables, model applicability, available evidence, computational cost, existing results and user constraints. The scientific engine owns the calculation. The following choices are independent of the order in which the software capabilities are developed.

| Planned route | When to use it |
| --- | --- |
| MKM only | A mean-field model can answer the question with the available evidence. |
| KMC only | The question needs a spatial observable and the lattice and event model are qualified. |
| Both in parallel | Both results serve the objective and the plans can proceed independently under their respective approvals. |
| Both in sequence | There is a scientific reason for the order. Either engine can run first. |

A first result can resolve the question. If it suggests spatial effects, exposes a model limitation or leaves a discrepancy unresolved, SPC may propose the other engine. That proposal requires its own qualification and execution approval.

When results from both engines are available, cross-validation is optional. Before comparing an observable, check operating conditions, reaction definitions and direction, site mappings, normalization denominators and the observable definition. Compare only the quantities for which those checks establish equivalence. For example, a turnover per site pair and a turnover per lattice cell need a documented mapping. Other observables can still be reported independently. Interpret a difference in light of the mean-field and spatial assumptions, correlations and relevant numerical or sampling uncertainty. A difference alone does not establish a software failure.

## Reactor handoff

Reactor is an independent, optional capability for questions that require reactor-scale predictions. SPC may propose an isothermal continuous stirred-tank reactor (CSTR) or plug-flow reactor (PFR) as an initial target. It can use existing validated macroscopic kinetic source terms. The handoff must identify the species sources, units, normalization, operating conditions and applicability to the requested reactor conditions. A per-site rate needs evidence for its conversion to the physical balance basis. Missing conversion evidence holds the affected reactor prediction open while intrinsic kinetic results remain available. Fixed-bed models, energy balances and transport coupling are possible future extensions.

## Rate contracts and scientific authority

B.1 preserves the native rate normalization denominator, derives species sources from stoichiometric reaction progress and isolates legacy and new task entry points through strict versioning. The shared V2 output contract permits engine-specific native inputs. Contract validation checks the representation and its arithmetic. Scientific acceptance requires the owning module's review of the evidence, including after a solver converges. Existing execution gates govern every proposed run.

[Shared kinetic data and V2 rate contract](../../modules/kinetic_data/multiphase_contracts.md) · [MKM](../../modules/baseline_mkm/README.md) · [KMC](../../modules/surface_kmc/README.md) · [Reactor](../../modules/reactor_simulation/README.md)
