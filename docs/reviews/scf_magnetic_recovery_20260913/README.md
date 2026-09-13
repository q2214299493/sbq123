# Same-geometry magnetic recovery review — not a submission package

2026-09-13. User approved comparison and preparation only. No new VASP job,
execution authorization or submission gate has been created.

## Evidence

SCF9754301 reached EDIFF=1e-7 in 135 steps and terminated normally. Compared
with SCF9752745, its TOTEN is higher by 4.124121068 eV (-384.15876210 versus
-388.282883168 eV), and its total moment is 67.8060 versus105.0209 muB.
Both final OUTCARs contain electronic convergence and normal termination.
Input/final positions agree under PBC within1e-10 A; cell, species/order and
Selective Dynamics agree. This is not a structural displacement failure.

Fe zero-based indices9,11,12,13,14,15,16,17 (one-based10,12–18) change from
+2.248–2.283 to -1.948–2.048 muB in the local projected magnetization table.
All eight are coordinate-fixed atoms. All45 Fe are positive in9752745.
Coordinate fixing does not constrain electronic spin. Projected atomic moment
sums are not required to equal total cell magnetization because of interstitial
magnetization and projection definitions.

Maximum atomic force is0.352661 versus0.374173 eV/A. The maximum per-atom
force-vector difference is0.402772 eV/A at zero-index17 (fixed). Among movable
atoms it is0.252698 eV/A; all-component force RMSE is0.086228 eV/A.
Consequently this is not merely an energy offset that can be ignored for Dimer.
The data establish a different collinear magnetic solution, not a proven global
magnetic minimum or a complete explanation of the earlier SCF divergences.

Per-atom values and hashes: per_atom_comparison.csv and comparison.json.
Reproducer: archive/scf_magnetic_recovery_20260913/compare.py (writes new review
artifacts, refuses to overwrite the CSV). Original outputs remain preserved.

## One proposed controlled test

Only replace MAGMOM with the50 final projected local moments of9752745, in the
verified original atom order; keep the current near-linear mixing parameters
and every other INCAR tag unchanged. Use a new empty directory with the same
POSCAR/KPOINTS/POTCAR and launcher; do not copy9754301 WAVECAR/CHGCAR.
Expected cold-start behavior must be verified as ISTART0/ICHARG2 at runtime.
Do not add NUPDOWN or local moment constraints. This tests an initial seed,
not a forced final magnetic state; projected moments cannot reconstruct the
full charge/spin density or guarantee recovery of the baseline solution.

MAGMOM initializes local moments in a cold start; when restarting with an
existing magnetic density it does not reset the local moments. Source:
https://vasp.at/wiki/MAGMOM

Accept only actual EDIFF convergence and normal termination, then compare
energy, local/total magnetization and forces against9752745. All-positive Fe
alone is insufficient. A new different solution requires review; a higher
energy does not authorize automatic rejection as numerically invalid.
After successful low-energy-branch recovery, verify saved-state restart before
any separately gated Dimer. If this seed fails, do not repeat it unchanged.

## Validation and boundaries

Reproducer executed:50 magnetization rows and50x3 forces in both outputs;
finite data, PBC equivalence and fixed masks passed. Candidate contains exactly
the extracted50 values; pymatgen comparison proves MAGMOM is the only changed
tag. Custodian read-only validate returned no blockers or warnings. Python
compile and targeted Ruff passed. No model/DFT calculation ran for validation.
Runtime recovery remains untested. This candidate is specific to this exact
structure and is not a new global Fe initialization policy.
