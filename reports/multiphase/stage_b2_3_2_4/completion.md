# B.2.3.2.4 synthetic Zacros zero-event execution preparation

**Preparation passed. Execution approval is pending. Native parsing, loading, event matching and checkpoint readback are unverified for this dataset.** Both Windows trees reproduced the same five input files and verified them against the installed Zacros 4.0 executable hash. The supplied 400 K, 1 bar pure CO2 controls now form an isolated software benchmark named `synthetic_oxide_zacros_control_v1`.

## Model and independent reference

The four acid nodes and three oxygen nodes form a finite six-edge graph. The ordered seeds at (1,5) and (2,6) are byte-identical to B.2.3.2.3. The graph hash is `77d0f2fe9ab30743eec527bf412c4f35ed0097dc66fb9514ae0bb541673d0fea` and the mapping hash is `bb0f706fefc969bdf67a5fa44b2c21f8f61ed2e09f1778a76d6b1b6d342e0971`. The prior manifest retains digest `01f93bb5ed6d6b1dc9e422a9ef90e554558e57862a1713b53469eae94ed3cdae`.

| Direction | Native prefactor | Barrier | Ordered placements at event 0 | Propensity per placement | Summed initial propensity |
| --- | --- | --- | --- | ---: | ---: |
| Adsorption | 1.0e5 per bar per second | 0.10 eV | (3,7), (4,7) | 5,496.127439 /s | 10,992.254879 /s |
| Desorption | 1.0e13 per second | 0.50 eV | (1,5), (2,6) | 5,015,150.508419 /s | 10,030,301.016839 /s |

Only adsorption consumes a gas molecule and takes a native factor of CO2 partial pressure in bar. The two initially possible adsorption events compete for node 7. The initial state has two molecules, two vacant acid sites and one vacant oxygen site. One hypothetical adsorption would give three molecules and vacancy counts (1,0). One desorption from the starting state would give one molecule and (3,2). At the planned event limit all these changes remain hypothetical.

The chosen energy zero is empty sites plus gas CO2. A single typed two-leg bridge contributes -0.40 eV per molecular entity, consistent with the declared barrier difference. Its initial lattice energy contribution is -0.80 eV for two molecules. All inter-molecular cluster interactions are zero. Graph multiplicity is 1 and the explicit proximity factor is 0.5. Gas mass is 44.0096 amu. Detailed balance remains `not_assessed` because the control lacks independent equilibrium free energies and reservoir thermodynamics. No real material measurement, literature performance benchmark or production dataset uses these numerical assignments. [Control dataset](control.json) / [Unit and rate verification](rate_law.md) / [Numerical reference](numerical_reference.json)

## Input and independent approval

The [new five-file manifest](native/input_manifest.json) has SHA-256 `023b40ad208b77a8028d9e03e2131fdc53bd34c2f88f09cdcf2fe19c39f0c285`. The [execution plan](execution_plan.json) has SHA-256 `2c0a012270fec9a6a11e52411c9993742fe6ffc3017db333857fbc4c2dd1b7d8`, calculated on its exact file bytes. It binds all five inputs, the numerical reference, control dataset, Windows executable, resource limits and output criteria. A reviewer can approve or reject a single serial initialization. The [current execution approval request](approval_request.json) has an empty allowed-action list. The read-only preflight checks the source hashes, byte-for-byte rebuild, executable digest and limits. The existing bound-action gate checks a separately recorded researcher decision. State Handoff decisions have their own authority. There is no native launcher in this preparation entry point.

The budget is zero events, one process, one thread, 15 s native wall limit, 30 s external deadline and zero retries. On failure or timeout retain the partial run. Future execution must reserve a single use of the approved plan, stage only the verified five inputs in a fresh empty directory, and reconfirm their hashes. Acceptance requires the five native reader confirmations, zero executed events, the seven-site restart ledger with entity and leg IDs, and all four directed placements in the initialization section of `process_debug.txt`. An aggregate catalogue size or cumulative event count is insufficient. The native text propensity tolerance is 1e-5 relative and 1e-8 /s absolute. Counts and ordered placements must match exactly. The expected directed-step warning 4008 must be reviewed. The five inputs have passed offline checks; their combined native acceptance still requires this separately approved test.

To reproduce the native bytes, choose a *new* output directory. The second command hashes inputs and prints the request without launching Zacros.

```powershell
C:/Anaconda/python.exe -m scripts.surface_kmc.oxide_control reports/multiphase/stage_b2_3_2_4/control.json NEW_DIRECTORY
C:/Anaconda/python.exe -m scripts.surface_kmc.zero_event_review reports/multiphase/stage_b2_3_2_4 D:/Zacros4.0/bin/Zacros.exe
```

Both worktrees passed 697 focused tests, with 8 native re-executions explicitly deselected. [Regression scope](regression.md) / [State Handoff](handoff.md)

## Changed files

- `modules/surface_kmc/README.md`
- `scripts/surface_kmc/oxide_control.py`
- `scripts/surface_kmc/zero_event_review.py`
- `tests/test_zacros_zero_event_control.py`
- `reports/multiphase/stage_b2_3_2_4/.gitattributes`
- `reports/multiphase/stage_b2_3_2_4/control.json`
- `reports/multiphase/stage_b2_3_2_4/numerical_reference.json`
- `reports/multiphase/stage_b2_3_2_4/rate_law.md`
- `reports/multiphase/stage_b2_3_2_4/execution_plan.json`
- `reports/multiphase/stage_b2_3_2_4/approval_request.json`
- `reports/multiphase/stage_b2_3_2_4/native/input_manifest.json`
- `reports/multiphase/stage_b2_3_2_4/native/lattice_input.dat`
- `reports/multiphase/stage_b2_3_2_4/native/state_input.dat`
- `reports/multiphase/stage_b2_3_2_4/native/simulation_input.dat`
- `reports/multiphase/stage_b2_3_2_4/native/energetics_input.dat`
- `reports/multiphase/stage_b2_3_2_4/native/mechanism_input.dat`
- `reports/multiphase/stage_b2_3_2_4/completion.md`
- `reports/multiphase/stage_b2_3_2_4/regression.md`
- `reports/multiphase/stage_b2_3_2_4/handoff.md`
- `modules/state_handoff/events/history-stage-b2-3-2-4-oxide-zero-event-control-20261122.json`
