# Windows regression and evidence replay

The independent publication worktree and the remote task branch began at `f560ec82a8a23ec4bba5d4d25d975248d8eecdc4`. The development directory retained its independent `refactor/v2-architecture-repair` checkout at `233d5a6c589560094a0e942b6d48708b1fd5a847`. Before editing, the reaction schema, bundle validator, network builder, catalog, module README, B.1 projection implementation and legacy bundle fixture were compared byte-for-byte across both trees.

| Verification | Development | Publication |
| --- | ---: | ---: |
| Before editing, three suites for exchange records, reaction networks and multiphase identities | 156 passed | 156 passed |
| Existing B.1 through B.2.2.1 focused scope | 749 passed | 749 passed |
| New transfer tests | 30 passed | 30 passed |
| Final combined invocation | **779 passed, 0 failed, 41.05 s** | **779 passed, 0 failed, 40.20 s** |
| py_compile and Ruff for five changed Python files, public imports, reaction schema metaschema validation | Passed | Passed |
| Archived files equal to the baseline Git blobs | 25 of 25 | 25 of 25 |

The tests exercise the V1 exchange and partial-network entry points, a two-phase transfer through a named contact, no implicit transfer, explicitly unknown contact, binding errors, missing footprints and vacancies on either side, unknown charge, gross vacancy and molecular conflicts that can survive net checks, multi-site coefficients, direction reversal, missing scientific evidence and consistent identity renaming. Separate tests reconstruct the increments through B.1 matrices and apply B.2.1 coverage accounting to the before and after populations.

During focused test development, two new negative tests initially expected the destination diagnostic while the declared error was already detectable at the source. A later check exercised an empty vacancy map and a fixture with two simultaneous errors. The test inputs and expected first diagnostics were aligned with the specific contradictions being exercised. The final tests still require rejection of each contradiction. The existing tests were left intact.

The CLI generated the same synthetic network version in each worktree, `e50f1520e3d792d106ad98d232d141e6466ce1c754dbd59cea35a8290a69394c`. Serialized snapshot SHA-256 was `ae00afb986f289731019e5e871feed81a1536640acd57594d74b8b6e693e9865`. Both independently generated validation receipts have SHA-256 `dd80d789e0a679d3cf386f02550f76501658ef1510287cf0aff20ae05068dfbb`. The receipt lists every baseline file and digest, including the Fe and Ni/Cu networks, ten native-output replays, the oxide and identity fixtures and the three V2 rate/source schemas. [Machine receipt](transfer_validation.json)

One live CATKINAS test and eight native Zacros tests were deselected in each tree. This was a focused offline regression. The remaining repository suite was outside its scope. All computation here was fixture arithmetic, schema validation or archive replay. Production SQLite and native scientific workflows were outside the write and execution paths.

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_reaction_site_review.py tests/test_reaction_network.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
```
