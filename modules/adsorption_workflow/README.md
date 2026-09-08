# Adsorption and Endpoint Workflow

## Purpose

Routing and ownership come from `configs/skill_routing.yaml`; scientific values
come from the owning configs linked there. This README is procedural guidance,
not a second machine-rule source.

Generate, relax, validate, and compare adsorption/coadsorption states and provide compatible reaction endpoints.

## Inputs

- converged clean slab and gas/reference states
- adsorbate identity, coverage, site strategy, and structure source
- convergence-backed INCAR/KPOINTS/POTCAR family
- evidence-gated site/orientation provenance: whitelist first, authoritative
  literature only after `NO_WHITELIST_MATCH`

## Execution Backends

`configs/execution_backends.yaml` is the machine-readable backend contract.
Every transfer must validate against `configs/aqcat25_handoff.schema.json` with
`scripts/aqcat25_handoff.py` before leaving `work`, before GPU execution, before
GPU return, and after return. Adsorbate atoms, anchors, internal-bond or
separation constraints, and monitored pairs come from the manifest; the GPU
runner must not infer a fixed C/O composition.
After the evidence and initial-structure gates pass, `BUCT(sbq)` / `MZ73` uses
AQCat25 to pre-relax and rank adsorption candidates. Those energies, forces,
geometries, and rankings remain predictions: they cannot delete an
evidence-required motif, prove the final adsorption site/global minimum, enter
adsorption-energy tables, or replace VASP. GPU outputs return through `work`
for geometry, chemistry, provenance, compatibility, and duplicate review.
Only `sunboquan-codex` runs adsorption VASP relaxations and optional compatible
final statics; neither backend submits automatically.

AQCat25 ranking additionally requires an `in_domain` result from
`configs/aqcat25_domain_gate.yaml`. The current empirical gate covers only
near-relaxed Fe45 adsorption structures containing Fe/H/C/O with 2--6
adsorbate atoms. It does not establish per-candidate uncertainty or a
transition-state/path domain.

## Workflow

1. Run `modules/catalysis_data_retrieval/` when external candidates are needed, then register the clean slab, gas/reference, and candidate structure provenance.
2. Run the chemistry-aware candidate pre-screen, then generate exactly the
   unique stable motifs supported by accepted evidence. Surface site classes
   are a geometric dictionary, not a mandatory sweep. Choose binding
   atoms/denticity, orientation, intact versus dissociative state, and only then
   the needed projection. Two supported motifs produce two candidates; four are
   generated only when four stable motifs are supported.
   Use external stability order to prioritize candidates and use reported bond
   lengths, angles, heights, and orientations only as reviewed initial-geometry
   references. Never treat reported external energies as local results.
3. Send the evidence-accepted candidates to AQCat25 on `BUCT(sbq)` for ML
   pre-relaxation and ranking. Return every result to `work` with structure,
   model/checkpoint, optimizer, unit, compatibility, and domain-status hashes.
   Do not remove an evidence-required motif solely from the ML prediction.
4. Review predicted final chemistry, contacts, site, duplicate class, and
   out-of-domain status in `work`; only reviewed structures may enter VASP
   input preparation.
5. Select the adsorption/endpoint method here, then use `modules/incar_custodian/` for structured INCAR generation or recovery with species-separated `MAGMOM`.
6. Check internal bonds, nearest surface contacts, minimum contact, periodic branch, and Selective Dynamics.
7. Submit only to `sunboquan-codex` through `docs/01_METHOD_PROTOCOL.md`; record the job and every status event.
8. Separate scheduler completion from `reached required accuracy`, force convergence, and geometry validity.
9. Assign final chemical identity with `chemical-plausibility-gate`: final species, chemical event, final site, and whether the structure is `PASS`, `NEEDS_REVIEW`, `RECLASSIFY`, or `REJECT`.
10. Before extracting an adsorption energy, verify that every term uses `GGA=PE`, the same PAW-PBE POTCAR family, `ENCUT=400 eV`, and one compatible system/stage branch. Fe-containing surface terms use the active final `OUTCAR` `TOTEN` convention with `ISMEAR=1`, `SIGMA=0.20 eV`; closed-shell gas-phase CO uses its separately validated `ISPIN=1` reference branch without `MAGMOM`. For the same surface family, require the same lateral cell, layer count, vacuum, fixed-layer rule, dipole policy, and slab k-mesh.
11. Extract total and adsorption energies only from compatible VASP references and preserve units and source files. A separate single-point is not required for an ionically converged, geometry-valid production relaxation. Existing `SIGMA=0.10 eV` statics are optional checks and cannot be mixed with the active `SIGMA=0.20 eV` surface-energy chain. Metals and oxides may use separately converged smearing/magnetic/DFT+U groups; do not mix groups in one energy difference.
12. Promote only VASP-converged, chemically valid structures as endpoints.
13. In the same completion workflow, automatically register every reviewed
    VASP adsorption/coadsorption result through the canonical append-only
    `registry-write plan/apply` interface. A separate user reminder or approval
    is not required for this registration. The accepted-result record requires
    normal termination, electronic convergence, ionic/force convergence,
    compatibility, and chemistry-aware final-geometry acceptance. Registration
    is idempotent and must include scheduler evidence, final structure/output
    provenance, compatible final `OUTCAR` `TOTEN`, final movable-atom force, and
    the scientific review. Failed, incomplete, incompatible, duplicate, or
    unreviewed calculations retain their truthful status and cannot be inserted
    as accepted results. Do not infer an adsorption energy when the clean-slab
    and adsorbate reference tuple is incomplete; Excel promotion remains a
    separate gate.

### Chemistry-aware pre-screen and staged relaxation

Use `configs/adsmind_lite/prescreen_rules.yaml` through:

```bash
python -m scripts.adsmind_lite.plan_adsorption_candidates \
  --species H2O,CHO_formyl
```

The planner applies accepted local outcomes directly. Otherwise it requires the
whitelist-first `modules/catalysis_data_retrieval/` gate. A usable whitelist
match stops retrieval. `NO_WHITELIST_MATCH` triggers the controlled
authoritative-journal stage; failure there remains `NEEDS_REVIEW`. Chemical
heuristics may form search terms but cannot generate candidates. Multidentate
and same-site orientation variants require reviewed templates.

For Fischer-Tropsch intermediates, use the coordination-demand ladder and
oxygen-role rules in `configs/adsmind_lite/iron_fts_prescreen.yaml`. Require
isomer-specific connectivity; score each carbon separately for C2+ species;
then apply carbonyl eta2, hydroxyl, steric, and Fe-row orientation corrections.
This rule set is Fe(110)-only. Do not use it for Fe(100), Fe(111), carbide, or
oxide surfaces; the planner rejects those surface names.

Pilot relaxations use an 80-step screening stage. Continue from the screening
`CONTCAR` only when the intended or reclassifiable chemistry remains plausible,
the candidate is not a duplicate, and forces/energies still make meaningful
progress. This stage limit changes workflow scheduling, not the compatible DFT
energy method. Never stop a live calculation automatically.

## Fe(110) Site-Generation Contract

Use `scripts/adsorption/build_fe110_adsorption.py`; do not hand-code per-adsorbate site coordinates. This file owns both site generation and clean-reference nearest-class Fe(110) classification, while `configs/adsmind_lite/site_rules.yaml` and `analysis_rules.yaml` own the tolerances. AdsMind Lite imports these functions instead of maintaining a second Fe(110) rule set. Pair topology is fixed by the clean relaxed slab and is not reclustered on each adsorbate-distorted slab.

1. Identify the highest-z Fe layer from the clean relaxed slab.
2. Build `top` from one top-layer Fe projection.
3. Cluster top-layer Fe-Fe distances under xy PBC. The shortest class defines `short_bridge`; the next distinct class defines `long_bridge`.
4. Build `hollow` from the centroid of three adjacent top-layer Fe atoms with two short and one long triangle edges. Reject any hollow coinciding with an Fe-Fe midpoint.
5. Deduplicate the geometric projections and validate their identities.
6. Place adsorbates only on projections selected by an evidence-gated motif
   plan; do not enumerate the full dictionary automatically.

Generate reviewable POSCARs only from a completed evidence-gated plan with:

```bash
python -m scripts.adsmind_lite.generate_adsorption_candidates \
  --surface CLEAN_RELAXED_POSCAR_OR_CONTCAR \
  --sites REVIEWED_SITES_JSON \
  --adsorbates EXACT_SPECIES \
  --plan EVIDENCE_GATED_PLAN_JSON \
  --output OUTPUT_ROOT
```

This command generates structures only; it never submits calculations.

For a read-only audit of the Step 12A remote batch, use:

```bash
python -m scripts.adsmind_lite.audit_remote_fe110_batch
```

The audit reads only POSCAR/CONTCAR over SSH, checks initial and latest site classes, contacts, and molecular geometry, and prints compact JSON. It does not create a report or change remote jobs.

## Required Outputs

- reviewed POSCAR/CONTCAR copy, INCAR, KPOINTS, POTCAR metadata, LSF script
- scheduler and scientific status
- final species, chemical event, and plausibility status
- final energy, force, geometry, and adsorption-energy record
- file inventory and result provenance in the calculation registry

## Current Evidence

The active corrected true Fe(110) production dataset uses the user-selected
five-layer Fe45 slab and Gamma `5x5x1` branch. Any later layer-count comparison
is validation-only and cannot change or mix with production automatically.
Compatible adsorption states and gas/reference records remain **Needs
confirmation** until promoted through the current adsorption gate.

## Boundary

An adsorption state may be a NEB endpoint, but a tilted or stretched intermediate is not automatically a stable endpoint. Adsorption convergence does not prove a transition state.

## Code ownership

- `scripts/adsorption/gas_vasp_common.py` owns the common gas-reference INCAR,
  KPOINTS, job script, POSCAR rendering, POTCAR metadata, and reusable C1
  geometry primitives.
- `build_gas_h2_chx.py`, `build_gas_cho_chxo.py`,
  `build_gas_oxygenated_isomers.py`, and
  `build_gas_step12a_references.py` own only species metadata and initial
  geometry. `preflight_gas_references.py` validates the Step 12A gas-reference
  method, spin, cell, k-point, POTCAR-order, and job-script contract before
  backend handoff. Do not copy VASP templates back into species files.
- `build_fe110_adsorption.py` owns Fe(110) geometric sites. AdsMind Lite and
  species metadata may rank or select motifs but must not duplicate site or
  anchor-height geometry.
- `c2_coads_geometry.py` owns C₂/C₂O geometry templates,
  `c2_coads_catalog.py` owns the reviewed candidate definitions and UTF-8 labels,
  and `build_fe110_c2_coads.py` only writes POSCARs and manifests.

## Done Criteria

Every accepted state is converged, geometrically valid, traceable to compatible references, and registered with its input/output evidence in the same completion workflow without waiting for a separate user reminder.
