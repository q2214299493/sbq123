# Final Behavior Compatibility Report

Date: 2026-07-27

## Conclusion

The final tree preserves the independently accepted Phase 2B path-quality
behavior. Endpoint behavior preserves Phase 3B except for the explicitly
authorized close-contact, desorption, and empty-identity corrections recorded
in `TS_ENDPOINT_ISSUE_CLOSURE_REPORT.md`.

## Regression layers

| Layer | Command/scope | Result | Protected behavior |
|---|---|---|---|
| Gate/external safety | 6 focused test files | 48 passed | legacy gate imports, timeout distinction, submission idempotency/recovery, alpha-Fe guards, atomic JSON |
| Path quality | 4 focused test files | 38 passed | sole evaluator, shared entry paths, reason/status ordering, pilot/workflow behavior |
| TS endpoint | 2 focused test files | 45 passed | signatures, deterministic evidence, single read, status/reasons, routing, guarded temporary migration |
| Full repository | `python -m pytest -q -ra` | 274 passed | cross-module behavior |
| Skip/xfail | pytest report | 0 | no hidden non-executed acceptance cases |

## Scientific authority

Only `scripts.neb_agent.path_quality_control.evaluate_quality` builds the NEB
path-quality scientific conclusion. Only
`modules.ts_endpoint_validator.TSEndpointValidator` aggregates endpoint
scientific status and reason codes.

`modules.ts_endpoint_evidence` returns raw displacement, connectivity,
pair-distance, and surface-relative height evidence. It does not assign status,
apply scientific thresholds, or emit reason codes. The manager and database
adapter do not reconstruct scientific conclusions.

## Current endpoint behavior

| Case | Current result |
|---|---|
| Normal valid endpoint | existing result preserved |
| Broken/formed target bond | existing result preserved |
| Atom-count/map mismatch | existing rejection preserved |
| Non-target bond/site change | existing review ordering preserved |
| 0.2 Å C–O contact | `REJECTED`; `UNPHYSICAL_ATOM_CONTACT` |
| Surface-normal adsorbate rise above 2.0 Å | `REVIEW_REQUIRED`; `ADSORBATE_DESORPTION_WARNING` |
| Opposite in-plane motion | existing displacement warning preserved; not mislabeled as desorption |
| Empty/whitespace reaction ID | `ValueError` before generation or persistence |
| Migration post-validation failure | complete transaction rollback |
| Non-empty endpoint rollback | refused |

The endpoint threshold version is `ts_endpoint_thresholds_v2`. Public
validation-result fields, status names, reason sorting, and status priority are
preserved. New reason codes occur only for the newly governed contact and
desorption conditions.

## Preserved boundaries

- execution-gate decision priority and `ALLOWED_ACTIONS` enforcement;
- timeout, connection/command failure, and unknown scheduler state remain
  non-success;
- failed or ambiguous submission cannot create success or automatic retry;
- atomic JSON failure preserves the old target and cleans temporary files;
- path-quality status, reasons, metrics, thresholds, Schema, CLI, workflow, and
  pilot semantics;
- endpoint purpose priority, database record fields, and exception
  propagation;
- validator failure does not create a successful endpoint record;
- adapter construction and normal CRUD never run a migration;
- same input remains deterministic.

## Side-effect verification

Acceptance used mocks, temporary directories, and temporary SQLite databases.
The revised endpoint forward migration and empty rollback were exercised only
against pytest temporary files. No real migration, SSH, LSF, `bsub`, `bkill`,
VASP, or NEB operation was executed.

The real registry SHA-256 remained:

`4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.
