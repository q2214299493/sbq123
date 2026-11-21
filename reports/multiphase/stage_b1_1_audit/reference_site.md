# Synthetic Ni/Cu benchmark · What the reference site counts

The closed cycle uses one normalized Ni-top inventory and one normalized Cu-bridge inventory. Its historical “per reference site” field reports progress per **model reference**. For this benchmark the documented model reference contains one of each site, so the same turnover is reported per reference pair. The per-site average over all individual sites is half that value. Identification of a physical neighbor pair on an arbitrary lattice requires separate evidence.

## Readback from the original calculations

| Evidence | Observation |
| --- | --- |
| Phase 2.5.2 parameter dataset and native input | The adsorption row consumes one `top-Ni` and one `bridge-Cu` vacancy. Native equation 1 is H₂ + #1 + #2 ⇌ H#1 + H#2. The transfer step exchanges site occupancies. Initial vacancy fractions are 1 in each inventory. |
| Phase 2.5.2 validation | `flux_unit` explicitly includes “one inventory unit of each type per reference pair”. Independent site totals in the receipt are each 1. The site counts refer to model inventory units. A Cu bridge as one inventory unit is distinct from the number of Cu atoms in its geometry. |
| Phase 3.0 native input manifest on the development machine | `archive/phase3_0_native/validated/run/input/manifest.json` binds #1 to Ni top, #2 to Cu bridge, the four reaction indices and the generated input bytes. Its file map equals the published benchmark manifest’s native-input map. |
| Phase 3.0 result and workflow configuration | The preserved labels are `one_event_per_reference_site` and `events per reference site per second`. The site rows separately record inventory 1 for each pool. The Ni occupied/vacant fractions are 0.70831345/0.29168655 and the Cu fractions are 0.69667948/0.30332052. Each pool balances independently. |
| Two archived MAT files and matching log extracts | The native reader returns the same four signed net event fluxes from both runs, in reaction order: +81.5127701616477, +81.5127701616477, +163.0255403232954, +163.0255403232954. For H₂ + 2 NO → 2 HNO these give an overall progress of 81.5127701616477 and HNO production of 163.0255403232954, on the native basis per second. These are different observables. |
| Phase 3.1 archived analysis | Its normalization record explicitly sets `reference_basis=reference_site_pair` and `sites_per_reference={top-Ni: 1, bridge-Cu: 1}`. The archived overall turnover is 81.5127701616477 per pair per second and 40.75638508082385 per individual site per second. The archived HNO source is 163.0255403232954 per pair per second and 81.5127701616477 per individual site per second. |

The physical area density, mass loading, reactor volume normalization, real neighbor-pair multiplicity and relationship to an arbitrary Zacros cell do not follow from these mean-field inventories. The archived area-, mass- and reactor-volume-normalized rates are null. Preserve the native label and the model-specific mapping when interpreting either record.

## Units and hashes checked offline

The two native MAT files carry separate `kf`/`kr` coefficients and `R`/`Rnet` fluxes. Using gas stoichiometry and the native pressure convention, all eight archived coefficient units matched in both trees.

| Reaction | Forward coefficient unit | Reverse coefficient unit |
| --- | --- | --- |
| ads | bar⁻¹ s⁻¹ | s⁻¹ |
| transfer | s⁻¹ | s⁻¹ |
| hydrogenate | bar⁻¹ s⁻¹ | s⁻¹ |
| desorb | s⁻¹ | bar⁻¹ s⁻¹ |

The benchmark uses 400 K, total pressure 1.6 bar, partial pressures H₂ 1.0, NO 0.5 and HNO 0.1 bar, gas standard pressure 1 bar, and fractional site occupation. These values come from its records. The MAT arrays by themselves do not identify a physical site density or a reactor rate.

| Binding | Verified SHA-256 |
| --- | --- |
| Canonical parameter dataset version | `417cf1dc3236175476441c4c4e7b4bd5771bc4a7062aa5e34eff69070483d11b` |
| Raw parameter dataset file | `0ac30eec437cebf321339d6c4dde26a0e2146229d8c27fb9fa9f3926adf6d778` |
| Canonical network version | `0978e2199dd35b1bae883edcfb6537376c3152d13fa1f54a4102cc4f035d8264` |
| Raw network file | `6a4717c44a6c5a76191baf88e419621e461886c96989a6cdb86402df70c58b40` |
| Native input and input echo | `b793e6f37f2262e4a006f912d18950c17581ccc014aa9779008741a4e31890f8` |
| Phase 2.5.2 MAT file | `20ebda963c5d5b57e9a47144831a3fd3d416f864d0211db1a4e03020938ff655` |
| Phase 3.0 MAT file | `a010f66603a85035cdcbbc2e81e5ea712c4833a979b7d595df4dcdb386db308d` |

Both worktrees verified the five published Phase 2.5.2 source references, the three Phase 3.0 input hashes, its published result/MAT/log-extract hashes and the native input. On the development machine all eight files listed in the Phase 2.5.2 closed-cycle raw output receipt and all four Phase 3.0 raw output files also matched. The publication checkout contains the published evidence subset.

[Dataset](../phase2_5_2/cycle_dataset.json) · [Configuration](../phase2_5_2/cycle_configuration.json) · [Native equations](../phase2_5_2/catkinas_closed_cycle_input.m) · [Closed-cycle validation](../phase2_5_2/catkinas_closed_cycle_validation.json) · [Phase 3.0 manifest](../phase3_0/benchmark_manifest.json) · [Phase 3.0 result](../phase3_0/result.json) · [Phase 3.1 normalization and turnover](../phase3_1/closed_cycle/analysis.json)
