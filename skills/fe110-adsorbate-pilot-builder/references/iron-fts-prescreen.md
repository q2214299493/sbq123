# Iron Fischer-Tropsch adsorption pre-screen

Use this reference for C/H/O intermediates on the active true Fe(110) branch.
Use the chemical ranks below only to formulate retrieval terms and review
transferability. They cannot seed a calculation without accepted local,
whitelist, or authoritative-literature stable-structure evidence.
Do not reuse these site names or rankings on Fe(100), Fe(111), iron carbide, or
iron oxide. Stop with `fe110_only_rule_not_transferable`.

## Required reasoning

1. Identify the exact isomer and connectivity. Never infer an oxygenate from a
   molecular formula alone.
2. Mark every radical center and the gas/reference spin branch.
3. Count the existing sigma bonds and substituents at each potential carbon
   anchor. Assign a reviewed carbon coordination-demand class from 0 to 4.
4. Classify each O as atomic/oxyl, alkoxy radical, carbonyl, hydroxyl, or neutral
   water/alcohol donor.
5. Apply functional overrides after the carbon score:
   - carbonyl pi activation can place eta2(C,O) ahead of end-on motifs;
   - hydroxyl O is normally secondary, not an O-only primary anchor;
   - saturated closed-shell species carry weak-binding/desorption risk.
6. Penalize high coordination when H, OH, or a carbon chain would overlap Fe.
7. On Fe(110), compare long and short bridges using molecular width and row
   direction. Do not treat them as interchangeable.
8. For C2+ species, score each carbon independently. Test terminal radical,
   unsaturated, or heteroatom-adjacent carbons first; then test only
   symmetry-inequivalent along-row/across-row orientations and credible
   multidentate modes.

## C2 multi-center modes

- Alkyne: compare `di_sigma_long` and `di_sigma_short`; both carbons bind
  different Fe atoms and the C-C axis stays near-parallel to the surface.
- Vinyl radical: test radical-C top, eta2(C,C), then radical-C long bridge.
- Alkene: compare di-sigma long, di-sigma short, and pi-top. Do not replace
  these with separate single-C top/hollow sweeps.
- Alkyl radical: bind the radical carbon at top, then one reviewed bridge; keep
  the chain away from Fe.
- C2 carbonyl: score the carbonyl C and apply eta2(C,O); compare only
  symmetry-inequivalent methyl/chain directions.
- Neutral C2 alcohol: use O-top orientation variants; keep dissociative
  alkoxy+H as a separately labelled state.

## Carbon coordination-demand ladder

- 4, bare C: hollow and bridge candidates may be required.
- 3, highly unsaturated/carbyne-like C: long bridge, then short bridge; hollow
  is not automatically first for substituted species.
- 2, carbene-like C with two sigma bonds: long/short bridge before top.
- 1, carbon radical with three sigma bonds: top before bridge.
- 0, saturated C: top-like weak contact or gas-like behavior; do not force
  chemisorption.

The ladder is not a bond-order calculator. Review resonance, carbonyl pi
activation, radical localization, and steric accessibility before assigning the
class.

## Evidence-controlled candidate selection

- Reuse compatible reviewed local structures when available.
- Otherwise search the approved whitelist first. A usable exact match stops
  retrieval; only `NO_WHITELIST_MATCH` permits authoritative-journal search.
- Keep all and only the unique stable configurations supported by accepted
  evidence. Do not impose a two-, three-, or four-candidate budget.
- Treat distinct stable orientations at one nominal site as distinct motifs;
  remove symmetry-equivalent duplicates.
- Keep dissociated products under explicit product labels; never mix them with
  intact adsorption candidates.

Machine-readable rules and user-reviewed calibration profiles live in
`configs/adsmind_lite/iron_fts_prescreen.yaml`.
