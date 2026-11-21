# Stage B.1.3 · Independent stoichiometric source engine

The V2 validator and two MKM consumers now use one implementation to project signed reaction progress onto molecular production and vacant-site rates. The 400 K synthetic Ni/Cu archive reproduced on both Windows checkouts. Scientific execution, historical data, rate denominators and version selection retain their existing contracts. This checkpoint covers offline source mathematics.

## Ownership and interfaces

| Responsibility | Before | After |
| --- | --- | --- |
| Species and vacancy source projection | V2 built lists of signed products, while MKM analysis and single-point reconstruction separately accumulated species rates. | The kinetic-data module builds two labeled sparse matrices and projects qualified progress. The original V2 import is a direct alias. |
| Native and reported progress | Single-point reconstruction used native coefficients, pressures, coverages and vacancies. Analysis checked published forward, reverse and net observations. | Each consumer still qualifies its own observations. The common owner projects reconstructed nets in the reader and reported nets in analysis. Analysis keeps per-reaction gas contributions. |
| Units, dimensions and declared basis | B.1.2 owned coefficients, normalization and explicit conversions. | Existing unit and basis authority stays in place. Source projection multiplies by signed stoichiometric counts on the parent denominator. |
| Uncertainty | Kinetic parameter laws expose uncertainty on parameters or log coefficients. The versioned outputs have no net-progress covariance field. | A pure optional Python API accepts labeled full covariance or explicitly independent variances from a caller. The schemas and data paths retain their existing meanings. |
| Qualification and I/O | Schemas, directional evidence, native observations and scientific review reside with their respective owners. | Matrix construction, projection, conservation, residuals and covariance require no files, Registry access or external process. V2 continues to enforce evidence before checking a reported source. |

## Matrix, conservation and missing-value validation

For each labeled reaction column the species rows use product minus reactant counts, and the vacancy rows use released minus consumed counts. Both matrices use the full configured identity. The cross-interface fixture binds one molecule while consuming two sites from one phase, one site of the same type from a second phase, and one interface site. At progress 3 it produces three surface molecules and vacancy rates of −6, −3 and −3. The four occupied sites per molecule enter the inventory checks separately. The network contract defines positive integer multiplicities.

The tests compare element and charge sums, and occupied-plus-vacant changes on every inventory per reaction. Independent mutations of O count, charge, and site footprint produce labeled residuals while unrelated balances remain zero. The reported-source check uses reported minus projected with the original 1e-12 relative tolerance and zero absolute floor. Missing catalog fields identify the species and required evidence. Source arithmetic itself can proceed without a conservation certificate.

A known zero remains zero. Unknown net progress only affects nonzero coefficients in its column. A spectator can have known zero production even with missing flux. Excluded directions and unavailable directions retain distinct meanings. Existing tests also cover independent net evidence and its physical consistency with each known direction. Signed progress, 1:1, 1:2, 2:1, serial and parallel reactions, generator input, row order and ID permutations have hand-calculated checks.

## Uncertainty validation

The optional API evaluates the joint covariance of species and vacancy sources. Its labeled axes bind the numerators, and the returned parent normalization supplies amount scale, denominator and time. A source variance thus has squared source units and a cross-covariance has the product of the two axis units. For the hand case B = 2r₁ − r₂, variances 4 and 9 and covariance 1 give Var(B) = 21. Explicitly independent variances give 25. A singular perfectly correlated case gives zero for this combination. An unavailable covariance remains null. With documented independence and one missing variance, only entries depending on it become null. Tests reject non-finite, asymmetric, indefinite and mislabeled covariance, including a three-reaction matrix that passes all pairwise correlation bounds.

## Archived 400 K Ni/Cu benchmark

| Recomputed from the four signed progress observations | Value |
| --- | ---: |
| Overall turnover per reference site pair per second | 81.5127701616477 |
| HNO production per reference site pair per second | 163.0255403232954 |
| Turnover per individual modeled site per second, averaged across the pair | 40.75638508082385 |
| Ni-top vacant-site source per reference pair per second | 0 |
| Cu-bridge vacant-site source per reference pair per second | 0 |

Each of the four reactions conserves H, N, O, charge, and both individual site inventories. H₂, NO and HNO source residuals against archived gas observations are zero. The site mean uses the archived one-Ni-top plus one-Cu-bridge definition. The source rates retain their native pair denominator. There is no archived net-progress covariance for this replay. The receipt binds the original network, result and analysis by SHA-256. Those three archives and the four checked V1/V2 schema files were byte-identical before and after in each tree. [Replay receipt](ni_cu_replay.json)

## Windows regression and release

The independent publication checkout started at `c80e127bd4cf45749d1486f6308454452c04b813` on the task branch. The development checkout retained its local `refactor/v2-architecture-repair` history at `233d5a6c589560094a0e942b6d48708b1fd5a847`. Changes were applied to each tree in place.

| Focused scope | Development passed | Publication passed |
| --- | ---: | ---: |
| Pre-change baseline, V1 + V2 + dimensional checks | 250 | 250 |
| New mathematical owner and archive replay | 40 | 40 |
| V1 multiphase, V2 output, B.1.2 dimensions and versions | 250 | 250 |
| Kinetic parameters, MKM analysis, single-point workflow | 95 | 95 |
| Native model assembly, advanced offline checks and closed-cycle regressions | 68 | 68 |
| DRC archive reports, four raw result hash replays and cross-reaction stability | 7 | 7 |
| B7 release and maintained import graph | 18 | 18 |
| **Post-change focused total** | **478 in 25.16 s** | **478 in 23.72 s** |

Both focused runs had zero failures. Each deselected eight native Zacros cases and one live CATKINAS case. The full repository suite was outside this checkpoint. Both checkouts passed py_compile and Ruff for all six task Python files. In independent temporary builds, each installed wheel exposed the same original V2 alias and produced the expected signed 1:2 projection outside the checkout. Existing V1/V2 CLI and cross-submission regressions passed. Verification used offline fixtures, temporary test databases, and archived outputs. No production SQLite write or native engine run was performed.

## Exact changed files

- `scripts/kinetic_data/__init__.py`
- `scripts/kinetic_data/stoichiometric_sources.py`
- `scripts/rate_output_v2.py`
- `scripts/baseline_mkm/kinetic_analysis.py`
- `scripts/baseline_mkm/single_point_result.py`
- `tests/test_stoichiometric_sources.py`
- `modules/kinetic_data/multiphase_contracts.md`
- `modules/kinetic_data/stoichiometric_sources.md`
- `reports/multiphase/stage_b1_3/ni_cu_replay.json`
- `reports/multiphase/stage_b1_3/completion.md`
- `reports/multiphase/stage_b1_3/handoff.md`
- `modules/state_handoff/events/history-stage-b1-3-stoichiometric-sources-20261121.json`

The checkpoint records implementation and replay evidence. Project eligibility continues to depend on the owning scientific review. [State Handoff and pending decisions](handoff.md)
