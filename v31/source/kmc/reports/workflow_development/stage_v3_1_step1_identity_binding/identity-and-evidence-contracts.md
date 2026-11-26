# V3.1 Step 1 scientific identity and evidence binding

The integration entry points operate on a completed run. They produce one JSON sidecar on stdout. To verify a saved sidecar, provide the original artifacts and pass `--verify FILE` to the same command. A discrepancy raises an error. Source paths and example bindings are in the accompanying report. CATKINAS and Zacros keep their existing run and result formats.

## Elementary identity

Call `scripts.kinetic_data.scientific_identity.require_reaction_identity(left_dataset, right_dataset, reaction_id)` on two compiled kinetic datasets. It returns the verified oriented reaction identity or raises `ValueError` with the differing components. Its scope is elementary reaction identity. Passing this check supplies no equivalence decision about rates, thermodynamic conditions or stationary ensembles.

| Component | Evidence and decision |
|---|---|
| Molecular stoichiometry | Resolve each gross forward reactant and product through the existing species fingerprint. Preserve coefficients on each side, composition, charge, phase, molecular footprint and structural context. Recompute element, charge and occupied-plus-vacant inventory totals. |
| Site requirements | Compare vacancy consumption and release separately, recompute the site balance, validate the ordered pattern against entity denticity and the graph, and compare any additional local spectator/vacancy pattern. Follow the site IDs through surface, phase, material and interface ownership. Missing local geometry leaves the cross-engine event unproven. |
| Direction | Reconstruct the reverse using the existing reaction builder. Unknown reversibility, swapped orientation or contradictory directional records fail. |
| Parameters and provenance | Each binding references the exact kinetic dataset bytes, dataset/network versions, reaction ID, parameter set ID and canonical hash of the complete compiled reaction row. Retrieve the original row using that ID and verify its hash before reading its rates, units, activity orders, multiplicities, energies, standard states, fit evidence, uncertainty or covariance. The sidecar also exposes the parameter-set energy basis, energy reference and uncertainty. A stored null retains its original unknown meaning. |
| Scientific review | File and record hashes identify the evidence used. Existing module review records retain their original authority and scope. This identity check does not grant approval for parameter transfer or native execution. |

The archived MKM and KMC `ads` definitions both consume one gas H2 and one vacancy in each of two inventories. The MKM products are two monodentate H fragments. The KMC product is one bidentate H2 molecule. Both worktrees reject molecular stoichiometry and local geometry. The dataset inventory counts agree per firing. The gas reservoirs also differ. See `ads-counterexample.json`.

## MKM point

`python -m scripts.baseline_mkm.result_binding RUN [--normalization-profile PROFILE] [--verify FILE]`

The reader verifies the three approved input file digests, reuses the accepted point and steady-state MAT/log replay, then binds the result, plan, receipt, input echo, runtime, normalization and physical conditions. The exact terminal coverage and vacancy vectors determine `root_state_sha256`. The complete binding also includes the initial molecular/site state, residuals and individual execution. Equal endpoints reached from different starts can share the state digest and have distinct execution bindings. Root identity here means the observed numerical endpoint. Basin classification, stability and uniqueness require the owning steady-state analysis. An explicitly supplied legacy normalization profile has its own byte hash and `profile_bound_by_plan=false`. On modern points the originally approved profile hash must match.

## KMC observation

`python -m scripts.surface_kmc.result_binding DATASET CONFIGURATION RUN START_S END_S [--verify FILE]`

The reader reconstructs the native model and validated cumulative streams and walks the claimed checkpoint parents. The leaf plan digest and exact receipt byte digest identify the native result. The ordered lineage retains each run, plan, receipt, reviewed decision, model, checkpoint preimage, parent receipt and global terminal step and time. A child links to the checkpoint written by its parent. The historical writer remains authoritative for a missing legacy spatial cursor.

The observation definition records seconds, both bounds, the left-held population rule, event counts on `(start,end]`, and the simulation-cell denominator. The attached observation retains rates in events per simulation cell per second, net molecular sources in molecules per simulation cell per second, mean molecular counts per cell, and occupied fractions relative to the separate inventory capacities. Each event stream uses its recorded physical clock. The window digest covers the definition, values, capacities, input and condition references, full lineage and leaf result identity. Equal values in distinct windows yield distinct digests. Bounds outside the finite sampled streams fail.

## Digest and replay conventions

File digests are SHA-256 of original bytes. Record digests use `scripts.artifact_io.sha256_json`. For a point or window, exclude only its own outer digest field when recomputing that digest. Verification reconstructs the binding from the supplying engine's evidence and compares the entire sidecar. A detached manifest or reviewed digest is needed to identify the originally delivered sidecar if the artifacts and the sidecar can both be replaced.

The KMC archive supplies its compiled network version. This work does not certify the bytes of a separately supplied source network for that trajectory. The MKM approved plan directly supplies its network file hash. Equal network version strings, aliases, aligned site totals or an equal parameter-set label alone cannot qualify a cross-engine observable. Site labels, geometry and catalog records are matched conservatively. A differently labeled site/phase or equivalently permuted geometric representation can require a reviewed crosswalk. The shared module has the same bytes in both branches and requires no import from the other checkout.
