# Phase 2B Behavior Baseline

Captured: 2026-07-27, before Phase 2B source changes

## Frozen source and interface

| File | Lines | SHA-256 |
| --- | ---: | --- |
| `scripts/neb_agent/path_quality_control.py` | 330 | `12b277f51a1a9add4c82422ff7024c031dde1ceeca2b6330d80cb06d99d4b523` |
| `scripts/neb_agent/path_quality_cli.py` | 96 | `0063f77d759b97d116df2c379376080d767231b9fad1517874cfc35223b09de8` |
| `scripts/neb_agent/pilot_validation.py` | 192 | `db0d00bc286138bb8a772fb292011845b1b3219f617524b25ca15f963de2e90d` |
| `scripts/ts_strategy_engine/workflow.py` | 316 | `bff5a7e412f0f58b5d2638f8a53ff397c93e3b9dee553093812f2bea7a9bdade` |

The authoritative evaluator signature is:

`evaluate_quality(evidence: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]`

Its stable top-level field order is:

1. `schema_version`
2. `PATH_QUALITY_STATUS`
3. `REASON_CODES`
4. `CRITICAL_IMAGES`
5. `EVIDENCE`
6. `CHEMICAL_INTERPRETATION`
7. `FILES_SAVED`
8. `NEXT_REQUIRED_EVIDENCE_CHECK`
9. `execution_authority`
10. `COMPUTE_COST_ASSESSMENT`

The standalone and unified CLI `--help` commands both returned exit code 0.
Missing required CLI arguments and an invalid reaction pair returned 2. A
missing threshold file returned 1 with `FileNotFoundError`.

## Semantic cases

All rows below were evaluated directly with the existing in-memory fixtures.
Thresholds were the unchanged test/config values: monitoring cycles `5`,
independent-family minimum `2`, image-jump warning `1.0 A`, abnormal-gap ratio
`2.0`, gap non-decrease fraction `0.98`, basin span `0.05 A`, sharp energy
corner `0.20 eV`, hard NELM exhaustion count `3`, pre-CI force `0.10 eV/A`,
and recent coordinate drift `0.05 A`.

| Case | Status | Ordered reason codes | Critical images | Key result |
| --- | --- | --- | --- | --- |
| Qualified smooth path | `ORDINARY_NEB_PROGRESS_EVIDENCE` | `C_gap_persistent_or_increasing` | `01,02` | Important interval sampled; no discontinuity family |
| CI-ready path | `CI_NEB_READINESS_EVIDENCE` | `C_gap_persistent_or_increasing` | `01,02` | All internal projected forces at `0.08 eV/A`; stable highest image |
| Large/unsampled C–O gap with multiple problems | `UNDERRESOLVED_REACTION_COORDINATE` | `B_large_reaction_coordinate_gap`, `C_gap_persistent_or_increasing`, `E_important_interval_unsampled`, `G_neighbouring_images_in_separate_basins`, `H_force_drop_from_product_basin_motion`, `ELECTRONIC_CONVERGENCE_FAILURE` | `03,04` | Families remain ordered as discontinuity, persistence, basin separation |
| Endpoint and mixed-step monitor flags | `ORDINARY_NEB_PROGRESS_EVIDENCE` | `C_gap_persistent_or_increasing`, `UNVERIFIED_INVALID_ENDPOINT_FLAG`, `UNVERIFIED_MIXED_ELEMENTARY_STEPS_FLAG` | `01,02` | Unverified flags remain warnings and cannot create a hard stop |
| One discontinuity family only | `ORDINARY_NEB_PROGRESS_EVIDENCE` | Existing condition reasons only; no electronic failure | Fixture-specific | Independent families exactly `["discontinuity"]` |
| Missing evaluator evidence | exception | `KeyError: 'image_names'` | — | No partial report |
| Invalid evaluator configuration | exception | `KeyError: 'persistence'` | — | No partial report |

The existing five evaluator tests also freeze abnormal adjacent displacement,
reaction-coordinate discontinuity, condition-family deduplication, endpoint
monitor warnings, and optional stable-highest readiness policy. No assertion in
those tests may be removed or weakened.

## Ownership boundaries captured before refactor

- Atomic collision/too-close checks are owned by the upstream geometry
  diagnosis, not by `evaluate_quality`; path-quality has no collision reason
  code to reorder.
- Magnetic continuity is owned by `pilot_validation.py` through
  `evaluate_magnetic_continuity`. The existing warning fixture keeps the pilot
  result accepted while reporting magnetic `WARNING`; path-quality does not
  reinterpret it.
- With no analysis output, workflow path quality returns `{}`.
- With no primary reaction coordinate, workflow returns exactly
  `{"PATH_QUALITY_STATUS": "INVALID_ENDPOINTS", "REASON_CODES":
  ["PRIMARY_REACTION_COORDINATE_MISSING"], "CRITICAL_IMAGES": []}`.
- `pilot_validation.py` currently contains no path-quality calculation or
  path-quality field in its Schema-v2 payload. Phase 2B must not silently add
  path quality to `passed` or change that payload Schema.

## Pre-refactor duplication and complexity

| Measure | Before |
| --- | ---: |
| Path-quality config merge implementations | 2 |
| `collect_evidence()` orchestration sites | 2 |
| `evaluate_quality()` orchestration sites | 2 |
| Result-document formatting implementations | 2 |
| `neb_path_quality.json` write sites | 2 |
| Path-quality scientific decisions in CLI | 0 |
| Path-quality scientific decisions in workflow | 0 |
| Path-quality calculations in pilot | 0 |
| Relevant production files | 4 |
| Relevant production lines | 934 |
| Largest function | `evaluate_quality`, 180 lines |

The scientific evaluator was already unique. Phase 2B therefore freezes it
and removes only duplicate application orchestration around it.
