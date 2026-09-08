# Phase 2B Behavior Compatibility

Date: 2026-07-27
Result: **PASS**

## Scientific behavior proof

The SHA-256 of the sole evaluator file remained
`12b277f51a1a9add4c82422ff7024c031dde1ceeca2b6330d80cb06d99d4b523`
before and after Phase 2B. Both threshold files also remained byte-identical.

For the same normalized evidence and merged configuration, direct evaluator,
shared application service, standalone CLI, unified workflow, and pilot
path-quality adapter return identical evaluator fields, list ordering, result
metadata, and source manifest.

| Sample | Before status | After status | Ordered reason codes | Key metric/threshold | Fields | Match |
| --- | --- | --- | --- | --- | --- | --- |
| Qualified smooth path | `ORDINARY_NEB_PROGRESS_EVIDENCE` | same | `C_gap_persistent_or_increasing` | Interval sampled; no discontinuity family; 5-cycle threshold | Exact Schema-v2 evaluator fields | Exact |
| CI-ready path | `CI_NEB_READINESS_EVIDENCE` | same | `C_gap_persistent_or_increasing` | Internal projected forces `0.08 eV/A` vs `0.10 eV/A`; stable highest image | Exact | Exact |
| Single endpoint monitor warning | `ORDINARY_NEB_PROGRESS_EVIDENCE` | same | `C_gap_persistent_or_increasing`, `UNVERIFIED_INVALID_ENDPOINT_FLAG` | Unverified flag cannot create a hard stop | Exact | Exact |
| Electronic failure | `ELECTRONIC_FAILURE` | same | `C_gap_persistent_or_increasing`, `ELECTRONIC_CONVERGENCE_FAILURE` | 5 trailing iterations at `NELM=200`; hard minimum 3 | Exact | Exact |
| Large adjacent displacement | `UNDERRESOLVED_REACTION_COORDINATE` | same | `A_abnormal_adjacent_displacement`, `C_gap_persistent_or_increasing` | Critical displacement `1.2 A` vs warning `1.0 A`; two independent families | Exact | Exact |
| Discontinuous/unsampled target coordinate with multiple problems | `UNDERRESOLVED_REACTION_COORDINATE` | same | `B_large_reaction_coordinate_gap`, `C_gap_persistent_or_increasing`, `E_important_interval_unsampled`, `G_neighbouring_images_in_separate_basins`, `H_force_drop_from_product_basin_motion`, `ELECTRONIC_CONVERGENCE_FAILURE` | Critical images `03,04`; important interval `1.5–2.1 A`; family order unchanged | Exact | Exact |
| One discontinuity family only | `ORDINARY_NEB_PROGRESS_EVIDENCE` | same | Existing condition reasons only | Independent families exactly `["discontinuity"]`, below minimum 2 | Exact | Exact |
| Mixed-step plus endpoint flags | `ORDINARY_NEB_PROGRESS_EVIDENCE` | same | Existing condition reason, endpoint warning, mixed-step warning | Warning order unchanged | Exact | Exact |

A real temporary POSCAR/INCAR fixture additionally exercised file collection.
All four application consumers produced identical complete documents; no
scientific fields were normalized away.

## Separate owning checks

| Case | Before | After | Compatibility |
| --- | --- | --- | --- |
| Atomic collision/too close | Owned by upstream geometry diagnosis, not path-quality | Unchanged | No new reason code or reinterpretation |
| Magnetic discontinuity | Pilot soft warning; does not reject pilot | Unchanged existing pilot tests | Pilot meaning and Schema unchanged |
| Workflow has no analysis output | `{}` | `{}` | Exact |
| Primary reaction coordinate missing | `INVALID_ENDPOINTS` with `PRIMARY_REACTION_COORDINATE_MISSING` | Same three-field dictionary | Exact |

## Error behavior

| Error | Before | After | Semantic impact |
| --- | --- | --- | --- |
| Missing required CLI arguments | exit 2 | exit 2 | None |
| Invalid reaction-pair syntax | exit 2 | exit 2 | None |
| Missing threshold file | exit 1 with traceback | exit 1 with concise `path-quality error` | Message-only improvement; no artifact |
| Invalid threshold structure | later `KeyError` | early descriptive `ValueError` before collection | Clearer boundary failure; no scientific result |
| Missing NEB images | evaluator pipeline error, no result | clear exit 1, no result | No success artifact |
| Expected evaluator exception | uncaught exit 1 | readable exit 1 | No success artifact |
| Output write failure | uncaught exit 1 | readable exit 1 | No status printed; no valid artifact |

The only intentional differences are non-scientific error presentation and
earlier invalid-config rejection. Exit success/failure meaning is preserved.

## Schema and public interface

The path-quality document retains the original evaluator fields followed by:

1. `document_kind = "neb_path_quality_evidence"`
2. `producer = "scripts.neb_agent.path_quality_control"`
3. `source_files`

No original JSON field, status, reason code, list order, CLI argument, module
path, evaluator signature, workflow request field, or pilot public signature
was removed or changed.
