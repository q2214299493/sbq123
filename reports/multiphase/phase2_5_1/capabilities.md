# Native engine capability matrix, 2026-11-19

| Capability | Input generated | Static check | Actual native read | Bounded numerical result | Scientific evidence |
| --- | --- | --- | --- | --- | --- |
| CATKINAS, synthetic two-site reaction | Phase 2.5 input, exact SHA-256 verified | Stoichiometry, two inventories, 400 K, frozen 1 bar H₂ and two reference coefficients passed | November distribution echoed exact bytes, equation, species and site inventories. Full acceptance failed during rate-law construction | Failed with exit code 1; native kf and kr unavailable | No numerical benchmark result for this model |
| CATKINAS environment control | Vendor five-step single point, bounded solver settings | Input hash recorded, 673 K | Accepted on the same binary and MATLAB runtime | Produced data1.mat; all five kf and five kr exactly equal the vendor sample | Independent software control only. [Receipt](catkinas_environment_control.json) |
| Zacros 4.0, ideal Ni/Cu model | Yes | Passed | Four files | Original 20-event benchmark preserved; continuous checkpoint-enabled control reproduces the event history | Synthetic reference only |
| Nonempty monodentate lattice | Yes | Passed | Five files including state | One occupied Ni site leaves 16 matches. Hydrogen conserved through recorded trajectory | Synthetic occupancy benchmark passed |
| Bidentate initial state | Yes | Passed | Five files | One two-leg molecule leaves 15 adsorption placements and one desorption event. The molecule counts once | Synthetic footprint benchmark passed |
| Attractive lateral interaction | Yes | Explicit −0.04 eV per unlike occupied bond | Five files | Initial energy −0.04 eV. Eight physical adsorptions yield 18 bonds and −0.72 eV at saturation | Synthetic pair-energy and occupancy benchmark passed |
| Repulsive lateral interaction | Yes | Explicit +0.04 eV per bond, reverse BEP factor 0.75 | Five files | Full lattice 0.72 eV; first desorption leaves 0.60 eV. Rate response agrees with the independent reference within 0.00019% | Synthetic energy/response verified. Warning 804010 limits physical interpretation of the rate model |
| Checkpoint writing | Yes | Checkpoint enabled | Four input files | Stops at 8 events and writes a nonempty native checkpoint | Synthetic software behavior verified |
| Checkpoint restoration | Yes | Checkpoint and producing model hashes checked | Native reader confirms restart from step 8 | Stops at 20. Species/time/energy records and process statistics match continuous run byte for byte | Deterministic continuation verified on this build |
| Restart provenance | Yes | Changed checkpoint, model, receipt or input rejected | Exact bound checkpoint read | Same uninterrupted reference trajectory | Binds exact bytes and model identity; authenticity of an outside provider requires trusted provenance |
| Real Fe(110) CH* + CO* → CHCO* | Both adapters reject the draft dataset | Existing export gate exercised | No model submitted | No run | Endpoint thermochemistry, reviewed site balance, catalyst phase and kinetics remain incomplete |

## Reproduction

The eight ZIPs contain the actual synthetic inputs, configuration, kinetic dataset, manifest, full native console and generated outputs. In the resume bundle, `input-checkpoint.inf` is the bytes read on entry and `restart.inf` is the new checkpoint at termination. Individual hashes, execution arguments, observed warnings and numerical results are in the [Zacros validation record](zacros_validation.json).

From a checkout with the authorized executable installed, reproduce the cases in fresh temporary directories using the following command. The tests check the binary digest before invoking it, bound each process to 30 s, and compare the resulting trajectories with the archived outputs.

```powershell
$env:SBQ_ZACROS_BENCHMARK_EXE = "D:/Zacros4.0/bin/Zacros.exe"
python -m pytest -q tests/test_native_advanced.py
```

**Lateral-interaction oracle.** At full coverage, each of nine Ni sites has two unlike neighbors. One desorption removes three repulsive bonds, including the isolated pair. The environment-dependent energy difference is −0.08 eV. At 400 K, with reverse proximity factor 0.75, the expected rate ratio is exp(0.06 eV / kBT) = 5.70120592. All 18 initial events are equivalent. Comparing the first waiting time against the fully occupied ideal control with the same seed gives 5.70119537. The fixed-temperature rate representation uses zero apparent activation energy and directed steps. Zacros reports 4008 for directed steps and 804010 for out-of-range effective barriers in the repulsive case. The attractive adsorption-only case ends in an absorbing state. Warning 801002 and the final clock sentinel follow exhaustion of physical events; the final physical sample is event 8.

**Restart oracle.** The writer and reference share one input manifest, seed, clock limit and executable. A native command-line stop at 8 steps produces the checkpoint. The restore command requests a total of 20 steps. Species and process files sample states through event 19; the native termination record confirms event 20. Joining the writer and reader streams exactly reconstructs both reference files, including timestamps. The native reader and writer can include restart counters in their output, so checkpoint-file identity at the final step is not the continuation criterion.

**CATKINAS environment.** Four previously identified copies matched the expired P-code. The researcher then provided a different vendor download labeled `20261106`. Its runtime banner still says `20230524`; its compiler stamp is 7 November 2026. MATLAB R2025b loaded that isolated copy, and the native engine identified one reversible equation and two site types. It then reported no overall reaction and an offline step, followed by a symbolic assignment dimension error. The echoed energies are inputs. The project model produced no native kf or kr. [Bounded attempt and output hashes](catkinas_target_attempt.json) · [Console](catkinas_target_console.txt) · [Official downloads](https://www.catkinas.com/downloads/)
