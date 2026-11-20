---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: MODULE_CONTRACT_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# AdsMind Lite

## Purpose

Provide a compact adsorption-configuration pre-screening stage between CARE-generated species and expensive VASP adsorption calculations:

```text
CARE species/network
  -> adsmind_lite chemistry-aware motif planning, site detection, candidate generation, validation, relaxed-state analysis, deduplication
  -> selected VASP adsorption structures
  -> NEB/DIMER
  -> MKM/KMC
```

This is a rule/config/script module, not a multi-agent AdsMind implementation and not a final physical-conclusion engine.

Fe(110) site geometry is not duplicated here: generation and nearest-class classification are imported from `scripts/adsorption/build_fe110_adsorption.py`. AdsMind Lite adds family routing, metadata, confidence, validation, and export gates.

## Scope and Staging

- `metallic_fe`: enabled. Fe(110) top, short bridge, long bridge, and true hollow detection remains the robust benchmark. Fe(100) and Fe(111) have deterministic exposed-layer detectors covered by synthetic BCC regression tests.
- `iron_carbide`: manifest-only, with medium default confidence. The first staged family supports `top_Fe`, `bridge_FeFe`, `hollow_FeFeFe`, `bridge_FeC_lattice`, and `hollow_FeFeC_lattice`. Every slab C must be explicitly identified as `C_lattice` or `C_ads` before C-bearing candidates pass.
- `iron_oxide`: manifest-only, with medium/low confidence. The staged family supports Fe top/coordination labels, Fe-Fe and Fe-O lattice bridges, explicit oxygen vacancies, and Fe-Fe-O lattice hollows. Every slab O must be identified as `O_lattice` or `O_ads` before O-bearing candidates pass.
- Carbide/oxide manifests provide labels; they are not automatic detectors. No full automation claim is made until real-surface fixtures and scientific validation exist.
- Oxygen vacancies require `site_role: vacancy_O`, an explicit risk tag, and explicit validation. Unvalidated hydroxylation and oxide H2O dissociation remain review-required.
- C2+ multidentate adsorption remains low-confidence and review-required.

The module does not run CARE, VASP, NEB, DIMER, MKM, or KMC and never submits jobs.

## Chemistry-aware candidate planning

Routing and ownership are defined only by `configs/skill_routing.yaml`.
Candidate policy is defined by `configs/adsmind_lite/prescreen_rules.yaml`,
external-evidence order by `evidence_gate.yaml`, and geometry thresholds by
`analysis_rules.yaml`; this README explains their use and does not override them.

Run `python -m scripts.adsmind_lite.plan_adsorption_candidates` before structure
generation. `configs/adsmind_lite/prescreen_rules.yaml` stores species-specific
motifs and reviewed suppression evidence without duplicating the Fe(110)
geometric site detector.

- Review the minimum number of chemically plausible, non-equivalent initial
  site/binding modes required by `prescreen_rules.yaml` before any partial batch.
  `candidate_count` counts initial configurations; `initial_motif_coverage`
  separately reports distinct modes, the requirement and any shortfall.
  Height, tilt, azimuth and configuration-ID changes at one unchanged anchoring
  mode do not increase coverage. A shortfall downgrades `READY` to `NEEDS_REVIEW`;
  retrieval and template blockers retain their existing status.
- Initial modes are hypotheses, not accepted stable minima. The plan keeps
  `final_stable_minima_count: null`; local DFT result validation owns that count.
  Do not pad missing modes or infer historical coverage from notes, suppression,
  or final sites. Review existing provenance before deciding whether work is
  missing; the planning gate never authorizes a historical rerun.
- External evidence only selects and ranks motifs and supplies reviewed initial
  geometry references. External energies remain relative-order provenance and
  cannot enter local result tables or Excel.
- Unknown species: `NEEDS_WHITELIST`; `NO_WHITELIST_MATCH` then requires the
  authoritative-journal stage, never an automatic site sweep.
- H2O's two retained O-top orientation variants cover one initial mode. The
  current local prior reports a coverage shortfall; it does not automatically
  add bridge/hollow structures or repeat historical calculations.
- CHO/formyl: prioritize side-on C/O dual-center `h-lb-h`; require a reviewed
  multi-anchor template before construction.
- Screening relaxations stop at `NSW=80` for review. Only plausible,
  nonduplicate, progressing candidates continue from `CONTCAR`.

The pre-screen is a decision gate, not a claim that chemical intuition proves a
global minimum. New relaxed evidence must update the compact memory and rules.

Generation rechecks current coverage and source-bound external evidence for
the entire requested batch before writing any POSCAR. Cached `READY`, cached
coverage counts and cached policy values cannot bypass this check. Every
candidate retains `initial_motif` separately from its relaxed site so that ML
migration/dissociation cannot rewrite the original mode identity.

Initial generation must produce chemically plausible, distinct adsorption-site
structures; it does not require a lowest-energy or DFT-converged structure.
Before writing the first POSCAR, generation now runs the existing candidate
validator in memory and checks internal connectivity against the configured
molecule, internal overlap, compressed bonds (shorter than the configured
reference length divided by the existing connectivity scale), buried atoms,
and surface/anchor contacts. Multidentate poses use the existing CARE seed
contact bounds, without inheriting a single-anchor height or distance range.
The molecular reference must be present in the species rule. These are initial
geometry screens; they do not grade stability or establish an accepted result.

Diversity is checked from actual mapped anchors, independently of motif labels.
When the request specifies different site classes, use the generator's
`--require-distinct-site-classes` option. It applies the same configured
minimum to the realized primary site classes before writing any POSCAR.
A single unchanged binding atom/site counts once even if molecular azimuth,
tilt or height changes. Fe(110) resolves each anchor to a canonical site center
before comparing multiple anchors. Fe45 uses the existing clean-slab,
face-preserving symmetries and the site deduplication tolerance. Coordinate
offsets within the same resolved site and edits to labels count as one mode.
One representative is emitted per actual mode, with omitted
same-site variant IDs recorded in its metadata. Fewer than the required
number of actual modes blocks the whole batch before output. Each emitted
record reports `initial_geometry_validation: PASS`, actual anchor site classes,
and `scientific_stability: NOT_ASSESSED` separately. Existing source-review,
scientific-acceptance and execution gates retain their roles.

When a motif supplies `reviewed_structure_template`, the generator consumes
its coordinates rather than the configured default molecule. The descriptor
contains exactly `path` and `sha256`. The implemented format is an unwrapped,
adsorbate-only POSCAR with positive scale, Direct/Cartesian coordinates and
the exact `atom_symbols` order from `adsorbate_rules.yaml`. All template atom
flags must be unconstrained. Hashing and parsing use the same bytes.
The configured anchor is translated to the selected site using the existing
Fe-anchor distance rule; template internal geometry and tilt are retained,
then the planned azimuth is applied. Slab cell, atom mapping and constraints
remain governed by the existing builder. Output `geometry_source` records the
consumed path/hash, format and units separately from `initial_motif`.

Multi-anchor modes consume a full slab/adsorbate POSCAR in the current slab
frame. The atom order must be the complete original slab followed by the
configured adsorbate `atom_symbols`; the cell, slab coordinates and slab flags
must match the input slab (absolute numeric tolerance 1e-8, no relative tolerance).
Adsorbate flags must be unconstrained. These poses retain every adsorbate
coordinate, including unwrapped x/y coordinates: no configured height,
translation or azimuth is applied. `orientation_degrees` must be zero.

The motif must supply the same hash-bound descriptor plus
`binding_atom_indices_zero_based`, a complete mapping from its distinct
`binding_atoms` labels to distinct, actual integer adsorbate-local indices.
Repeated elements such as `C1` and `C2` require explicit indices; element names
are never used to guess an atom. The first entry of `binding_atoms` selects
the primary anchor and must be a preferred, non-forbidden binding element.
All mapped anchors must be non-forbidden. `generator_site_class` selects its
primary canonical Fe(110) site, checked against the full pose by the existing
site classifier. The full `site_pattern` remains the initial-mode identity;
it is not replaced by the primary site. For example, a reviewed two-carbon
motif may carry the mapping `{"C1": 0, "C2": 1}` with
`binding_atoms: [C1, C2]`; this example supplies no physical geometry or approval.

Output records both adsorbate-local and structure-level binding atom indices,
together with `geometry_source.format: slab_adsorbate_POSCAR`. Multi-anchor
outputs remain low-confidence and review-required. Relaxation analysis compares
the initial and relaxed site class of every mapped anchor, so a secondary
anchor's site-class change is reported even when the primary anchor stays put.

To import already reviewed local full poses, pass
`--reviewed-templates BUNDLE.json` to `plan_adsorption_candidates` and keep
the resulting plan for generation and `validate_candidates --plan PLAN.json`.
The import is scoped to the exact species and clean Fe(110) slab in the bundle.
It can use a reviewed molecular reference for a species absent from the shared
catalog. Where a catalog entry exists, its identity and binding constraints apply.

The bundle has six fields:

- `species` and `surface`: the exact species label and `Fe110`.
- `slab_sha256`: the SHA256 of the actual clean slab input bytes.
- `molecular_reference`: `atom_symbols` and unwrapped
  `relative_cartesian_angstrom` in the reviewed adsorbate atom order.
- `motifs`: `motif_id`, `site_pattern`, `binding_mode`, `binding_atoms`,
  `generator_site_class`, `binding_atom_indices_zero_based`,
  `reviewed_structure_template` (path and SHA256), and `geometry_origin`.
  The origin is `archived_local`, `literature_guided`, or `local_construction`.
  Use absolute template paths so the same plan resolves from any directory.
- `evidence`: the existing claim, snapshot, review and transfer record for
  `candidate_guidance` in `surface_adsorption`. The claim's
  `record_sha256` is the owning `evidence_lifecycle.record_subject` digest
  of the bundle. The review and transfer follow that module's existing hash
  bindings. Compatibility binds `species`, `surface` and `slab_sha256`.

For a locally constructed pose, record the geometry rationale in the source
snapshot, including the anchor assignments and any assumptions. Accept the
exact pose and mapping through the existing candidate review before including
it in an approved bundle. A published image or distance can guide a draft.
It does not supply reviewed coordinates on the local slab. Generation checks
the source binding again, including the slab and each template hash. It only
writes a complete batch after the initial geometry and actual site coverage
checks pass. Readback checks the POSCAR beside each candidate's metadata against
the reviewed coordinates, constraints and atom mapping in output order.

Unmapped atom order, incompatible slabs, constrained adsorbate atoms, a different
single binding atom and invalid or stale templates are blocked before any
batch output. There is no fallback to default geometry when a supplied/required
template cannot be consumed. `--available-template` motif IDs alone do not
provide geometry or authorize generation. Configured geometry remains the
source for local-prior motifs that require no template. The three distinct
reviewed starting modes and source-evidence gates still apply; this support
does not supply missing scientific templates or authorize any calculation.

For iron Fischer-Tropsch C/H/O intermediates, the planner first loads
`configs/adsmind_lite/iron_fts_prescreen.yaml`. It distinguishes carbon
coordination demand, radical localization, carbonyl/hydroxyl/alkoxy O roles,
steric accessibility, and symmetry-inequivalent directions along/across Fe
rows. Formula-only or element-only ranking is not accepted.
For C2 species it also separates di-sigma long/short directions, eta2(C,C),
pi-top, terminal-radical anchoring, carbonyl modes, and chain-orientation
variants. Multi-center construction uses the mapped full-pose template contract
above; it never synthesizes extra anchors from the single-anchor defaults.

For an uncalibrated species, `--species-features FEATURES.yaml` activates the
feature-based FTS planner as a retrieval-query helper. Its output is stored
under `search_hypotheses`, always has `candidate_count: 0`, and cannot be passed
to structure generation until whitelist or permitted literature evidence
returns an accepted motif.

## Inputs

- a clean slab structure readable by ASE;
- `configs/adsmind_lite/surfaces.yaml`;
- `configs/adsmind_lite/site_rules.yaml`;
- `configs/adsmind_lite/adsorbate_rules.yaml`;
- a mandatory `site_manifest.yaml` for carbide and oxide surfaces;
- candidate or relaxed POSCAR/CONTCAR structures plus compact metadata.

## Commands

Install the lightweight structure dependency with `python -m pip install ".[adsmind]"`. MLFF packages are never required for `no_relax`.

```bash
python -m scripts.adsmind_lite.detect_surface_sites \
  --surface calculations/true_fe110_clean_20260629/POSCAR \
  --surface-name Fe110 \
  --surface-family metallic_fe \
  --output sites.json

python -m scripts.adsmind_lite.generate_adsorption_candidates \
  --surface calculations/true_fe110_clean_20260629/POSCAR \
  --sites sites.json \
  --adsorbates CO,H,O,OH,H2O,C \
  --plan data/reports/prescreen_plan.json \
  --output data/candidates

python -m scripts.adsmind_lite.plan_adsorption_candidates \
  --species H2O,CHO_formyl \
  --output data/reports/prescreen_plan.json

python -m scripts.adsmind_lite.plan_adsorption_candidates \
  --species unseen_CH2_radical \
  --species-features species_features.yaml \
  --output data/reports/retrieval_hypotheses.json

python -m scripts.adsmind_lite.validate_candidates \
  --candidate-root data/candidates \
  --output data/reports/validation.jsonl
```

For a non-metallic surface, pass `--site-manifest` to `detect_surface_sites.py`. The manifest owns exact-slab 1-based atom roles, enabled classes, explicit fractional site coordinates, support atoms, risk tags, and validation state.

Relaxed-state analysis, deduplication, and export are handled by the corresponding scripts under `scripts/adsmind_lite/`. Export includes recommended high-confidence and validated, recommended medium-confidence records by default. Use `--no-include-medium` for high-only export. Low-confidence and `needs_review` records require explicit override flags.

## Code Layout

- `adsmind_common.py`: JSON/YAML contracts, ASE loading, and compact output.
- `site_detection.py`: automatic and manifest-gated surface sites.
- `candidate_generation.py`: adsorbate placement and candidate metadata.
- `motif_coverage.py`: initial-mode identity, coverage and generation preflight.
- `evidence_gate.py`: whitelist-stop and authoritative-literature fallback decision.
- `relaxed_analysis.py`: geometry, connectivity, and plausibility analysis.
- `state_deduplication.py`: RMSD/energy duplicate grouping.
- `candidate_export.py`: final selection and copy-out.
- `core.py`: small stable facade containing only end-to-end operations and shared serialization helpers.
- `scripts/workflow_geometry.py`: shared slab-PBC, distance, relative-coordinate, and element-expansion primitives.

Fe(110) site and anchor geometry remains owned only by
`scripts/adsorption/build_fe110_adsorption.py`.

The global `surface-adsorption-builder` skill is an installed copy of the
repository skill. Deploy its `SKILL.md`, `agents/openai.yaml` and CO compatibility
launcher from `skills/surface-adsorption-builder/` together. The launcher accepts
just the slab POSCAR: it finds a unique project above cwd or the slab and runs
this module with `--prepare-missing` (CO, `no_relax` only). Missing sites are
detected afresh. A unique `plan.json` or `prescreen_plan.json` beside the slab is
reused without rewriting; otherwise the canonical planner writes a draft.
Missing evidence/review blocks generation and retains preparation artifacts in
`_inputs/`. Default output is a fresh numbered directory under
`modules/adsmind_lite/data/candidates/co_candidates`. An explicit output must
not exist. All four launcher path options remain available; ambiguous project
or sidecar choices require an explicit selection. Ordinary generator calls
still require `--sites`, `--plan` and `--output`. The launcher contains no
separate placement algorithm or automatic approval. Legacy height/bond-length
overrides and fixed-site sweeps are rejected.

## Compact Output Contract

Detailed records are JSON/JSONL. Stdout is limited to short counts or this table:

```text
adsorbate planned_site relaxed_site slip dissociated duplicate keep confidence needs_review reason_code
```

Never print full VASP structures, trajectories, or output files. Unknown or potentially large shell output remains byte-capped by the repository command rules.

## Data Layout

Runtime data belongs under `modules/adsmind_lite/data/` or another user-selected output root:

- `surfaces/`
- `adsorbates/`
- `candidates/`
- `relaxed/`
- `reports/`
- `vasp_ready_adsorption/`

Durable compact memory lives under `modules/adsmind_lite/memory/`.

## Done Criteria

- Fe(110) dry-run returns standardized top, distinct short/long bridge, and true hollow IDs.
- candidates are generated only from an evidence-gated plan, with no fixed site count;
- validation writes compact JSONL without large terminal output;
- chemical slip and dissociation are detected from relaxed structures;
- duplicate relaxed states are marked using site/connectivity/RMSD and optional energy tolerance;
- only recommended high-confidence or validation-selected medium-confidence structures are exported by default;
- Fe(100) and Fe(111) metallic detectors pass regression fixtures without displacing Fe(110) as the benchmark;
- carbide and oxide classes work through explicit manifests without overstating automatic detector support;
- high-risk carbide/oxide states require explicit labels or `needs_review`.
