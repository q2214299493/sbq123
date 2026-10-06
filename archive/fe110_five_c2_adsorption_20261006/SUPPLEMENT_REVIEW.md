# Five additional intact Fe110 adsorption hypotheses

User request: 再补足其他的. Scope is local construction/review only. No new GPU/VASP job was submitted; existing9839748-9839757 inputs, reservations and jobs were not changed or queried in this step.

The candidates reuse the exact local CARE connectivity templates and canonical clean Fe45five-layer slab. Coordinates are changed by rigid adsorbate rotation/placement; internal geometry, atom order, cell and fixedFe0-17 are preserved. The canonical `generate_sites` and `anchor_cartesian_position` own the site coordinates. This is not a blind four-site sweep and not a literature claim of three stable minima. Existing bounded whitelist discovery and journal SI inspection remain background; no new external structure or energy was imported.

| Name | Chemical target | Main proposed placement | C-C/A | C-O/A | nearest Fe distances/A |
|---|---|---|---:|---:|
|01_extra1|C2H `[C][CH]`|BareC46 long bridge; CH end outward along x,25deg tilt|1.539|—|C45-Fe44:2.271;C46-Fe43:2.150;H47-Fe44:2.880|
|02_extra1|C2H2 `[C][CH2]`|BareC46 long bridge; CH2 end outward along x,35deg tilt|1.540|—|C45-Fe44:2.508;C46-Fe43:2.150;nearestH-Fe:2.644|
|02_extra2|C2H2 `[C][CH2]`|BareC46 short bridge; CH2 end outward along y,40deg tilt|1.540|—|C45-Fe43:2.852;C46-Fe41:2.150;nearestH-Fe:2.984|
|03_extra1|C2HO `[CH][C][O]`|C45 CH end short bridge; intact C-C-O chain along x,15deg tilt|1.535|1.401|C45-Fe41:2.350;C46-Fe44:2.680;O47-Fe39:3.023;H48-Fe43:2.024|
|03_extra2|C2HO `[CH][C][O]`|C45 CH end long bridge; intact C-C-O chain along y,10deg tilt|1.535|1.401|C45-Fe43:2.350;C46-Fe37:2.199;O47-Fe37:2.549;H48-Fe41:1.943|

All indices are zero-based. Nearest-Fe distances and projected site labels are geometric evidence, not proof of a chemical bond or final adsorption denticity. In02_extra2 the CH2 carbon is relatively far from Fe; this deliberately tests bare-C-primary binding rather than calling it bidentate. In03_extra1 O is outward, not O-anchored. In03_extra2 O has a possible secondary surface contact; the final state needs relaxation review.

The duplicate audit compares every added candidate to the three original starts of the same species, the intact retained GPU outputs, and earlier supplemental candidates. It uses top-side-preserving full clean-slab spglib symmetry operations, xy minimum images and identical-H permutations. Uniform z height offsets are removed, so height-only variants cannot pad the count. No arbitrary adsorbate rotation/lateral-centroid alignment is allowed. Closest RMSD values are0.942,0.745,1.004,1.177,1.810A, all above the project0.20A duplicate tolerance.

Validation: all5canonical geometry reviews pass without warnings; all5exported POSCARs were reparsed and checked for hashes, cell, all45Fe positions, flags and connectivity; Python syntax, focused Ruff and4tests pass (height-only duplicate, periodic/H-permutation duplicate, surface-symmetry handling, rigid-rotation bond invariance). The combined top/chain-side figure was inspected. The initial03_extra2 trial had a low H height; reducing the tilt and adjusting the C-Fe placement distance resolved the geometric issue before files were exported. No bond constraint or model was run.

Artifacts: `calculations/fe110_five_c2_adsorption_20261006/supplement_v1/`: five POSCARs, `candidate_review.json`, and `structure_review.png`. This supplies five additional initial candidates, making nominal candidate counts3/3/3/3/3 when combined with the ten submitted inputs. It does not establish15distinct optimized minima, final adsorption energies, global minima or checkpoint-domain validity for these new unrelaxed poses.

Next: user review of the five structures, followed by a separately authorized bounded AQCat25 pre-relaxation batch. Every GPU output must return to work for chemistry/duplicate/domain review before any new VASP submission.
