# Zacros 4.0 zero-event native acceptance: failed at the simulation reader

The researcher authorized one initialization of `synthetic_oxide_zacros_control_v1` from publication baseline `335008915ebcb227cc5012054df105a2e0ac4404`. The installed serial Zacros 4.0 build rejected line 2 of the exact approved simulation input. The program returned exit code 0 and wrote a fatal abnormal-termination marker. **The native acceptance verdict is FAILED.** The run establishes a real-token formatting incompatibility in this input. The native ability to load the seven-site oxide and match its bridges remains unverified.

## Authorization and one execution

The publication worktree was on `codex/multiphase-phase0-integration`; its HEAD and the remote branch matched the approved baseline. The development tree retained its independent history. The approved plan, control, reference, request, manifest and five inputs were checked against the publication Git objects. The module gate verified the separately recorded direct human approval against the plan bytes and executable. No matching earlier run was found in the configured Zacros work area or the project evidence records; no Zacros process was running at preflight. An exclusive directory keyed by the plan digest and an exclusive consumption receipt reserved the one allowed launch. A new empty child directory received exactly five input files. Immediately before launch the staged member hashes, executable and approval passed verification.

| Bound item | Actual |
| --- | --- |
| Execution plan SHA-256 | `2c0a012270fec9a6a11e52411c9993742fe6ffc3017db333857fbc4c2dd1b7d8` |
| Five-input manifest SHA-256 | `023b40ad208b77a8028d9e03e2131fdc53bd34c2f88f09cdcf2fe19c39f0c285` |
| Zacros.exe SHA-256 | `84a8f88d6df633eeea9eeac8aa9227237cdf2564a4dc72e0cab8a18c4ce119d2` |
| Execution window (Asia/Shanghai) | 2026-11-22 16:49:21.470453 to 16:49:22.138951 |
| Process / elapsed | PID 31020, 0.667834 s measured with a monotonic clock, exit 0, no timeout |
| Limits and consumption | One serial process, `OMP_NUM_THREADS=1`, zero maximum events, native wall limit 15 s, external timeout 30 s, one launch, zero retries |
| State after termination | All five input hashes still agree. The only native output file is `general_output.txt`; stdout and stderr were captured separately. |

[Execution receipt](execution_receipt.json) / [Researcher approval](execution_approval.json) / [One-use claim](consumed.json) / [Original inputs, output and streams](raw_native.zip) / [Byte-level I/O manifest](io_manifest.json)

## Five-reader acceptance and propagation

| Native reader, in program order | Result | Evidence |
| --- | --- | --- |
| Simulation | Rejected | Version and serial-mode banners and random seed appear. Fatal code 1002 in `simulation_parser_module` identifies `temperature 400` at line 2. |
| Lattice | Not reached | Simulation reader did not return normally. No lattice output. |
| Energetics | Not reached | No reader completion marker. |
| Mechanism | Not reached | No reader completion marker. |
| Initial state | Not reached | No reader completion marker or seed confirmation. |

The release calls these readers in order at `zacros_main.F90` lines 209-215. Lattice-state initialization and process enumeration occur later at lines 265-267, followed by the event loop. Native stdout confirms the requested limit of zero. The fatal error prevented any event propagation; the binary never printed a terminal event counter. Its measured value is recorded as null. An expected zero-event initialization with a readable checkpoint was **not achieved**.

## Initial state, ordered matches and numerical evidence

| Quantity | Independent expectation | Native measurement |
| --- | --- | --- |
| Bridge entities and legs | bridge-1: acid leg 1 at 1, oxygen leg 2 at 5; bridge-2: acid leg 1 at 2, oxygen leg 2 at 6 | Unavailable. No `restart.inf`. |
| Adsorption placements | (3,7), (4,7) | Unavailable. No native initial process catalogue. |
| Desorption placements | (1,5), (2,6); (2,5) spans distinct entities and must be absent | Unavailable, including exclusion of the false match. |
| Acid / oxygen inventories | Occupied 2/4 and 2/3; vacant 2/4 and 1/3 respectively | Unavailable. |
| Lattice energy | -0.80 eV | Unavailable. |
| Per-placement propensity | Adsorption 5,496.127439 /s; desorption 5,015,150.508419 /s | Neither measured. No numerical agreement or residual can be evaluated. |

The [seven-site ledger and comparison](validation.json) lists every expected site, molecule and bound leg alongside null native entity, species and leg IDs. The reference state and [reference rates](../numerical_reference.json) retain their original provenance.

## Root cause and decision needed

The old offline checks accepted the text `400` as a numerical value. In the distributed Zacros 4.0 source, `simulation_parser_module.F90` lines 1656-1663 request an R8 token for temperature. `parser_module.F90` lines 186-265 and 352-358 require a decimal point or an exponent marker for the real-token recognizer. This differs from a permissive Python float conversion. The release ZIP hashes to `55ae665d845ad1120241b98e0a72192bb3737ade801275ec13c06d81fae9abae`; the parser member hashes to `8f6019e33ace873e78fe4c835edbc07e10c22be41299fdbb55bfb993623acff5`.

A read-only comparison of the immutable input bytes against the vendor field declarations found eight bare integer tokens in real-valued positions:

| File | Lines | Fields | Source of classification |
| --- | --- | --- | --- |
| `simulation_input.dat` | 2, 3, 6, 8 | temperature, pressure, gas energy, gas mole fraction | Simulation parser 1660, 1695, 1804, 1834 |
| `energetics_input.dat` | 8, 16 | two empty-site cluster energies | Energetics parser 1691-1703 |
| `mechanism_input.dat` | 13, 28 | adsorption and desorption prefactors | Mechanism parser 2363-2375 |

Only line 2 was rejected in this run. The other seven findings come from source inspection. The original inputs and plan remain archived intact. The proposed next decision is whether to prepare a separate revision that renders native real fields with decimal or exponent syntax (for example `400.0`) and leaves integer fields such as `max_steps 0` alone. That revision would need new byte hashes, lexical regression checks and a fresh execution approval. No replacement input or retry was generated.

[Focused offline regression](regression.md) / [State Handoff](handoff.md)
