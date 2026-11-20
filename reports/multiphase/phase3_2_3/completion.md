# Phase 3.2.3 — Scientific Priority Engine

Phase 3.2.3 links condition-specific kinetic evidence to atomistic candidates, checks which evidence can be reused, and writes immutable recommendations for human review. The general engine supports multiple phases, facets, interfaces, target species, site inventories and model versions. The synthetic Ni/Cu benchmark has two ranking policies and three distinct proposed operations. No scientific job was submitted.

## Ni/Cu ranking at 400 K

The accepted parent run uses H₂/NO/HNO = 1.0/0.5/0.1 bar and positive overall turnover per reference Ni/Cu site pair per second. The transition-state DRC is 0.4502575521 for hydrogenate and 0.04069045116 for transfer. HNO-top formation-energy sensitivity is 0.401377874. The constrained NO composition order is 0.494841688 and stays with its fixed-total, proportional-remainder experiment. The network supplies no C3 selectivity derivative.

| Candidate | Reviewed input for importance | Proposed synthetic evidence acquisition | Activity score (position) | Interface score (position) |
|---|---|---|---:|---:|
| hydrogenate TS | TS DRC | DFT single-point energy | 0.816422 (1) | 0.560077 (2) |
| HNO-top | Intermediate Gibbs sensitivity | DFT frequency calculation | 0.743798 (2) | 0.551183 (3) |
| transfer TS | TS DRC | DFT single-point energy | 0.162732 (3) | 0.832207 (1) |

The activity policy weights the scaled absolute derivative, validation-error gap and cost at 82%, 8% and 10%. The interface policy assigns 80% to participation of independent site types, 15% to the activity derivative and 5% to cost. Transfer involves both Ni-top and Cu-bridge. The activity measurement is identical in the two policies. All three candidates lie on the first Pareto front under each policy; the weighted orders express different trade-offs. A fourth record reuses the existing mock transfer geometry. The two alternative policy views produce six content-addressed proposals. All six remain unreviewed and non-runnable.

[Activity report](reports/4da73f1cda3e08ff2a7dfbcfb8e102d4f53d7ed9b2b10b6b7731e3de935c6452.json) · [Interface report](reports/1ead1348ef65787e43393b0250f643c149513ebbb9f6767aedacc0223a8eaa25.json) · [Proposal index](index.json)

## Which numbers carry scientific evidence

- The two DRCs, intermediate derivative, constrained gas order and signed reaction fluxes come from accepted synthetic native results. Their hashes, observable, baseline, temperature, feed, parent network and dataset travel with the report. The raw gas order is context for feed decisions. It is not attributed to a TS or used as a selectivity derivative.
- Site participation, molecular connectivity and flux are distinct. A count or a graph path can inform a screening policy; neither gives a product-pathway percentage. Additional objectives require matching selectivity or contrast data.
- Held-out errors, ensemble standard deviation, calibrated predictive distributions and domain indicators have separate fields. The demonstration's model, atomistic structure IDs/coordinates, training coverage, error magnitudes, costs, prior and posterior uncertainty assumptions are deterministic fixtures. They supply no validation of an actual Ni/Cu potential.
- Transfer has a conditional expected reduction of 0.0011148315 in squared log-TOF loss under the fixture's Gaussian energy prior, expected posterior variance and local derivative. Other candidates have null information value. Weighting choices, saturation scales, ordinal grades and the cost benefit are heuristic. They are configurable per objective. Missing-dimension intervals are score bounds at fixed weights. No empirical rank probability, net monetary value or decision-utility estimate for real Fe is available.

## Real Fe(110) inventory

The development registry was opened read-only. Exact IS/TS/FS structure hashes gave two, two and one distinct calculation-and-file-role hits respectively. Each state's referenced accepted result matched its calculation and scientific review status; all three local structure files matched the declared SHA-256. The registered electronic forward and reverse barriers of 0.97360174 and 0.31429371 eV and previously validated TS local ZPE of 0.51405165 eV are retained. Prior thermochemistry excludes mode 12 as the reaction coordinate. Compatible endpoint corrections or matched endpoint frequencies, site and vacancy accounting, reversibility and reviewed kinetic parameters are still missing. Fe DRC, gas order, intermediate sensitivity, free-energy barriers, predictive uncertainty and priority score remain null. Review endpoint evidence first. The indexed exact-hash search is not an exhaustive symmetry search of unregistered archives. [Read-only Fe inventory](fe110_inventory.json)

## Architecture and validation

The sensitivity and uncertainty owner now exposes the general ranking and review CLI. Its interfaces cover the existing MKM/network outputs, scientific intake, registry lookup, MLIP validation, TS strategy and NEB path-quality evidence, optional SPC Phase 3A proposals and H7 Ticket identity. Real execution stays in the owning workflows. Existing trainer, NEB/DIMER/VASP execution code and production database were untouched. The development and release copies of some MLIP trainer/benchmark and gate files already differ; both histories were preserved.

Both worktrees reproduced the two reports and all six proposals byte for byte. The live Fe database SHA-256 before and after repeating the read-only inventory was 4da73dbbc09fc697933cb6fa191493f78e0fbddb8863eadc66af082700fbe881. The installed SPC independently validated a temporary non-runnable fixture export and rejected malformed input. H7 returned the accepted baseline's bound question ID. No actual human decision was recorded on a scientific proposal. [Module interfaces, assumptions and CLI](../../../modules/sensitivity_uncertainty/README.md)

- full: 5 failed, 2298 passed, 8 skipped, 1 deselected, 15 warnings in 999.93s (0:16:39). [Log](regression/full.txt.gz)
- development: 742 passed, 8 skipped, 1 deselected in 54.98s. [Log](regression/development.txt.gz)
- release: 742 passed, 8 skipped, 1 deselected in 51.84s. [Log](regression/release.txt.gz)

The clean full sweep collected the initial 28 new tests. Both final scoped sweeps included the final 33 priority cases and exercised the later provenance and review checks. The five full-suite failing node IDs exactly match the previously recorded architecture/governance debt. Eight optional native Zacros cases were skipped and the native CATKINAS baseline was deselected in the scoped suites. [Historical regression debt](../phase3_2_0_1/historical_regression_debt.md)
