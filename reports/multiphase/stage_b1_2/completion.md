# Stage B.1.2 · Dimensional rate units and native normalization

Publication baseline `cdfbfb278a57a0e76534fc427a7d1c8c22ce305e`. The new V2 revision `2.1.0` checks a rate coefficient against its declared activity orders and checks a reported flux or source against its model’s time, extent and physical denominator. All conversions are explicit. A conversion receipt retains the original value, basis, requested basis and supplied physical evidence. [Model, units, conversion evidence and usage](../../../modules/kinetic_data/rate_dimensions.md)

## Existing owners and revision choice

- `scripts.kinetic_parameters.laws` owns the native pressure-power notation, finite fractional coverage and coefficient evaluation. `export.per_bar` already handles the standard-pressure choice when exporting engine parameters. B.1.2 reuses `pressure_unit`, `fraction`, shared numeric checks, canonical content hashes and the existing V2 reader and stoichiometric projection. The numerical laws and both native adapters are unchanged.
- The existing MKM analysis uses inventory counts and molar-reference density, catalyst area per mass and reactor loading as explicit inputs. Its factors remain in that owner. The new rate API uses the same physical factor definitions with units, a source artifact and hashes of the two physical references. The maintained code did not have an independent general dimensional conversion backend.
- Astropy supplies SI dimensional algebra, unit scales, the CDS standard atmosphere and Avogadro’s constant. The kinetic layer interprets a bounded product/quotient notation and distinguishes event, molecule and vacancy counts. The new optional `rate-units` package extra keeps earlier readers usable without Astropy.
- The original 2.0.0 output and nested source schemas are byte-identical to baseline. The new schema references their definitions. Known 2.0.0 records retain the original rules, while 2.1.0 adds a physically scoped basis and optional separate coefficient records. Missing or unknown versions do not select a reader by inference. V1 has its own entry point. Earlier readers will reject 2.1.0.

## Archived checks

Phase 2.4 reports the synthetic CATKINAS table per mean-field reference site and the Zacros table per matching directed event. The adsorption forward coefficient has unit bar⁻¹ s⁻¹ and the reverse has unit s⁻¹ in both tables. Equality of the printed units does not establish equality of the physical reference or of event fluxes. Phase 2.5’s Zacros manifest counts 18 sites in the tested lattice and binds event checks to that model.

The Phase 2.5.2 CATKINAS evidence and Phase 3.0 result retain their original denominator wording. Using the explicit Phase 3.1 inventory mapping in a dimensional regression, the archived overall progress of 81.5127701616477 per reference pair per second gives 40.75638508082385 per individual site per second across the two model inventories. No density or loading was inferred. [Archive investigation and program inputs](../stage_b1_1_audit/reference_site.md)

## Test matrix

| Area | Independent check |
| --- | --- |
| Pressure, time, amount, area, mass, volume | Scalar scale factors and round trips, including 1 atm = 101.325 kPa, 1 m² = 10000 cm², 1 L = 0.001 m³. |
| Activity, pressure and concentration orders | Zero, first, second, fourth and mixed orders. Compare direct factors including bar⁻² min⁻¹ to Pa⁻² s⁻¹. Reject a coefficient with event/s units and incompatible units even at zero. |
| Five flux/source roles | Check numerator, sign, time direction and non-unit denominators. Test unknown, known zero, excluded direction, negative directional flux, nonfinite numbers and underflow. |
| Physical mappings | Site vs pair, lattice site vs cell, explicit forward/inverse mapping. A density of 2 mmol of reference sites per m² converts 2 molecules per site per second to 4 mmol of species per m² per second. Missing site density, specific area or loading returns the original rate and names the missing factor. |
| Identity and evidence | Validate custom-basis definitions, evidence units, source/hash shape, inventory set and both reference hashes. A different project with the same display label has a different identity. Supplied catalog checks include canonical network digest, inventory membership and CLI raw artifact SHA-256. |
| Revision and packaging | Exercise 1.0.0, 2.0.0 and 2.1.0 in their own entry points, cross-version rejection, strict new fields, optional dependency absence, installed package resources and a conversion outside the repository. |

### Windows regression results

| Suite | Development | Publication |
| --- | ---: | ---: |
| Baseline V1 and V2 before changes | 167 passed | 167 passed |
| New B.1.2 tests | 83 passed | 83 passed |
| Existing V2 and V1 contracts | 91 + 76 passed | 91 + 76 passed |
| Kinetic parameters and MKM analysis | 35 + 29 passed | 35 + 29 passed |
| Native model assembly and offline archive checks | 32 + 23 passed | 32 + 23 passed |
| CATKINAS MAT reader and archived Phase 3.0 result | 10 + 1 passed | 10 + 1 passed |
| B7 packaging and maintained import graph | 17 + 1 passed | 17 + 1 passed |
| **Final focused suite** | **398 passed, 0 failed in 19.26 s** | **398 passed, 0 failed in 18.31 s** |
| Compiled modified Python and ran Ruff | Passed | Passed |
| Installed-wheel subprocess and resource checks | Passed | Passed |

Each run excluded the eight `test_native_zacros_replay` cases that would invoke a native executable. The full repository suite was outside the requested scope. During development four new compound-unit tests used an accidental exact floating comparison. The final assertions use relative tolerance 1e−14 and an absolute floor of zero against independently calculated factors. No changes to the archived numbers or scientific equations were needed.

The two wheels were built offline from each worktree’s packaging sources and installed into separate targets. Each matched the original resource bytes, validated all three declared revisions via their CLI, rejected both V1/V2 cross-submissions and converted a native rate outside either checkout. With the unit backend deliberately unavailable the original V2 reader still passed and the dimensional reader reported a missing capability. The development wheel SHA-256 was `771c83e3ebe7e079b0ae4c6d5267d15941b30fca5ac964f064008f36dd599b7b`; the publication wheel SHA-256 was `102c6c84048eef76be1263b4123b79de55b5b6af59435c175218305de3042538`.

Byte checks before and after verification covered 43 existing archive, audit and legacy-contract files in **each** tree. No native calculation or production SQLite write was performed. Ordinary conversion requires an identical physical scope. Cross-normalization requires a supported physical relation and externally qualified evidence. File/hash shape validation cannot establish that a site density or loading is scientifically applicable. The explicit network option additionally checks its file/content binding, without granting execution or scientific acceptance.

## Exact changed files

- `MANIFEST.in`
- `configs/release_resources.json`
- `configs/kinetics/rate_output_v2_1.schema.json`
- `pyproject.toml`
- `scripts/optional_dependencies.py`
- `scripts/rate_output_v2.py`
- `scripts/kinetic_parameters/rate_units.py`
- `scripts/kinetic_parameters/rate_normalization.py`
- `tests/test_rate_dimensions.py`
- `modules/kinetic_data/multiphase_contracts.md`
- `modules/kinetic_data/rate_dimensions.md`
- `reports/multiphase/stage_b1_2/completion.md`
- `reports/multiphase/stage_b1_2/handoff.md`
- `modules/state_handoff/events/history-stage-b1-2-dimensional-rate-contract-20261121.json`

[State Handoff receipts and review choices](handoff.md)
