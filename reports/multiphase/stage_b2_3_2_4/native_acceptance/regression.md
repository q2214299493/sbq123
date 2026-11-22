# Offline replay of the oxide initialization failure

| Windows worktree | Focused regression | Excluded | Checks on the new Python test |
| --- | --- | --- | --- |
| Development (`233d5a6c`, developer changes preserved) | 701 passed, 0 failed in 42.79 s | 8 native benchmark re-executions | py_compile and Ruff passed |
| Independent publication (`33500891` before the evidence commit) | 701 passed, 0 failed in 43.38 s | Same 8 | py_compile and Ruff passed |

Four new cases verify the consumed permission and plan binding, archive contents against source and receipt hashes, the fatal reader error despite exit code zero, and missing native observations remaining null. The 697 previous tests cover B.1/B.2 contracts, native input preparation and the approval boundary. These results concern offline software and evidence handling. The approved native initialization **failed**. The eight opt-in native replays were explicitly excluded and no retry was run. The full repository suite was outside this evidence checkpoint.

Both trees compared ten original artifacts (six bundle members including its manifest plus control, reference, plan and request) with the exact baseline Git blobs. All five staged native files still matched after process exit. All eight byte streams in the archive (five inputs, one native output and two console streams) were re-read and hashed.

```powershell
C:/Anaconda/python.exe -m pytest -o addopts= -q tests/test_native_model.py tests/test_native_advanced.py tests/test_native_rate_adapters.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_kinetic_parameters.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py tests/test_reaction_network.py tests/test_catkinas_network_mapping.py tests/test_catkinas_oxide_multidentate_audit.py tests/test_zacros_multiphase_mapping_audit.py tests/test_oxide_bridge_topology.py tests/test_zacros_bridge_input.py tests/test_zacros_zero_event_control.py tests/test_zacros_zero_event_native_receipt.py -k 'not test_native_zacros_replay' --tb=short
C:/Anaconda/python.exe -m py_compile tests/test_zacros_zero_event_native_receipt.py
C:/Anaconda/python.exe -m ruff check tests/test_zacros_zero_event_native_receipt.py
```

## Changed files

- `reports/multiphase/stage_b2_3_2_4/native_acceptance/researcher_authorization.md`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/execution_approval.json`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/consumed.json`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/execution_receipt.json`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/raw_native.zip`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/io_manifest.json`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/validation.json`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/native_acceptance.md`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/regression.md`
- `reports/multiphase/stage_b2_3_2_4/native_acceptance/handoff.md`
- `tests/test_zacros_zero_event_native_receipt.py`
- `modules/state_handoff/events/history-stage-b2-3-2-4-oxide-native-init-failed-20261122.json`
