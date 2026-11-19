# Native engine compatibility · installed files

Inspected the paths in `configs/postprocessing_software.yaml`, the deployed guides, the startup scripts and existing example outputs. No engine or solver was started.

| Interface | CATKINAS | Zacros |
|---|---|---|
| Installed runtime | `C:/Users/86177/Desktop/app/CATKINAS/CATKINAS.p` (MATLAB p-code). MATLAB launcher resolved on PATH at `D:/BaiduNetdiskDownload/bin/matlab.exe`, file product version 25.2.0.2978516. Historical quickstart log reports MATLAB 25.2.0.2998904 (R2025b). An independent CATKINAS release number needs confirmation. | `D:/Zacros4.0/bin/Zacros.exe`. Installed manual and existing run header both identify 4.0. The manual is the 101-page User Guide dated 19 July 2024. |
| Native invocation | From quickstart, `run_single.m` calls `CATKINAS('INPUT_single')` with the p-code and input on the MATLAB search path. A future wrapper can use MATLAB batch mode. Deployment README's older PATH observation differs from this inspection. | In the writable model directory put `D:/Zacros4.0/bin` on PATH and invoke `Zacros.exe` without model arguments. Installed `Zacros_Shell.cmd` opens an interactive shell; `work/example_100/run_example_100.cmd` sets cwd and launches the executable. |
| Inputs | `quickstart/INPUT_single.m`, curve/map variants. Indexed sites (#1 etc.), reversible equations, conditions and eV energetics. ReadMe.m specifies optional `Thermodynamics.data` fields CF/TR/AH/FQ/EF. No literal `CATKINAS.in` or `Thermodynamics.data` was found under this installation. Preserve the actual input stem. | `simulation_input.dat`, `lattice_input.dat`, `mechanism_input.dat`, `energetics_input.dat` exist in example_100. Optional initial state is absent there. Match site labels, neighbour graph, event pattern, cluster energetics and species ordering across the files. |
| Outputs | `examples/Examples-Run/Examples/result_{single,curve,map}/data1.mat`, logs and figures. Each of the three MAT headers is MATLAB 5.0 format. `scipy.io.whosmat` read Rnet, Rnets, R, Z and y. Rnet has shape 1×5, 401×5 and 315×5 in single, curve and map respectively. Quickstart's own log1.err records an undefined atom-symbol warning and its result folder lacks data1.mat. Completion of that local run needs confirmation. | example_100 contains general, lattice, history, specnum and procstat text outputs. general_output records normal termination. specnum headers identify time, temperature, energy, two surface and three gas species. procstat groups event names, configuration, times and counts. Optional restart.inf was absent. Absolute rates/TOF require a time interval and physically justified normalization. |
| Limits | ReadMe.m gives MaxTime per Newton attempt and MaxOdeTime per ODE attempt. quickstart/timelimit.m checks elapsed time. No process-level timeout or child cleanup exercised. MAT v7.3 support and variable meanings across builds require separate verification. | example_100 sets simulated max_time 25.0 and wall_time 3600 seconds. The cmd wrapper provides no external watchdog. Timeout, license, MPI and restart behavior were not exercised. |

## Capability matrix at this boundary

Binary SHA-256 identities are `40cf8854167d1c60b93ed722bf7a2af8baf7400de817640ddba2f520cced1382` (CATKINAS.p) and `84a8f88d6df633eeea9eeac8aa9227237cdf2564a4dc72e0cab8a18c4ce119d2` (Zacros.exe). The archived runner timeout test passed with a sleeping Python subprocess. Installed example_100 records serial execution. The guide locates lattice definitions on pp. 49–54, energetics from p. 55 and history, process statistics and species counts on pp. 81–83.

| Capability | Installed evidence | SBQ123 implementation | Tested here | Scientifically validated | Version dependence |
|---|---|---|---|---|---|
| CATKINAS mechanisms, sites, corrections, steady state and scans | ReadMe.m and input examples | Native adapter pending | Input inspected | No | Verify current p-code semantics |
| CATKINAS rates, coverages, DRC, selectivity and figures | Supplied completed examples and MAT directories | Normalized parser pending | MAT header and variable directory on 3 examples | No | MAT version and variable layout |
| Zacros site graph, events, lateral interactions and multisite exclusion | Manual p. 3 and example_100 inputs | Native model generation pending | Example inspected | No | Model-specific lattice and clusters |
| Zacros counts, histories, termination | Installed text files | Normalized parser pending | Headers/blocks and termination marker checked | No | Model species/event order |
| Process timeout, restart, parallel execution | Documented settings and wrappers | Production runner pending | No | No | Build/runtime dependent |
| Phase 1 common run identity | Engine-specific artifact roles | Declarative manifest | See Phase 1 report | Scientific validation is inapplicable to schema syntax | Native inputs remain external artifacts |

No Fe-specific kinetic benchmark, native input generator, numerical convergence claim or simulation throughput follows from these inspections.
