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

# Convergence Workflow

## Purpose

Select transferable VASP numerical and slab settings for a precisely defined material model and accuracy target.

## Inputs

- structure family and magnetic state
- candidate ENCUT, k-mesh, smearing, vacuum, and slab-thickness ranges
- comparison quantity, normalization, and tolerance
- reviewed retrieval evidence when an external model or parameter range is adopted

## Gates

- Keep geometry, pseudopotentials, functional, magnetism, and comparison convention consistent.
- Lock `GGA=PE`, the approved PAW-PBE POTCAR family, and `ENCUT=400 eV` across each adsorption-energy dataset. Use `ISPIN=2` for Fe-containing magnetic systems and `ISPIN=1` without `MAGMOM` for closed-shell gas-phase CO. Metals and oxides may have separate convergence-backed `EDIFF`/`EDIFFG`, smearing, magnetic, and DFT+U branches, but one reported energy difference cannot mix branches.
- Within one surface family, converge and then lock the lateral cell, slab thickness, vacuum, fixed-layer rule, dipole policy, and slab k-mesh for every clean, adsorbed, endpoint, and TS state.
- Use a suitable energy quantity for smearing comparisons and normalized surface energies for slab thickness.
- Do not transfer Fe(110) settings to chi-Fe5C2 or Fe3O4 without system-specific evidence.

## Outputs and Handoff

- convergence tables, selected routine settings, high-accuracy settings, limitations, and source paths
- registry records for every sweep job, input, output, and extracted result
- downstream handoff to adsorption, NEB, and static-energy workflows

## Corrected True Fe(110) Result

- Jobs `9554557-9554562` completed normally for bulk and 4-8-layer clean slabs.
- All slabs retain flat Fe(110) layers, negligible lateral motion, and zero fixed-layer drift.
- Clean-surface geometry supports five layers as the active production model and seven layers as a validation reference.
- Five layers are locked for the production dataset by explicit user decision. Any later matched five- and seven-layer CO/C+O comparison is validation-only; it must be stored as a separate compatibility branch and cannot switch production automatically.
- Seven versus eight layers differs by `0.0008 A` in top interlayer spacing and `0.0106 J/m2` in surface excess.
- Clean-surface convergence does not replace matched adsorbate/reaction observables for quantifying the production model's remaining thickness uncertainty.
- Curated results: `results/fe110_true_facet_thickness_20260628.csv`.

## Reusable Utilities

- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`: alpha-Fe smearing campaign.
- `scripts/convergence/setup_true_fe110_thickness_retest.py`: corrected true bcc Fe(110) four-to-eight-layer relaxation/static campaign and surface-excess summary.

These scripts have distinct scopes. Submission flags require task-level review and registry setup before use.

### Alpha-Fe canonical execution handoff

`setup_alpha_fe_bulk_smearing --setup` now creates the canonical `script.lsf`
with the original LSF bytes and a `POTCAR.spec` containing only the source
POTCAR SHA-256 identity. The scientific inputs and summary convention are unchanged.
An existing `run.lsf` causes setup to stop: review its byte-preserving handoff to
`script.lsf` explicitly before regenerating inputs. The tool never maintains two
independently mutable LSF templates or rewrites existing legacy submission markers.

`--submit` without a manifest fails with
`CANONICAL_EXECUTION_AUTHORIZATION_REQUIRED`. For each selected case, prepare the
canonical `submission_preflight.json`, current source-bound scientific evidence,
and a gate decision using the existing B1 authorization procedure described in
[`SUBMISSION_RECOVERY.md`](../../SUBMISSION_RECOVERY.md) and
[`transition_state_search`](../transition_state_search/README.md).
POTCAR source/hash, target, bundle, action and evidence must match that reviewed
authorization. Neither `--check` nor the routing manifest grants authorization.

Pass `--submit --submission-manifest /absolute/path/reviewed-handoffs.json`:

```json
{
  "ISMEAR_m5_TETRA": {
    "workdir": "/absolute/campaign/ISMEAR_m5_TETRA",
    "decision_path": "/absolute/review/gate-decision.json",
    "host": "sunboquan-codex",
    "remote_dir": "~/sbq/reviewed-campaign/ISMEAR_m5_TETRA",
    "potcar_source": "~/sbq/reviewed-potentials/POTCAR",
    "potcar_sha256": "REPLACE_WITH_REVIEWED_SHA256",
    "action": "SUBMIT_DIAGNOSTIC_VASP"
  }
}
```

Replace illustrative paths with reviewed values; workdir must be the selected
case under the configured campaign `WORKDIR`. The manifest selects one or more
known labels. Each delegates to `scripts.neb_agent.submission.submit`; alternatively
use that owner's CLI (`python -m scripts.neb_agent.submission --help`). Cases are
independent submissions, not an atomic multi-job transaction: stop on the first
failure and inspect canonical receipts before preparing any further handoff.

Canonical immutable reservations and `submission_record.json` replace the old
`submitted.jobid` success marker. Any old marker requires reviewed reconciliation;
an unresolved canonical reservation is never automatically retried. The campaign
adapter creates no authorization, reservation, scheduler command or private receipt.

Old wrong-facet generator scripts have been removed from the repository.

## Done Criteria

Selected settings, tolerance, transfer scope, source paths, limitations, and registry records exist for every accepted campaign.
