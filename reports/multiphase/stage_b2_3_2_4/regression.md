# B.2.3.2.4 offline regression

| Windows worktree | Final focused pytest | Native archive launches excluded | py_compile | Ruff |
| --- | --- | --- | --- | --- |
| Development, `refactor/v2-architecture-repair@233d5a6c` | 697 passed, 0 failed in 31.71 s | 8 | Passed | Passed |
| Publication, `codex/multiphase-phase0-integration@1bf5cff2` before commit | 697 passed, 0 failed in 31.01 s | 8 | Passed | Passed |

The 680 previous tests cover the B.1 rate, dimensional and source-term contracts, B.2.1 inventories, B.2.2 identity/transfer/cross-phase contracts, CATKINAS mappings, and Zacros offline archive and lattice readback. The 17 additional cases check deterministic input, byte preservation, actual native pattern and cluster syntax, cold-start controls, molecular and site ledgers, an independent Decimal Arrhenius evaluation, pressure scaling away from 1 bar, invalid numbers and units, the pending request, stale/unrelated decisions, modified inputs, unexpected restart and executable mismatches.

Both trees independently hashed the actual installed binary and reproduced the shipped approval request. Unit tests stub only the binary hash probe so CI can exercise preflight without possession of licensed software. They use temporary test decisions. All source, native-input and plan hashes are real file hashes. No native process was launched.

In an earlier pass the two trees returned 694 passed with 8 deselected, before three additional invalid-input tests were included. Ruff then flagged excessive branch complexity in the input renderer. Extraction of the source-binding read into its own function resolved that check. The final result above includes the complete rerun.

In each tree, 49 pre-existing evidence paths matched the given baseline's Git blobs, including the previous six structural-bundle files. All 40 earlier project evidence bindings and eight historical Zacros ZIP hashes were rechecked. The archives contained eight verified manifests, 38 verified input members, and 42 verified output members, including the distinct input checkpoint and resumed output checkpoint in the restart fixture. [Archive receipts](../phase2_5_1/zacros_validation.json)

```powershell
C:/Anaconda/python.exe -m pytest -o addopts= -q tests/test_native_model.py tests/test_native_advanced.py tests/test_native_rate_adapters.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_kinetic_parameters.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py tests/test_reaction_network.py tests/test_catkinas_network_mapping.py tests/test_catkinas_oxide_multidentate_audit.py tests/test_zacros_multiphase_mapping_audit.py tests/test_oxide_bridge_topology.py tests/test_zacros_bridge_input.py tests/test_zacros_zero_event_control.py -k 'not test_native_zacros_replay' --tb=short
C:/Anaconda/python.exe -m py_compile scripts/surface_kmc/oxide_control.py scripts/surface_kmc/zero_event_review.py tests/test_zacros_zero_event_control.py
C:/Anaconda/python.exe -m ruff check scripts/surface_kmc/oxide_control.py scripts/surface_kmc/zero_event_review.py tests/test_zacros_zero_event_control.py
```

This was the focused B.1/B.2 regression. The complete repository suite was outside this benchmark.
