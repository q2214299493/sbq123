# Fe(110) GPU2142 supplemental review and CHCO repair

Scope: collect/review five AQCat25 returns; deduplicate the four intact graphs; rebuild only failed03_extra2. No new GPU/VASP execution or accepted-energy registration.

| Candidate | Review outcome | CC / CO / CH (A) | Primary geometry |
|---|---|---|---|
| 01_extra1 | Keep distinct predicted candidate | 1.3377 / -- / 1.0872 | CH-C45 near top, bareC46 near long bridge |
| 02_extra1 | Hold as possible duplicate of live02_cfg2, not an accepted duplicate minimum | 1.4116 / -- / 1.0970,1.0946 | CH2-C45 near top, bareC46 near long bridge |
| 02_extra2 | Keep distinct predicted candidate; off-symmetry CH2 site warning | 1.3964 / -- / 1.0946,1.0998 | bareC46 long bridge; CH2-C45 displaced from ideal top |
| 03_extra1 | Keep distinct predicted candidate; off-bridge O site warning | 1.4152 / 1.2862 / 1.1004 | CH-C45 long bridge, C46 hollow, O47 offset toward short bridge |
| 03_extra2 | Reject returned structure as target CHCO; preserve CH+CO fragments as failure evidence | 2.9355 / 1.1896 / 1.1051 | CC dissociation, not a retained intact adsorption state |

All five producer exit records, returned structures and source-handoff hashes validate. All five reached the bounded ML fmax0.10eV/A threshold, but optimization convergence does not override chemistry. The four intact graphs preserve cell, atom order and bottom18Fe. These are ML-predicted geometries, not VASP final sites, adsorption energies or proven stable minima. Strict site classifier returns unknown for the secondary CH2-C45 site of02_extra2 (nearest-top lateral0.7327A) and O47 of03_extra1 (nearest-short-bridge lateral0.6308A); these offsets are explicitly retained for review, not silently relabelled as ideal sites.

## Duplicate evidence

Compare each return against previous retained same-checkpoint GPU candidates, all10VASP inputs, available live VASP CONTCAR snapshots, and earlier intact members of this batch. Use36top-side-preserving clean-slab symmetries, xy PBC and identical-H permutations, with actual relaxed adsorption height retained. No arbitrary molecule rotation/translation. Configured geometry tolerance0.20A and same-checkpoint GPU energy tolerance0.05eV are unchanged.

No same-checkpoint GPU duplicate was found.02_extra1 is geometrically close to the sampled live02_cfg2 CONTCAR (RMSD0.18567A). Since that is a live geometry snapshot and no compatible final energy comparison exists, this is **a possible duplicate/standby**, not proof of the same final minimum. Do not remove its source/output files or claim an additional stable state.03_extra1 differs from the direct-VASP03 input by1.18664A;01_extra1 and02_extra2 have nearest sampled differences0.87057A and0.43431A. Snapshot-based screening must be revisited if existing VASP structures materially change.

## Single repaired initial candidate

`03_extra2_repair_v1`: reuse the original intact exact CARE `[CH][C][O]` template, not separated CH+CO fragments. Anchor changes from CH-C45 long bridge to centralC46 short bridge. Orient the chain along the long Fe rows, azimuth0degrees, tilt0degrees; centralC46–nearestFe2.20A. Whole-adsorbate rigid transform preserves CC1.534923A, CO1.401380A and CH1.061876A. Other nearest contacts: C45–Fe2.1640A, O47–Fe2.1962A, H48–Fe2.1372A; minimum height above topFe1.8279A. Initial canonical geometry checks pass without warnings. Minimum surface-symmetry RMSD to prior03seeds/intact return is0.40653A after height-only differences are removed.

Only original bottom18Fe are fixed; no artificial bond/height/site restraint is introduced. The hypothesized benefit is better co-placement of the intact chain instead of transverse competition between anchors. **This is not a proven cause of the prior failure or a guarantee of successful relaxation.** No checkpoint/DFT settings were changed or fine-tuning performed. New candidate remains unrelaxed and unsubmitted.

## Files and validation

- Raw five returns: `calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_v1/*/output/job_2142/`.
- Hash/chemistry/contact/site/duplicate evidence: `calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_review_v1/review.json`.
- Read-only VASP structure snapshot: that review directory's `vasp_structure_snapshot/`; no scheduler completion or energy claim follows from these files.
- New geometry/recipe/hash: `calculations/fe110_five_c2_adsorption_20261006/supplement_repair_v1/repair_review.json` and `03_extra2_repair_v1/POSCAR`.
- Visual comparison: `supplement_repair_v1/repair_comparison.png` (original / failed return / rebuilt seed).

Python syntax and focused Ruff pass.12related tests pass, including actual four-intact/one-fragmented results, preservation of relaxed height during duplicate comparison, live-VASP geometry-only classification and new-seed invariants. Visual inspection passed. No model or expensive DFT calculation was launched as a test.

Next: authorize one bounded AQCat25 pre-relaxation of the repaired seed after review. Three distinct intact candidates remain available for separate VASP input review;02_extra1 stays on hold. Final relaxed sites and distinct minima require VASP validation.
