# Final Backlog

Date: 2026-07-27

## P0

`OPEN_P0 = 0`.

## P1

| Files | Problem | Risk | Why not handled now | Start condition | Required tests |
|---|---|---|---|---|---|
| repository-wide | final baseline is local evidence, not a commit/off-machine backup | loss of review provenance; indiscriminate staging could include calculations/results | commit/push were expressly unauthorized | explicit user authorization after staged-scope review | manifest verification, staged diff, secret/large-file scan |
| GPU wrapper/environment files | AQCat25/FairChem environment is not fully locked in base metadata | inference/training reproducibility drift | no validated GPU environment was available and pinning blindly can break deployment | before claiming reproducible GPU execution | MZ73 smoke, checkpoint load, held-out adsorption/TS regression |

## P2

| Files | Problem | Risk | Why not handled now | Start condition | Required tests |
|---|---|---|---|---|---|
| VFA, path-quality, endpoint validator, active-learning domain | functions of 138–208 lines | maintenance and review burden; refactor can change scientific ordering | current complexity policy and behavior tests pass | separately approved characterization/refactor task | exhaustive golden and reason/order tests |
| `scripts/adsmind_lite/audit_remote_fe110_batch.py` | local literal 15/60-second SSH timeouts | configuration inconsistency only | no observed defect and value is low | when the read-only audit gains shared timeout config | timeout/connection/command failure tests |
| VASP/campaign/adsorption builders | direct `write_text` into generated destinations | ambiguous overwrite recovery if callers reuse a destination | paths are fresh-directory builders; changing writes can alter workflow behavior | reproduce destination-reuse need | destination-exists and partial-write tests |
| gate, AdsMind core, active-learning wrapper | intentional compatibility facades look duplicative | premature removal breaks imports/docs | compatibility is an explicit current requirement | future major-version migration | repository/external caller inventory and old-path tests |

## BLOCKED

| Files | Problem | Risk | Why not handled now | Start condition | Required tests |
|---|---|---|---|---|---|
No implementation blocker remains for the endpoint extension. Real-database
execution remains a separate authorization gate; direct SQL execution and
non-empty rollback are prohibited.

## Closed on 2026-07-27

- Extreme endpoint contacts are rejected using the configured
  element-aware collision threshold.
- Actual surface-normal partial desorption requires review.
- Empty `reaction_id` is rejected at request and record boundaries.
- Endpoint migration shape validation, transactional failure rollback,
  repeat validation, and empty-only rollback guards are implemented and tested
  on temporary SQLite databases.

## OPTIONAL

| Files | Problem/opportunity | Risk | Why not handled now | Start condition | Required tests |
|---|---|---|---|---|---|
| `scripts/`, `modules/` | optional stricter type checker | new policy/dependency and annotation churn | not required for verified behavior | separately approve tool and scope | baseline current errors, CI compatibility |
| path/endpoint evidence collectors | optional performance profiling | premature tuning can alter scientific code | no measured bottleneck | representative local timing shows need | deterministic benchmarks plus behavior regression |

## Not recommended

- Do not execute or “test” the blocked endpoint migration against the real
  registry.
- Do not merge scheduler, convergence, geometry, and scientific statuses into
  one boolean.
- Do not split stable geometry/scientific evaluators merely to reduce line
  counts.
- Do not remove legacy import facades while they are contract-tested callers.
- Do not include calculations, outputs, SQLite files, runtime state, secrets,
  or scheduler evidence in a source release baseline or refactor commit.
