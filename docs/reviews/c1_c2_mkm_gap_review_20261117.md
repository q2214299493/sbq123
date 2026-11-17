# Fe(110) C1–C2 kinetic intake refresh — 2026-11-17

## Result

Read-only registry schema9 snapshot still contains four accepted electronic
barrier sets and six eligible Grade-A TS validations. There are no registered
ZPE/Gibbs/entropy/free-energy result-name matches in the queried inventory;
this is not proof that raw frequencies or unregistered corrections are absent.
The 14-row intake remains a draft, not an accepted site-balanced network or
formal CATKINAS input. No kinetics calculation, DFT, GPU job or registry write.

User-facing table and concrete next actions:
`outputs/c1_c2_mkm_inventory_20261117_v1/C1-C2能垒与补算清单.md`.
Machine-readable sources: `inventory.json` and `verification.json` in that
directory. Previous Nov16 output was not overwritten.

## Existing evidence and actual gaps

- CO dissociation: IS9558184/TS9656664/FS9622455; electronic forward/reverse
  barriers1.350209/2.056573 eV, reaction energy-0.706364 eV.
- C+H→CH: IS-A9715450/TS9720181/FS9573951;
  0.887692/0.741467 eV, reaction energy0.146225 eV.
- CH+H→CH2 competition: IS-A9701350/TS9709074/FS9622444;
  0.554547/0.069742 eV, reaction energy0.484805 eV.
- MID→FS-A O–H formation: MID9737143/TS9746548/FS9725471;
  1.285827/0.894817 eV, reaction energy0.391010 eV.
- CH+CO: IS9839757/TS9998592/FS9842136, accepted Grade-A VFA2260;
  compatible electronic barrier still needs its separate review/registration.
- INT06→MID: INT069748648/CI9796856/MID9737143, Grade-A VFA9798421;
  likewise lacks a registered compatible barrier set. Neither case is missing
  a TS or automatically needs another saddle search.
- IS-A→INT06: located Dimer9833429 archive and all12 raw-source bindings.
  Archived maximum atomic force0.015998 eV/A and negative curvature pass their
  numerical checks, but final-mode review is still needs_review and no linked
  Grade-A validation was found. Review final direction/soft residuals before
  deciding local frequency validation. Do not label this a fully accepted TS.

All four registered sets use compatible SIGMA0.20 final OUTCAR TOTEN, not
frequency-job energies. No new unregistered barrier value was reported.
The existing TS eligibility flag does not provide activation free energies.

## Interfaces that must not be silently collapsed

CO-dissociation FS contains C+O; the C+H reactive IS has no spectator O. Separate
CH and CO energies do not replace the selected coadsorbed CH+CO IS. Coupling
FS9842136 and hydrogenation IS-A9725473 differ by H population and potentially
site/motif; connect them through reviewed surface-pool and reference conventions.
The H-transfer sequence has three elementary segments, not one common barrier.
Multi-dentate site footprints, pair probabilities, diffusion/encounter treatment
and lateral/coadsorption corrections remain explicit review items.

For C→CH FS9573951 the energy archive contains OUTCAR but no companion CONTCAR.
The accepted energy source hash and arithmetic pass. No POSCAR was substituted
for final geometry; locate/verify its archived terminal-structure link before
thermal work. This is not evidence that the calculation must be repeated.

## One next step

Prepare compatible-energy review packages for CH+CO and INT06→MID using existing
outputs, then obtain their own current reporting/registration gates. No new
scientific computation is implied. Subsequent work is consistent local-active-set
IS/TS/FS thermochemistry, reviewed reference/site interfaces and conditions.

A minimal reversible CH+CO reactive-pair transient or imposed-coverage model
can precede a complete feed model, but is not an overall steady-state TOF model.
CO/H2-fed steady-state prediction additionally requires H2 dissociation/recombination,
O→OH→H2O clearance, water release, and a physical product desorption/further-growth
boundary. Search existing evidence before new TS calculations. Adsorption/desorption
does not automatically require an additional saddle if a justified reversible
rate model is available. No arbitrary irreversible product sink.

## Validation and RSI

- Compile and targeted Ruff PASS. Four registered barrier sets were checked
  against12 source hashes, energy conventions and actual IS/TS/FS arithmetic.
  Three complete companion-geometry triplets have matching composition; the
  C→CH final-geometry link above remains unresolved rather than a composition fail.
- CH+CO endpoint energy sources(two), saddle files(two), and Dimer9833429 raw
  bindings(twelve) also pass current hash checks. Fourteen unique row IDs,
  explicit non-kinetic statuses and no scientific execution were independently checked.
- The repaired RSI entry was called exactly once via explicit resume of the old
  C1–C2 question: GENERATED,3 turns/5 read-only host actions,89.96 s. One existing
  check_registered_material trial policy was provided; recorded correspondence
  is not proof of scientific correctness or causal benefit, and no policy was promoted.
- RSI saw bounded/truncated excerpts and did not independently verify all rows;
  its recommendation is only to inspect existing records before new calculations.
  Detailed conclusions above rely on direct registry/source checks, not an RSI
  scientific signoff. No automatic retry or budget increase.
- RSI evidence:
  `C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/mkm_c1_c2_inventory_20261117_v1/`.
  Dashboard:
  `C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html`.

This intake uses the reaction-pathway, kinetic-data-schema and reaction-kinetics
skills to separate evidence, state interfaces and formal kinetic parameters.
External-data and TS-frequency routing were consulted; no new external motif,
kinetic parameter, TS grade or partition-function result was introduced.
