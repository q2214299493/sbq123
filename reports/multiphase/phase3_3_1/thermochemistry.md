# Fe(110) thermochemistry at 523 K

All three selected saddles have reusable Grade A vibrational spectra. Six distinct endpoints still need state-specific thermal evidence. Only the R3 saddle has a documented conditional 523 K local harmonic correction. The temperature and 1 bar gas standard state follow the provisional project reference.

| Reaction and state | Structure SHA-256 prefix | Available evidence | Missing for 523 K |
|---|---|---|---|
| R1 IS · CO* | `6ed0dcc7bc57` | Registered structure and electronic energy | Matched stable-state spectrum or reviewed correction, scope and conventions |
| R1 TS · CO cleavage | `bc2d62ba7617` | Grade A, 6 modes, reaction coordinate 6 (537.452i cm⁻¹) | Review frequency scale, low-mode treatment, thermal basis and diagnostic smearing compatibility |
| R1 FS · coadsorbed C* + O* | `08ab46f9210e` | Registered structure and electronic energy | Matched stable-state spectrum or reviewed correction, scope and conventions |
| R2 IS · reactive C* + H* (A) | `121ace35043c` | Registered structure and electronic energy | Matched stable-state spectrum or reviewed correction, scope and conventions |
| R2 TS · C–H formation | `8fd9cb6818e1` | Grade A, 21 modes, reaction coordinate 21 (842.195i cm⁻¹) | Review frequency scale, low-mode treatment, thermal basis and diagnostic smearing compatibility |
| R2 FS · CH* long bridge | `ffeccf7353ea` | Registered structure and electronic energy | Matched stable-state spectrum or reviewed correction, scope and conventions |
| R3 IS · coadsorbed CH* + CO* | `f8bc627180b4` | Registered structure and electronic energy | Matched stable-state spectrum or reviewed correction, scope and conventions |
| R3 TS · C–C coupling | `0157a418cd1f` | Grade A, 12 modes, reaction coordinate 12 (318.644i cm⁻¹); ZPE 0.51405165 eV, G correction 0.27948341 eV | Comparable corrections for both endpoints |
| R3 FS · CHCO* | `11dab1631a99` | Registered structure and electronic energy | Matched stable-state spectrum or reviewed correction, scope and conventions |

The VFA inputs for the three TS spectra used SIGMA 0.10 eV. The electronic energies use the registered SIGMA 0.20 eV TOTEN branch. Each spectrum carries a structure and active-axis binding. R3 alone has an existing benchmark-specific unscaled convention. No R1/R2 scale or low-frequency cutoff was assigned. ZPE is included once in the Gibbs correction, and the thermal enthalpy increment excludes ZPE.

**Source check.** Twelve physical Hessian inputs were screened by ordered atoms, cell and periodic coordinates. None matched the six selected endpoints. A separate read-only search of nine relevant VASP server directories covered 35 INCARs and identified only the three known TS frequency jobs. The registry and scoped scientific JSON records yielded no additional registered or reviewed compatible state corrections. Unregistered material held elsewhere remains eligible for intake. [Per-state structure hashes, search scope, signed-mode evidence and missing fields](thermochemistry.json)

**Minimum additional work.** Review the existing R1/R2 TS spectra first. Request compatible evidence for the six endpoints using their full hashes in the audit. For each still uncovered endpoint, one local partial Hessian is the conditional fallback; all six would be needed only if none can be supplied. Reuse is possible across adjacent steps only after structure and thermal-reference compatibility have been established. No new static electronic energy is identified as necessary for these nine states.

R1–R3 can advance independently of job 13422. The three reaction free energies and both directional activation free energies for each reaction remain unavailable. R4 retains separate requirements for IS-A, INT06, MID and FS-A, and for its three segment saddles. The first-segment frequency job has its own handoff record. [Bound handoff checkpoint](../phase3_3_0/r4_9833429_frequency_submission.json)
