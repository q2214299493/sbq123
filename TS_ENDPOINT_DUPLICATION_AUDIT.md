# TS Endpoint Duplication Audit

Date: 2026-07-27
Scope: Phase 3B implementation routing; production behavior unchanged

This document closes a Phase 3A documentation omission. It classifies only
duplication relevant to the exact Phase 3B plan. It does not authorize
scientific, configuration, database, migration, routing, or API changes.

## Classification

| Area | Classification | Evidence | Phase 3B action |
|---|---|---|---|
| Initial ASE structure loading inside validator | `CONFIRMED_DUPLICATE` | `_observed_bond_changes()` loads initial/endpoint ASE structures; `_center_of_mass_displacement()` loads the same initial structure again solely for masses | Collect ASE initial/endpoint once per successful validation and reuse raw evidence |
| POSCAR/ASE structure representations | `INTENTIONAL_LAYERING` | custom POSCAR is authoritative for compatibility/minimum-image displacement; ASE is used by existing connectivity/mass helpers | Preserve both representations and their existing algorithms |
| Threshold loading for each candidate | `PARTIAL_OVERLAP` | generator calls validator per candidate, so the same config may be read repeatedly | Do not change: caching would alter the public validator/generator boundary outside the approved plan |
| Initial POSCAR parsing for each candidate | `PARTIAL_OVERLAP` | every candidate validation reloads the common initial structure | Do not change: cross-candidate caching belongs to a later, separately approved service design |
| Generator calling validator | `INTENTIONAL_LAYERING` under the frozen API | `GeneratedTSEndpoint` contains `validation` and assessments; manager consumes that public result | Preserve in Phase 3B because the implementation plan excludes manager changes and freezes the old public facade |
| Manager generator/validator logic | `INTENTIONAL_LAYERING` | manager delegates once and does not calculate mapping, bonds, sites, statuses, scores, or reasons | No change |
| Manager record construction vs database serialization | `INTENTIONAL_LAYERING` | manager maps a scientifically selected result into `TSEndpointRecord`; adapter serializes and persists it | No change |
| Validation status values in Enum/adapter/SQL | `INTENTIONAL_LAYERING` | Python result, input-integrity guard, and database CHECK require the same allowed values | No change; migration/Schema is blocked |
| Purpose config loading vs validator config loading | `INTENTIONAL_LAYERING` | manager consumes `enabled`; validator consumes `endpoint_validation` from the same formal file | No change |
| Scientific status/reason construction | no duplicate | only `TSEndpointValidator` constructs endpoint scientific status, score, errors, warnings, and reasons | Keep validator authoritative |
| Database scientific validation | no duplicate | adapter imports no generator/validator and calls no `validate` method | Keep adapter passive |
| Collision/desorption/empty reaction identity | `NEEDS_REVIEW` scientific gaps, not duplication | Phase 3A frozen behavior demonstrates missing/limited checks | Do not change in responsibility-only Phase 3B |

## Authorized duplicate removal

Only one implementation change is authorized by this audit:

1. add a small internal endpoint-evidence collector;
2. load each ASE structure once after compatibility preflight succeeds;
3. reuse the loaded initial ASE masses for the existing COM formula;
4. return raw displacement/connectivity evidence only;
5. keep all `BondChange`, status, score, warning, error, reason, and priority
   decisions in `modules.ts_endpoint_validator`.

## Explicit non-actions

- no manager/service rewrite;
- no generator public-flow rewrite;
- no database or migration change;
- no configuration split or cache;
- no scientific-gap repair;
- no public import removal or rename.
