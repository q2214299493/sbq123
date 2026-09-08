# TS Endpoint Issue Closure Report

Date: 2026-07-27

## Result

The three previously frozen endpoint gaps are closed with bounded behavior
changes. The migration implementation is revised and verified on temporary
SQLite databases, but real-database execution still requires separate explicit
authorization.

## Scientific behavior changes

### Extreme atom contact

- Previous behavior: a sampled 0.2 Å C–O contact was `VALID`.
- Current behavior: `REJECTED` with `UNPHYSICAL_ATOM_CONTACT`.
- Rule: an endpoint pair is rejected when its MIC distance is below
  `min(absolute_minimum_distance_A, collision_radius_scale * summed covalent
  radii)`.
- Configured values: `1.0 Å` and `0.55`, aligned with the existing project
  geometry-diagnosis defaults.
- The connectivity cutoff remains separate and unchanged.

### Partial desorption

- Previous behavior: there was no endpoint-specific surface-height check.
- Current behavior: if any adsorbate atom rises by more than `2.0 Å` relative
  to the top of the selected surface atoms, the result is `REVIEW_REQUIRED`
  with `ADSORBATE_DESORPTION_WARNING`.
- The historical synthetic “opposite motion” fixture moves atoms in the surface
  plane and is not geometrically a desorption case. It correctly remains
  `VALID_WITH_WARNING` with `REACTIVE_ATOM_DISPLACEMENT_WARNING`; the COM
  formula was not changed.
- A new vertical partial-desorption fixture protects the intended rule.

### Empty reaction identity

- `TSEndpointGenerationRequest` rejects missing or whitespace-only
  `reaction_id`.
- `TSEndpointRecord` repeats the check at the persistence boundary.
- Public field names and method signatures are unchanged.

The endpoint threshold version is now `ts_endpoint_thresholds_v2`. No existing
status name was removed and the public validation-result field list is
unchanged. Two new reason codes are introduced only for the newly handled
conditions.

## Evidence collector boundary

`modules/ts_endpoint_evidence.py` remains non-authoritative. It now returns:

- endpoint pair distances; and
- per-adsorbate height changes relative to the surface top.

It does not assign status, emit reason codes, apply thresholds, write files, or
persist records. `modules/ts_endpoint_validator.py` remains the only endpoint
scientific decision authority.

## Migration revision

The optional endpoint extension remains separately versioned by
`ts_endpoint_schema_version=1`; it is deliberately not added to the registry
core version because endpoint persistence is optional and existing version-5
registries must remain usable without this extension.

The validated API now:

- rejects a same-name table unless columns, types, nullability, primary key,
  foreign keys, indexes, uniqueness, check constraints, and extension version
  all match;
- treats a compatible existing extension as a verified repeat operation;
- explicitly starts a transaction before DDL;
- rolls back the full forward change if post-creation validation fails;
- prohibits `rollback=True` on the legacy API;
- permits rollback only through a separate exact-confirmation API and only
  while the endpoint table is empty;
- refuses all non-empty rollback.

The SQL files remain review-only and must not be executed directly. Real
database execution remains prohibited until separately authorized.

## Lightweight refactor decision

The validator’s status-priority block was mechanically extracted into one
private helper to keep Ruff complexity within the existing limit. The status
order is unchanged:

`REJECTED` → `REVIEW_REQUIRED` → `VALID_WITH_WARNING` → `VALID`.

No additional long scientific function was split because the expected
maintenance benefit did not justify increasing behavioral risk.

## Verification

Endpoint-specific and complete-repository results are recorded after execution
in `FINAL_VERIFICATION_REPORT.md`. The real registry SHA-256 must remain:

`4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.
