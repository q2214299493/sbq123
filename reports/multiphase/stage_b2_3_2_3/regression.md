# B.2.3.2.3 offline regression

Both Windows worktrees generated the same five native members and input manifest from their own files. The development tree was on `refactor/v2-architecture-repair` at `233d5a6c`. The independent publication tree started at `4620d43088504db4288bdf0bb09127ad8eaa8203`.

| Worktree | First focused run | Final focused run | Python compilation and Ruff |
| --- | --- | --- | --- |
| Development | 679 passed, 1 failed, 8 deselected | 680 passed, 8 deselected in 28.78 s | Passed |
| Publication | 679 passed, 1 failed, 8 deselected | 680 passed, 8 deselected in 28.21 s | Passed |

The new manifest round-trip test exposed tuple-valued seed pairs in the returned Python dictionary where the on-disk JSON contained lists. The builder now normalizes the topology result at its JSON boundary. The five member files and serialized manifest retained the same bytes. The final run includes the previous 676 tests and four new tests.

The four tests check deterministic byte reproduction and refusal to overwrite, unavailable kinetic fields and zero-event controls, independent directional matching and exhaustive packing, and rejection of an outdated archived mapping. The matching test parses the delivered lattice, seeds and mechanism patterns. Swapping the two legs of the first molecule loses precisely its desorption match. Filling either available bridge consumes its shared oxygen and leaves zero further adsorption placements. These checks run in Python.

Both trees compared 43 unique existing source files with the publication baseline Git objects. All 40 hash bindings in the earlier evidence index matched. All eight Phase 2.5.1 Zacros archives matched their receipts. Within them, eight input manifests, 38 input members and 42 output members matched their recorded hashes. For resume, the input checkpoint was read from `input-checkpoint.inf` and the newly produced restart from `restart.inf`. [Archived evidence index](../stage_b2_3_2_1/evidence.json) and [archive receipts](../phase2_5_1/zacros_validation.json).

The following focused command was run separately in each worktree. The eight excluded cases would start the native benchmark executable. Full-repository tests were outside this local change.

```powershell
C:/Anaconda/python.exe -m pytest -o addopts= -q tests/test_native_model.py tests/test_native_advanced.py tests/test_native_rate_adapters.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_kinetic_parameters.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py tests/test_reaction_network.py tests/test_catkinas_network_mapping.py tests/test_catkinas_oxide_multidentate_audit.py tests/test_zacros_multiphase_mapping_audit.py tests/test_oxide_bridge_topology.py tests/test_zacros_bridge_input.py -k 'not test_native_zacros_replay' --tb=short
C:/Anaconda/python.exe -m py_compile scripts/surface_kmc/bridge_input.py tests/test_zacros_bridge_input.py
C:/Anaconda/python.exe -m ruff check scripts/surface_kmc/bridge_input.py tests/test_zacros_bridge_input.py
```
