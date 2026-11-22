# R.2.5 limited repair qualification

All four repairs satisfy the limited R.2 acceptance criteria. All eight required regression groups passed their offline checks. Windows full validation passed with one explicitly gated test skipped. Linux full validation retains one failure independently observed on production. The qualification branch is suitable as a V.1 development baseline with that recorded exception.

## Integrated baseline

| Remote branch under `codex/` | Verified head |
| --- | --- |
| multiphase-phase0-integration (production) | `dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73` |
| stage-r2-1-network-binding | `5fb520a6eb5d4161949edef78bd3b86ce0585c05` |
| stage-r2-2-safe-only | `0e36efa0f1bc75055a394c5f235b4956e9a3c77f` |
| stage-r2-3-zacros-safety | `0a02c230207ff66352867091fe66b1f072ff536c` |
| stage-r2-4-engine-conservation | `b272db81b403704d61c8936403b9d805e93dde4a` |
| stage-r2-5-release-qualification (qualified implementation) | `e944ee7f1c228dc1b59d5a55cc78488003d9980a` |

R.2.1 forked from `335008915ebcb227cc5012054df105a2e0ac4404`. Merge `b8f2640a` has production and R.2.1 as its two parents. R.2.2, R.2.3, R.2.4 and the qualified implementation descend successively from this merge. Git ancestry checks and remote branch lookups agreed. The earlier normal merge already integrated the four repairs. Qualification used independent Windows development, publication and production-control worktrees. The desktop development checkout and the original repair worktrees were outside the change set.

## Reproduced integration defect

R.2.2 changed `tests/test_state_manager.py`, one of the inputs to the capability readiness report. Both generated views still contained the old aggregate input digest. The deterministic regeneration test passed at production on Windows and in both production engineering CI jobs. It failed at R.2.4 in an isolated Windows checkout and in Linux CI. Two independent generations agreed with each other.

The existing `python -m scripts.generate_capability_readiness --root .` regenerated the current views. The JSON changes only the State Manager test digest and aggregate input digest. Markdown changes only the aggregate digest. All capability rows, projection bindings, maturity assessments and archived reports compare equal. All 29 governance tests passed after regeneration. The repair changes three lines of derived report data. Runtime code, tests and the generation policy have identical blobs at R.2.4 and R.2.5.

## Combined architecture review

| Boundary | Verification |
| --- | --- |
| V1/V2 contracts and V2.1 network binding | The existing shape, version and dimensional checks serve network-free callers. Explicit qualification reads and hashes the supplied bytes and checks the network-bound rows. The adapter builder and consumer reuse `validate_bound_rows`, which calls the existing catalog, scope and direction rules. Malformed row bindings use `ValueError`. The existing CLI and version-boundary tests cover legacy behavior. |
| State Manager | The safe-only branch builds the preview and verifies evidence before the cache, receipt reuse, approval and apply paths. Isolated-store tests compare evidence, event, proposal and projection state. The explicit review, apply and separately authorized receipt workflows still pass. |
| Native formats and authority | Real-valued control fields use the validated finite value at serialization. Integer-only fields retain their type checks. Ordinary pytest supplies no reviewed run. The tests cover poisoned inherited environment values, explicit denied decisions, preparation with inert executables and archived replay. |
| Engine assembly | Four clean-interpreter selections cover MKM, KMC and both orders of explicit dual use. Imports of every unselected adapter submodule are blocked during the single-engine probes. Manifest and rendered file bytes match the fixtures. An unsupported selector retains `KeyError`. |
| Conservation | The strict bundle, draft network and signed residual callers all use `stoichiometric_totals` for weighted elements, charge and occupied sites plus vacancies. Per-caller metadata requirements and missingness remain distinct. Molecular coefficients, free-site sources, directional flux and native normalization retain their own units and rules. |
| Dependency direction | The maintained-source AST cycle check includes function-local imports. The architecture suite checks shared infrastructure, domain/CLI boundaries and the native assembly layer. Shared contracts import without either adapter. The nine changed runtime files contain one new functional module for row validation. The combined diff adds no manager, service, schema version or scientific parameter. |

## Offline regression

Windows ran `python -m pytest -o addopts= -q --tb=short -ra` from each checkout with JUnit output outside the repository. The interpreter was Anaconda Python 3.13.9 with pytest 8.4.2. No native invocation option was supplied. Ubuntu 24.04 CI ran the repository workflow with Python 3.11 and the dev, NEB and Sella test dependencies. The Linux command was `python -m pytest -o addopts= -q`. Both Windows and Linux ran full discovery. Windows Ruff on `scripts modules tests` and `py_compile` on the combined repair's changed Python files passed.

| Checkout and environment | Passed | Failed | Skipped | Outcome |
| --- | ---: | ---: | ---: | --- |
| Production, Windows targeted control | 2 | 0 | 0 | Both deterministic readiness and pilot-plan identity pass. |
| Production, Linux full | 2,787 | 1 | 10 | Historical DRC pilot-plan identity. [Production CI](https://github.com/q2214299493/sbq123/actions/runs/45005145449) |
| R.2.4, Windows full development | 2,866 | 1 | 1 | Newly introduced readiness digest mismatch. The pilot plan passes. |
| R.2.4, Linux full | 2,864 | 2 | 2 | Readiness digest mismatch and historical DRC issue. [Repair baseline CI](https://github.com/q2214299493/sbq123/actions/runs/45010150377) |
| R.2.5, Windows full publication | 2,867 | 0 | 1 | All executed tests passed in 17 min 42 s. |
| R.2.5, Linux full | 2,865 | 1 | 2 | Only the historical DRC mismatch remains. [Qualified implementation CI](https://github.com/q2214299493/sbq123/actions/runs/45010740101) |

The Linux failure is `tests/test_mkm_drc_batch.py::test_pilot_plan_is_reproducible_without_native_execution`. The archived minus member has ID `minus-ce3d2031cc1ebec3`. Reconstructing the child in Linux CI yields `minus-d37e15be163218ff` on production, R.2.4 and R.2.5. The same case passes locally on Windows. The underlying platform-dependent cause is unresolved. The archived plan and its test remain intact.

In the qualified implementation's CI, both wheel jobs passed. Engineering CI passed on Windows (284 tests) and Ubuntu (283 passed, one platform skip). The full Linux job remains red. The expected Windows full-suite skip is `test_live_closed_cycle`, which requires a reviewed native run and decision on the command line.

The following counts come directly from the qualified Windows full-suite JUnit test cases. Some groups overlap. Module names omit the `tests/test_` prefix and `.py` suffix.

| Group | Passed | Skipped | Selection |
| --- | ---: | ---: | --- |
| A. V2.1 network binding and ten-output replay | 32 | 0 | `rate_network_binding` and `b1_contract_acceptance::test_ten_outputs_and_both_qualification_files_replay_byte_for_byte` |
| B. State Manager, safe-only and Registry | 185 | 0 | `state_manager`, `b4_state_governance`, `state_log_projection`, `state_sync_repository_items`, `state_sync_task_ownership`, `state_sync_safe_only`, `registry_schema`, `registry_write`, `registry_excel_promotion`, `b4_registry_governance` |
| C. Zacros serialization, native receipts and execution authorization | 107 | 1 | `zacros_zero_event_control`, `zacros_zero_event_native_receipt`, `native_advanced`, `mkm_single_point` |
| D. Isolated engine imports, common arithmetic and import graph | 47 | 0 | `native_imports`, `stoichiometric_sources` and the native input dependency and acyclic runtime graph cases in `b5_architecture_boundaries` |
| E. B.1 rate, unit, source-term and normalization contracts | 219 | 0 | `rate_dimensions`, `rate_output_v2`, `b1_contract_acceptance`, `kinetic_parameters` |
| F. B.2 identity, inventory, transfer and elementary reactions | 262 | 0 | `multiphase_contracts`, `reaction_network`, `inventory_accounting`, `multidentate_coverage`, `interphase_transfer`, `cross_phase_elementary`, `catkinas_oxide_multidentate_audit`, `oxide_bridge_topology` |
| G. CATKINAS and Zacros replay, oracles and model boundaries | 85 | 0 | `native_rate_adapters`, `b1_native_acceptance`, `catkinas_closed_cycle`, `zacros_bridge_input`, `native_model` and the ten-output B.1 replay |
| H. Fe(110) archive qualification, CLI and both blocked exports | 4 | 0 | `test_real_fe_blocked_no_invented_values`, `test_fe110_blocked`, `test_fe110_draft_matches_archived_scientific_evidence`, `test_cli_reproduces_versioned_fe110_artifact` |

## Scientific evidence

Independent adapter replay checked raw archive member and input hashes, reconstructed the ten V2.1 payloads, checked their identities and compared bytes with the checked-in outputs. Both combined qualification records also matched. The two CATKINAS payloads retain the reference-site-pair denominator and all eight Zacros payloads retain the simulation-cell denominator. The CATKINAS MAT and Zacros event-counter/lattice oracle tests provide independent numerical checks.

| Engine or source | Case or path | SHA-256 |
| --- | --- | --- |
| catkinas | `phase2_5_2` | `e1a71272fc19b0f8756e4fcb64ad7ef2e3b83eac9572290b27cef1005bc17e77` |
| catkinas | `phase3_0` | `eb73c3b756ad88316b792df4919c0e08cbe9e0967bcd4d6e2277a5eefcac2ec6` |
| catkinas | `qualification` | `9b8bb716277180587c32eb5cd0f4b90c3dfc32ce638a458d4a1717db18bac65d` |
| zacros | `mono` | `5d96357c05c3f5782f23818f0071330dd199b09e82e79b82f5d05eedf7d99367` |
| zacros | `dent` | `4fbd954adbfe88a1d65a8d40719ab56aca19db088029089b21f96e2720e1ecbf` |
| zacros | `full` | `dafa3b41d823c144b30be119690be1f1df50b9518958f5686e0f45c774ece404` |
| zacros | `interacting` | `73e1524fa096e0ffc6cef24c3e2638bdc497a195975e2b8dff67453be1fe075b` |
| zacros | `attractive` | `5e3d6a6708edb73208fe59cc3797b1d4bfbae6a044bbc8b4ae3ba0b0a9d08d44` |
| zacros | `continuous` | `f24c5f8b7def7aa89a95ccd0efd36f312084b1da09c5060d94e35df31aeaf330` |
| zacros | `split` | `f0c85072c95cc5c6a6de46fbe93411001fc271b30bd6c89b91193e7785e68f82` |
| zacros | `resume` | `c210a6448ae8fac95aa29d00717e2f40824e76daf539ed12f378fd4331cd6981` |
| zacros | `qualification` | `fa1577a131e850937cf5822cf8c2fc3f40bd5909c21ddb317cf990b4b20c70f5` |
| archive | `reports/multiphase/stage_b2_1/interface_validation.json` | `d50ff225f6f9c52361fca13920137720e4e5569bece453d7cd26fd6f4e8cbfe1` |
| archive | `reports/multiphase/stage_b2_1/oxide_validation.json` | `ab1c981802a6e01423c69656b1e6e2fef8e97b3bcb6d4ac3e673fe5181ed80ce` |
| archive | `reports/multiphase/ch_co_registry_mapping_20261119.json` | `5d8d7f3a4ebd90b5666bee4215b517f2f520f33e3adc2524c50f8d931e41dfbf` |
| archive | `reports/multiphase/phase2_2_chco_validation.json` | `3cb1440526b0e6386294100bbfe9a6e31c8d0c999850571f56ce99b322aa1789` |
| archive | `reports/multiphase/ch_co_intake_20261119.json` | `8c2b7561a9eeaa40ef3bd24d8b6ce69de58e416ef111b5bc4590a5e8d7caf8ef` |

The two coverage records and three Fe evidence files in the table also compared byte-for-byte to production Git blobs. The full `reports/multiphase` Git tree is `150e0850364fda4307b0cda10966f070c1c3eba5` at both production and qualification. The corresponding `configs` and `tests/fixtures/multiphase` trees also match. The reviewed R.2.3 corrected input remains a separate artifact.

The Ni/Cu replay gives 0.30 bridge and 0.50 top molecules, with occupied/vacant inventories of 0.80/1.20 (Ni) and 0.30/0.70 (Cu). The synthetic oxide software fixture has two bound CO₂ molecules, two occupied acid sites and two occupied oxygen sites. Fe(110) CH + CO remains DRAFT with unknown direction and site balance, missing Gibbs energies, and blocked MKM/KMC exports. Tests replayed the archived electronic barriers of 0.97360174 and 0.31429371 eV. Qualification produced no new scientific result.

## Scope and handoff

The R.2.5 diff relative to `b272db81` consists of four files.

- `reports/capability_readiness.json`
- `reports/capability_readiness.md`
- `reports/architecture_repair/stage_r2_5/completion.md`
- `modules/state_handoff/events/history-stage-r2-5-release-qualification-20261122.json`

The two current views form the qualified implementation. The final two files record its verification and propose a historical entry for human review. The existing module-map drift in the transition-state row and the earlier historical-compaction source mismatch remain separately recorded State Handoff conditions. Scientific engines, production SQLite, approved history and the V.1 workflow were outside execution scope.
