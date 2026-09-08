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

- Candidate count: exactly the unique stable motifs supported by accepted
  local, whitelist, or fallback literature evidence.
- External evidence only selects and ranks motifs and supplies reviewed initial
  geometry references. External energies remain relative-order provenance and
  cannot enter local result tables or Excel.
- Unknown species: `NEEDS_WHITELIST`; `NO_WHITELIST_MATCH` then requires the
  authoritative-journal stage, never an automatic site sweep.
- H2O on the active Fe(110) branch: top-like O-bound molecular starts only;
  retain at most two symmetry-inequivalent orientations.
- CHO/formyl: prioritize side-on C/O dual-center `h-lb-h`; require a reviewed
  multi-anchor template before construction.
- Screening relaxations stop at `NSW=80` for review. Only plausible,
  nonduplicate, progressing candidates continue from `CONTCAR`.

The pre-screen is a decision gate, not a claim that chemical intuition proves a
global minimum. New relaxed evidence must update the compact memory and rules.

For iron Fischer-Tropsch C/H/O intermediates, the planner first loads
`configs/adsmind_lite/iron_fts_prescreen.yaml`. It distinguishes carbon
coordination demand, radical localization, carbonyl/hydroxyl/alkoxy O roles,
steric accessibility, and symmetry-inequivalent directions along/across Fe
rows. Formula-only or element-only ranking is not accepted.
For C2 species it also separates di-sigma long/short directions, eta2(C,C),
pi-top, terminal-radical anchoring, carbonyl modes, and chain-orientation
variants. Multi-center output stays review-blocked until a structure template
passes geometry checks.

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
- `evidence_gate.py`: whitelist-stop and authoritative-literature fallback decision.
- `relaxed_analysis.py`: geometry, connectivity, and plausibility analysis.
- `state_deduplication.py`: RMSD/energy duplicate grouping.
- `candidate_export.py`: final selection and copy-out.
- `core.py`: small stable facade containing only end-to-end operations and shared serialization helpers.
- `scripts/workflow_geometry.py`: shared slab-PBC, distance, relative-coordinate, and element-expansion primitives.

Fe(110) site and anchor geometry remains owned only by
`scripts/adsorption/build_fe110_adsorption.py`.

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
