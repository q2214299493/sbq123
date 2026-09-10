---
document_class: CURRENT_REFERENCE
as_of: '2026-09-10T08:10:49.081307+00:00'
as_of_scope: thickness payload contract update, not a live scientific observation
source_scope: current thickness repair usage contract; historical observations retain original dates
source_version: fae4339f7f91b52c13f4b993c9791e7110f13249
source_version_role: thickness repair base commit
source_branch: codex/ac-closeout-thickness-workflow
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

### Thickness payload contract

Generate new inputs with
`python -m scripts.convergence.setup_true_fe110_thickness_retest --setup --output /absolute/new-campaign`.
Input generation still needs the `neb` optional dependency (ASE). Scientific
settings, four-to-eight-layer structures, bulk reference and the TOTEN surface
excess convention are unchanged. Input-only repeated setup is supported. Setup
checks every destination before writing and refuses existing calculation outputs,
payload attempts, scheduler attempt/receipt markers and symlinks. It does not
overwrite part of a previously run campaign before reporting an error.

New `run_chain.lsf` and standalone bulk `run.lsf` declare **Bash**. They retain
32 cores, NP_PER_NODE=32, OMP_NUM_THREADS=1, the default initialization script
`/home_gkx/env/intel/intel2016.sh` and VASP
`$HOME/soft/vasp.5.4.1/bin/vasp_std`. Before any calculation they require a
nonempty valid `LSB_HOSTS` list, writable machine file, regular contained stage
inputs (including a provisioned POTCAR), executable MPI/VASP and a Python with
the installed core package. No VASP/VTST or scheduler is launched by setup.

Explicit dependency selectors are `THICKNESS_ENV_SCRIPT`, `THICKNESS_VASP`,
`THICKNESS_MPI` (default `mpirun`) and `THICKNESS_PYTHON` (default `python3`).
They select a file/executable, never an evaluated shell fragment. A missing
explicit selection fails rather than falling back to another executable. The
environment script must return success; no `errexit`/`nounset` assumption is
imposed on vendor initialization. The stage module
`python -m scripts.convergence.thickness_stage --help` requires only the normal
core installation (including NumPy), not ASE, pymatgen, Sella or ML packages.
Install that package in the selected runtime before deployment. This change
does not establish that the HPC runtime has been deployed or verified.

Each payload exclusively creates `.thickness-attempt/` with `mkdir`. This is
local job-payload exclusion, not scheduler authorization/reservation. A second
instance or any repeat invocation refuses that directory, including after a
successful run. It never removes B1 reservations or retries a failed job.
The final `result` records stage, exit code and `scientific_acceptance=false`;
an attempt without a complete record requires manual reconciliation. Process
failures preserve their original code; dependency, input, output, handoff,
machine-file and receipt errors are nonzero. INT/TERM/HUP terminate the chain;
a hard kill may leave only the blocking attempt directory.

Both relaxation and static directories must be free of earlier calculation
outputs before the first MPI call. Each stage is checked again before launch.
An input `static/POSCAR` from setup is allowed. The payload never truncates old
outputs or requires new output bytes to differ from input. Relaxation must
produce current normally completed, explicitly electronically converged and
ionically converged OUTCAR evidence without a recognized fatal error. Static
uses current normal/electronic completion, with no ionic-relaxation requirement.
These checks use the existing OUTCAR owner; no NELM default is guessed or added
to INCAR. Invalid/missing CONTCAR, atom/cell/Selective Dynamics mismatch or an
atomic handoff failure stops before static. A legitimate unchanged CONTCAR is
accepted and copied byte-for-byte via a same-directory temporary file.

`--summary` is diagnostic. Shared `extract_toten` supplies the last finite
complete numeric token; malformed/nonfinite records raise an error rather than
falling back to an earlier energy. Missing/incomplete bulk output refuses a
summary; missing slab energy remains null. Slab output validity is explicit in
`output_status`; incomplete output has null surface excess, even if a diagnostic
TOTEN was extracted. `scientific_acceptance` is always false. No registry or
scientific promotion is performed, and the bulk normalization, double-surface
factor, area and eV/A²-to-J/m² conversion are unchanged.

Do not rerun old campaign directories or historical scripts under
`inputs/fe110_true_facet_thickness_20260627/`. Those retained historical inputs
are not updated in place by this repair. Use a new directory and regenerated
payload, or a separately reviewed manual recovery. Submission still belongs
to the canonical execution authority; this payload introduces no submission API.

## Done Criteria

Selected settings, tolerance, transfer scope, source paths, limitations, and registry records exist for every accepted campaign.
