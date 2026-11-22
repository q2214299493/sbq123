---
document_class: HISTORICAL_SNAPSHOT
as_of: '2026-11-22T00:00:00+08:00'
as_of_scope: Stage R.1 audit date in Asia/Shanghai
source_scope: SBQ123 publication source and archived evidence, focused offline Windows verification
source_version: 335008915ebcb227cc5012054df105a2e0ac4404
source_version_role: Requested production-code audit baseline
source_branch: codex/multiphase-phase0-integration
published_evidence_checkpoint: dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73
evidence_kind: HISTORICAL
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Native engines and Stage A/B implementation

## CATKINAS and Zacros independence

| Concern | CATKINAS / MKM | Zacros / KMC |
| --- | --- | --- |
| Input generation | `native.render` maps aliases, vacancy slots and activities. `network_mapping` and `mapping_scope` check roles and representation. `kinetic_parameters.export.catkinas` maps fixed-condition law/barrier inputs. | `surface_kmc/lattice.py` builds a periodic typed graph from vectors/basis/translations. `native.py` maps site/species and dentation, matches event embeddings, emits mechanism and clusters, and seeds ordered legs. `export.zacros` maps qualified local events and directional prefactors/barriers. |
| Rate output and qualification | `results.read_single_point` reads MAT arrays/log labels and gas flux. `single_point_result` reconstructs rates/sites and checks mass action, residuals and steady-state checks. `rate_adapter.adapt` binds archived inputs/output and creates V2.1. | `trajectory_statistics` parses process/species records and aligned windows. `rate_adapter.adapt` verifies ZIP members, reconstructs counters/flux and separately binds lineage for restart. `native_model.with_checkpoint` binds model bytes and exact checkpoint. |
| Permission | `single_point.prepare/preflight/execute` bind ticket, exact plan, configured runtime, inputs and explicit action. DRC and sensitivity coordinate separately approved invocations. `native_model` has no execution. | `zero_event_review.prepare_request/check_reviewed_action` validate exact control, executable, plan and affirmative external review. No general Zacros launcher or consumption API exists in `surface_kmc/`. External wrapper recorded the consumed claim for this one run. An opt-in benchmark test can directly start the binary (R1-007). |
| Native witness | Archived Ni/Cu closed cycle and separate Phase 3.0 point validate distinct a priori coefficients, native MAT/log output and site/source closure for the demonstrated topology. Bounded DRC and condition studies have their own receipts. | Archived synthetic Ni/Cu seed/dentation and typed edge cases, cluster energy checks, fixed-seed continuation, and finite-window rate evidence demonstrate specific Zacros 4.0 capabilities. Matching a failed native exit requires reading termination evidence. |
| Unverified scope | `Q1x2_CO2` is notation evidence. Footprint spanning inventories with unequal capacities remains unsupported in the adapter. Neither arbitrary cross-phase elementary reactions nor oxide native results follow from Ni/Cu. | No successful native run of the seven-node acid/O graph. General B.2.2.2 transfer, four-node elementary events and three-phase contacts require a specific typed graph, event and kinetics qualification. |

The only engine cross-import paths observed in the baseline inventory are through `scripts.native_model.assemble`. Lines 13–26 import both renderers, CATKINAS mapping scope and both offline parser entry points before using the selected engine. CATKINAS `single_point` and `rate_adapter`, and Zacros `rate_adapter`, consume this dispatcher. A targeted import-blocking probe confirmed that CATKINAS requests `scripts.surface_kmc.native` and Zacros requests `scripts.baseline_mkm.native` even before dataset validation. This is a software dependency, separate from process independence. No call from one adapter launches the other native executable, and neither engine requires the other's results for the paths reviewed.

Both engines consume qualified structural/network and fixed-condition parameter artifacts and emit the shared V2.1 boundary. The ADR specifies MKM only, KMC only, both in parallel, or either sequence with their own decisions. Runtime SPC dispatch for those choices is absent. Existing comparison reports are optional, artifact-based and scope-dependent. Pair/cell normalization, observable definition, directional flux, pressure/temperature, equilibration and sampling uncertainty must be comparable before drawing a discrepancy conclusion. Reactor can consume a later qualified macroscopic handoff without triggering either engine. [Adaptive engine selection ADR](../../../docs/decisions/adaptive_mkm_kmc_optional_reactor.md)

## Stage A integration

| Stage | Current code/evidence and remaining boundary |
| --- | --- |
| A.1 / A.2.1 | Architecture and legacy evidence are historical inputs. MKM registration delegates Registry batch acceptance/validation and emits a staged request. No second Registry mutation owner was found in the MKM path. |
| A.2.2 | Native renderer helpers take dependencies from `native_inputs.py`, removing reverse imports into assembly. The common assembly dispatcher still creates horizontal engine coupling at runtime. |
| A.2.3 | DRC pair evidence and planning/execution/report files and shared sensitivity reporting have bounded responsibilities. Retain normal CLI paths and exact native plan/receipt checks. More splitting lacks a current behavioral need. |
| A.2.4 | Readiness distinguishes implementation, test coverage, scientific qualification and production validation within the worktree's evidence scope. Historical development/publication views remain historical. |
| A.2.5 and A.2.6 | Raw VASP frequency observations have one owner, and TS grade and thermochemical interpretation retain distinct owners. A.2.6 archived regression proof is scoped. This audit rechecked the relevant parser/boundary tests. |

[Stage A integration checkpoint](../../multiphase/stage_a2_6/completion.md)

## Stage B assessment

| Stage | Current reusable capability, fixture or audit utility | Consumer and limit |
| --- | --- | --- |
| [B.1.1](../../multiphase/stage_b1_1/completion.md) | V2.0 schema, read-only validator, explicit missing directions and native denominators | Legacy separate from V2.1. Current adapters emit 2.1.0. Preserve revision-discriminated validation |
| [B.1.2](../../multiphase/stage_b1_2/completion.md) | V2.1 and reusable dimensional normalization, typed basis/bridge evidence and coefficients | Real adapter output consumer is validator and CLI. No production Reactor or automatic comparability consumer |
| [B.1.3](../../multiphase/stage_b1_3/completion.md) | Shared stoichiometric matrix/projection, conservation residual and covariance routines | Source projection consumed by both adapters/validation and MKM reconstruction. Residual/covariance functions have tests, with no matching audit-detected production workflow call |
| [B.1.4](../../multiphase/stage_b1_4/completion.md) | Two native result adapters plus thin shared builder. Archive readers currently know benchmark receipt/layout details | Useful replay entry points, not evidence that an arbitrary native run or format is eligible. No default promotion of outputs |
| [B.1.5](../../multiphase/stage_b1_5/completion.md) | Independent archive oracles and ten V2.1 replays, two CATKINAS and eight Zacros | Regression and qualification evidence. Sampling/qualification sidecar remains essential. Keep tests distinct from runtime |
| [B.2.1](../../multiphase/stage_b2_1/completion.md) | Reusable molecular footprint/coverage accounting and per-inventory closure. Synthetic unequal inventories provide independent fractions and bounds | Called by MKM coverage analysis, general accounting has no engine-independent procedure yet. Ni/Cu and synthetic observations have different evidence classes |
| [B.2.2.1](../../multiphase/stage_b2_2_1/completion.md) | Material/phase/surface/interface identity, ownership and state binding | Shared validation and network build use these constraints. Real systems need reviewed provenance and input compatibility |
| [B.2.2.2](../../multiphase/stage_b2_2_2/completion.md) | Shared `interphase_transfer` validates donor/acceptor, reactant/product identity, separate inventories and conservation | Used by structural/network checks and CATKINAS mapping. Synthetic transfer proves contract only. Next engine step depends on actual local event and rates |
| [B.2.2.3](../../multiphase/stage_b2_2_3/completion.md) | Shared cross-phase elementary type, participation and TS-role checks. Builder keeps gaps and qualification | Contract can express the declared events. No native support by inference from valid JSON |
| [B.2.3.1](../../multiphase/stage_b2_3_1/completion.md) | Reusable CATKINAS mapping/qualification, including scoped Ni/Cu backward compatibility | Real mapper consumer exists in input preparation. Unsupported topology and false endpoint/parameter bindings fail before execution |
| [B.2.3.1.1](../../multiphase/stage_b2_3_1_1/completion.md) and [normalization follow-up](../../multiphase/stage_b2_3_1_1_a/normalization_analysis.md) | One-off notation and normalization audit, placeholder `oxide_CO2.m.in`, strict block for unsupported dentation | Keep fixtures/test oracles. For two molecules in inventories 4 and 3, vacancy fractions are 1/2 and 1/3 with one population. A name or equal-capacity example cannot establish the native divisor `D`, or the required relation `4(1−vA)=3(1−vB)=n` |
| [B.2.3.2.1](../../multiphase/stage_b2_3_2_1/completion.md) | Source- and archive-backed Zacros capability mapping, plus regressions | Bounded typed lattice, seeds/restart and explicit local pattern evidence. Archive reports remain scoped |
| [B.2.3.2.2](../../multiphase/stage_b2_3_2_2/completion.md) | `bridge_topology` plus seven-node fixture, typed open graph and bipartite maximum matching | Six candidate pairs when empty, two admissible initial seeded bridges, two remaining candidate placements share a site, one further simultaneous molecule, maximum three. CLI consumers belong to the fixture chain. Generic matching has no production consumer here |
| [B.2.3.2.3](../../multiphase/stage_b2_3_2_3/completion.md) | `bridge_input` and manifest-bound offline lattice, state and directed pattern templates | Offline readback only. Numeric inputs incomplete at that checkpoint. Keep byte-for-byte regression and independent graph oracle |
| [B.2.3.2.4](../../multiphase/stage_b2_3_2_4/completion.md) and [subsequent native receipt](../../multiphase/stage_b2_3_2_4/native_acceptance/native_acceptance.md) | `oxide_control` and `zero_event_review`, five concrete synthetic input members plus independently calculated reference and request. Archive now shows the one attempted initialization failed | Old offline checks passed an integer-form `temperature 400`. The Zacros simulation reader reported fatal code 1002 with exit 0. Later readers, graph matches, energies, propensities and checkpoint were unobserved. Seven additional integer-form real token candidates derive from archived vendor field checks, rather than measured extra failures. The one-use permission was consumed |

## Seven-node boundary

Keep the topology, manifest, ordered seed ledger, two directed elementary patterns, synthetic rate law and failure receipt as a capability fixture. Retain current callable audit utilities and their regression tests for reproducibility. If a future approved cleanup relocates `bridge_topology`, `bridge_input`, `oxide_control` and `zero_event_review`, check documented CLI consumers first. Only a separate generic consumer can justify extracting tested finite typed graph operations. Lexical serialization of native real fields is already a useful adapter-level responsibility because two paths render the same language. No new oxide framework or alternate execution manager is needed.
