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

# Catalysis Data Retrieval

## Purpose

Provide the single external-data gate before any new catalysis calculation, including convergence campaigns, slab/adsorbate construction, adsorption and coadsorption states, endpoints, NEB/CI-NEB, DIMER, frequency setup, reaction networks, and kinetic-model parameter sourcing.

Monitoring or post-processing an already defined calculation does not rerun this gate unless a new external structure, path, or parameter is introduced.

## Source Boundary

First-stage whitelist searches may use only the sources and URL scopes in
`skills/catalysis-data-retrieval/references/sources.yaml`:

- Catalysis-Hub and CatApp
- Open Catalyst Project OC20/OC22
- OC20NEB and CatTSunami
- Materials Project Catalysis Explorer
- Materials Cloud Archive
- ioChem-BD
- NOMAD Catalysis

Local verified project files remain valid inputs. Official VASP/VTST
documentation may be used for software syntax and method behavior, but not as
an external structure/path database. Authoritative-journal literature is a
second-stage source only after the whitelist stage records
`NO_WHITELIST_MATCH`.

## Skill Routing

`configs/skill_routing.yaml` is the machine-readable authority. This module owns external structure/path/data retrieval; VASP, adsorption, NEB, DIMER, frequency, and kinetics skills only consume reviewed output.

For adsorption motifs only, this module may invoke chemistry literature
retrieval at that second stage. The article must be primary research in an authoritative peer-reviewed
chemistry/materials/catalysis journal with verified DOI and publisher URL,
exact surface and adsorbate matching, direct stable-structure evidence, and a
reviewed transferable geometry. Other scholarly work remains explicit-only.

## Gate

1. Define the target material, surface/facet, adsorbate/reaction, calculation stage, and desired data type.
2. If an image is supplied, inspect it and save reviewable visible features and uncertain inferences before producing text query terms. Never infer elements from display colors alone.
3. Ingest only whitelist-valid records with source URL, record ID, retrieval time, data type, license/access note, and scientific metadata.
4. Rank with BM25 plus a real sentence-embedding cosine score. Lexical-only mode is diagnostic and does not pass the production gate.
5. Return at most five results. Preserve component scores and explain local-system mismatches.
6. Human-review transferability before using any structure or path. Retrieved data never bypass endpoint, convergence, geometry, or TS validation.
7. If a usable whitelist motif exists, stop; literature retrieval is forbidden.
8. For an adsorption-site task with no usable motif, record
   `NO_WHITELIST_MATCH`, then search only authoritative journals under
   `configs/adsmind_lite/evidence_gate.yaml`. Other task types remain blocked.
9. Deduplicate by stable motif, not nominal site name. Return all and only the
   supported stable configurations; never pad to a fixed site sweep.
10. Rank the accepted motifs and extract only structure references needed to
    reduce local computation: sites, binding atoms, bond lengths, angles,
    surface heights, and orientations. Mark every reported external energy as
    relative-order reference only.

## Outputs

- normalized source records as JSONL
- image-query JSON when applicable
- `retrieval_top5.json` with BM25, semantic, and hybrid scores
- source/access warnings and transferability review
- a calculation-module handoff containing only accepted constraints or candidate references
- an evidence-gate decision recording whitelist stop or literature fallback,
  DOI/journal provenance, stable motifs, and rejected transferability claims

## Boundaries

This module does not perform DFT, accept a structure, infer missing scientific
values, or claim that database similarity proves transferability. It never
imports external energies into local results, the calculation registry, or
Excel. The owning scientific module keeps its own geometry, numerical, and
acceptance gates.

## Done Criteria

- every first-stage URL passes the whitelist validator
- literature is absent when a usable whitelist match exists
- every accepted fallback article has verified DOI/publisher provenance and an
  exact stable-motif match
- every result has traceable source metadata
- production output uses both BM25 and semantic ranking and contains at most five items
- image-derived claims are separated into visible facts and uncertain interpretations
- no scientific module contains a duplicate web/literature search implementation

## Evidence lifecycle and vector provenance (B3)

`scripts/adsmind_lite/evidence_lifecycle.py` owns the stages `IMPORTED`,
`SCHEMA_VALID`, `SOURCE_VERIFIED`, `CONTENT_BOUND`, `REVIEWED`, and
`TRANSFERABLE`. These are derived from supplied evidence, not trusted from
stored state flags. Source verification requires identity, a timezone-aware
retrieval timestamp, and an immutable reference to a SHA-256-bound snapshot.
Content must match a character span of that snapshot. An explicit reviewer,
timestamp, decision and scope bind the complete claim/source/content subject.
Transfer also requires the reviewed compatibility conditions and target domain.
Rejected reviews remain reviewed but cannot transfer. Source snapshots and
reviewer declarations are auditable records, not independent authentication of
the publisher or reviewer.

Claims retain their type: literature claim, expert opinion, model prediction,
calculated result, or reported experimental value. Opinions and predictions can
only transfer as candidate guidance; they never change into calculated results.
External energies remain excluded from local results and Excel.

The `evidence` envelope uses `claim`, `source`, `content`, `review`, and `transfer`
objects. `claim.record_sha256` binds the retrieved record (including motifs and
template references), excluding derived embedding and evidence fields. `source`
contains `identity`, `reference`, `retrieved_at`, `immutable_reference` and
`snapshot: {text, sha256}`. `content` contains `text`, `sha256`, `start`, and
`end` (zero-based, end-exclusive Unicode character offsets). `review` contains
`reviewer`, `reviewed_at`, `decision`, `scope`, and `subject_sha256`. `transfer`
binds that review by hash and declares `domain` and `compatibility`; these must
match the reviewed claim and actual requested target. Complete synthetic
examples are in `tests/evidence_fixtures.py`.

Precomputed vectors require `embedding_provenance` with `model`, `generated_at`,
`dimension`, `record_sha256`, and `content_sha256`, plus a content-bound source.
The query vector is an object with `query`, `embedding` and provenance binding
`query_sha256`, model, timestamp and dimension. Raw vector arrays are no longer
accepted. Finite numbers, nonzero norms, dimensions, model identity and current
content binding are checked before ranking. Similarity does not review evidence.
`production_ready`/`PASS` on retrieval output means ranking readiness only;
`status_scope` and `scientific_acceptance=false` make that distinction explicit.

The adsorption evidence gate requires the above review and real template
`{path, sha256}` bindings, validates whitelist URLs through the existing
retrieval validator, and retains the source payload in its output. Consumers
reapply the same gate before using cached external plans. Legacy booleans or
unbound READY documents require explicit evidence refresh; no historical source
record is rewritten automatically.

## B5 implementation ownership

The authoritative implementation is `scripts/catalysis_retrieval/`: `records.py`
validates whitelist records and bound embeddings, `ranking.py` ranks candidates,
and `workflow.py` orchestrates input validation and ranking. Existing
`skills/catalysis-data-retrieval/scripts/validate_records.py` and `hybrid_search.py`
retain their CLI and public imports as thin adapters. Normal package imports
replace skill-directory `sys.path` mutation and AdsMind's dynamic skill import.
Use the repository's installed/editable environment for these standalone commands;
whitelist resources remain at the unchanged repository skill path. Wheel resource
packaging is a B7 concern. A ranking PASS cannot accept or promote a scientific
result; failed record validation remains STOP, and lexical-only remains diagnostic.
