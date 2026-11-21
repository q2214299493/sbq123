# Native evidence inventory before implementation

| Archive family | Available | Missing or unverified | Rate interpretation |
| --- | --- | --- | --- |
| CATKINAS Phase 2.5 standalone | Input, failed attempt receipt and console | Successful converged MAT | No kinetic point from this attempt |
| CATKINAS Phase 2.5.2 closed cycle | Receipt binds MAT, symbol log extract, dataset, configuration, echoed input, executable identity, runtime self-report and parameter comparison | Standalone registry run ID. The receipt identifies the run by its local archive directory. | Four directional pairs and signed net observations on one site pair |
| CATKINAS Phase 3.0 | Separate accepted run manifest, result, network, MAT, native-log extract, input hashes, coverages and residuals | Physical catalyst validation and measured covariance | Independent replay of the same synthetic model |
| CATKINAS perturbation archives | The multiphase reports include 24 MAT files across the closed-cycle and subsequent sensitivity workflows. Later MAT files have their own perturbation receipts. | Perturbations are outside the requested two-run conversion. | Preserve original run and conditions for each MAT |
| Zacros Phase 2.5 initial smoke | Input manifest, model, aggregate events and terminal time in the receipt, output digests | Standalone receipt has no per-direction counts. Raw members can be reused only on exact hash identity. | Receipt-level totals alone cannot determine directional rates |
| Zacros Phase 2.5.1 | Eight hash-bound ZIPs with native input, model, per-process cumulative statistics, species numbers, general output, seed, lattice and event mappings | Independent replicates and an equilibrated production window. Two model variants need their exact network versions rematerialized from the existing synthetic fixture. | Finite observed-window counts per second on one simulated lattice |
| Split and resumed Zacros segments | Output and input checkpoint digests, cumulative event numbers and physical times | Resumed outputs omit column headers. Recover labels from the hash-bound writer. | Use counter and clock differences from the resumed first observation |
| Attractive absorbing case | Eight recorded physical events and native termination warning 801002 | Physical end time of the sentinel step | Stop at the last physical sample |

The Phase 3.1 normalization record binds one site of each inventory to the CATKINAS pair. A Zacros input coefficient is per matching event. The observed process counters are totals on the simulated lattice. Neither matching multiplicity nor lattice size is an implicit conversion factor. Coverage, native diagnostics and sampling qualifications belong in companion reports alongside the strict V2 rate payload.
