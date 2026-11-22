# Ni/Cu · Synthetic closed-cycle benchmark

**Usable boundary.** The archived, accepted CATKINAS single point supports offline rate, occupancy, selectivity and scoped DRC analysis for this synthetic model. All quantities below come from the accepted benchmark artifacts. They establish software behavior within the stated conditions.

| Project role | Binding and interpretation |
| --- | --- |
| Catalyst and interface | Project `demo`; Ni and Cu materials, phases `fcc-Ni` and `fcc-Cu`, surfaces `facet-Ni` and `facet-Cu`, interface `junction`. Keep the two inventories `top-Ni` and `bridge-Cu` distinct. One reference pair has one site of each type. |
| Species | `H2-g`, `NO-g`, `HNO-g` are gas species. `H2-top` and `H2-bridge` each carry one H in the archived definition; `HNO-top` occupies one Ni site. Reading the species formula from its display ID would change the balance. |
| Versioned network and kinetics | `0978e2199dd35b1bae883edcfb6537376c3152d13fa1f54a4102cc4f035d8264`. Dataset `417cf1dc3236175476441c4c4e7b4bd5771bc4a7062aa5e34eff69070483d11b` has a separate reviewed parameter/law record per step. Forward/reverse orders, units, applicability, kinetic eligibility and provenance follow those records. |
| Operating point | 400 K, H₂/NO/HNO partial pressures 1.0/0.5/0.1 bar, total 160000 Pa. Ideal gas standard state 1 bar, fractional surface activities and declared benchmark energy reference. |
| Native evidence | Archived input `catkinas_closed_cycle_input.m`, `data1.mat`, native log extract, benchmark manifest and result. Manifest stage `ACCEPTED` with scientific validity `validated_within_scope`. |
| Observables | Archived overall TOF **81.5127701616477 s⁻¹** on `one_event_per_reference_site`, HNO molar selectivity **1.0** for the declared product list. Occupied fractions **0.7083134510** (Ni) and **0.6966794790** (Cu). Each site balance closes separately. |
| DRC | Archived bounded ranking with stability evidence contains `hydrogenate` **0.4502575521** and `transfer` **0.0406904512**. `ads` and `desorb` have estimates with step-size stability untested and are omitted from that ranking. |
| V2.1 handoff | `catkinas-phase3_0.json` reports native forward, reverse and net events per reference pair per second. Source, run, input, dataset, network and inventory bindings accompany each export. The native single-point acceptance, the adapter qualification and export `validation.status=unreviewed` have different scopes. Rate uncertainty is unmeasured. |

## Four elementary steps

The vacancy changes are explicit reaction fields. Positive net flux is in the direction written. All four are reversible in this *fixture*.

| Reaction | Molecular direction | Vacancy change | Archived net events/(reference pair·s) |
| --- | --- | --- | ---: |
| `ads` | H2-g → H2-top + H2-bridge | Consume one top-Ni and one bridge-Cu | 81.51277016 |
| `transfer` | H2-bridge → H2-top | Release bridge-Cu, consume top-Ni | 81.51277016 |
| `hydrogenate` | H2-top + NO-g → HNO-top | Same top-Ni occupancy | 163.02554032 |
| `desorb` | HNO-top → HNO-g | Release top-Ni | 163.02554032 |

For example, archived `ads` has forward coefficient 1062.533451 and reverse coefficient 58.398207, in bar⁻¹ s⁻¹ and s⁻¹ respectively. Its forward/reverse *fluxes* are 94.007133 and 12.494363 events/(pair·s). The different units and values matter when building a project view. Cross-inventory counting tests also use separate synthetic observations; those inputs must retain their own provenance. [Cross-inventory evidence](../../multiphase/stage_b2_1/interface_validation.json)

## Source files in this checkout

SHA-256 below covers the exact bytes read in the F1.1 worktree. Domain version IDs are recorded separately.

| Source | File SHA-256 |
| --- | --- |
| [closed_cycle_network.json](../../../reports/multiphase/phase3_0/closed_cycle_network.json) | `6a4717c44a6c5a76191baf88e419621e461886c96989a6cdb86402df70c58b40` |
| [cycle_dataset.json](../../../reports/multiphase/phase2_5_2/cycle_dataset.json) | `0ac30eec437cebf321339d6c4dde26a0e2146229d8c27fb9fa9f3926adf6d778` |
| [workflow_configuration.json](../../../reports/multiphase/phase3_0/workflow_configuration.json) | `7687b9fe2495aa010c7faa79da17ada934cf1673dd910b49fa4605461dea6f53` |
| [catkinas_closed_cycle_input.m](../../../reports/multiphase/phase2_5_2/catkinas_closed_cycle_input.m) | `b793e6f37f2262e4a006f912d18950c17581ccc014aa9779008741a4e31890f8` |
| [data1.mat](../../../reports/multiphase/phase3_0/data1.mat) | `a010f66603a85035cdcbbc2e81e5ea712c4833a979b7d595df4dcdb386db308d` |
| [benchmark_manifest.json](../../../reports/multiphase/phase3_0/benchmark_manifest.json) | `0773bdbbf0d3a2f7b8907ed271fdc1f0f725150c5e8c16ae77d10c37d389822d` |
| [result.json](../../../reports/multiphase/phase3_0/result.json) | `6c09b2d304b0829e8912baa670fd274425c4e49a0376f4a4e710db981e4692f7` |
| [result.json](../../../reports/multiphase/phase3_2_1/result.json) | `8c085b8d91213724006b292584e667e84b0787ec143e06bd75d1c2c6951643b0` |
| [catkinas-phase3_0.json](../../../reports/multiphase/stage_b1_4/replay/catkinas-phase3_0.json) | `eb73c3b756ad88316b792df4919c0e08cbe9e0967bcd4d6e2277a5eefcac2ec6` |
| [catkinas_qualification.json](../../../reports/multiphase/stage_b1_4/catkinas_qualification.json) | `9b8bb716277180587c32eb5cd0f4b90c3dfc32ce638a458d4a1717db18bac65d` |
