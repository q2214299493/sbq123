# Read archived native kinetic rates

Both read-only adapters emit `kinetic-rate-output/2`, revision `2.1.0`. Run from the repository root. Standard output contains one V2 document. Add `--qualification` to print its companion observations, source hashes and limitations. In Python, each module's `adapt` returns `(v2, qualification)`. These explicit entry points use the existing unit, source and schema validators.

### CATKINAS single point

```powershell
python -m scripts.baseline_mkm.rate_adapter reports/multiphase/phase3_0/benchmark_manifest.json --network reports/multiphase/phase3_0/closed_cycle_network.json --dataset reports/multiphase/phase2_5_2/cycle_dataset.json --config reports/multiphase/phase3_0/workflow_configuration.json --input reports/multiphase/phase2_5_2/catkinas_closed_cycle_input.m --normalization reports/multiphase/phase3_1/benchmark_normalization.json
```

For the earlier closed cycle, use the Phase 2.5.2 `catkinas_closed_cycle_validation.json` receipt and `cycle_configuration.json`. Each receipt supplies its own MAT and log. The MAT reader resolves native indices, pressure symbols, coverages and gas flux columns. The adapter checks model input regeneration, reaction order and archived observations. Numeric coefficients come from the MAT. Units and activity orders come from the corresponding bound model direction. The engine version is its runtime self-report. The distribution label and native executable digest are separate qualification fields.

These two archive formats have an explicit reference pair. A signed reaction flux has units of events per pair per second. Species sources have units of molecules per pair per second and vacancy sources count vacancies per pair per second. The separately reported average per individual site uses the declared inventory counts. Absolute site density, mass and area conversions require additional evidence.

### Zacros process statistics

```powershell
python -m scripts.surface_kmc.rate_adapter reports/multiphase/phase2_5_1/zacros_validation.json mono tests/fixtures/multiphase/kinetic_interface_network.json
```

Select a case from the receipt. For `dent` and `attractive`, supply the corresponding version-verified synthetic network under `reports/multiphase/stage_b1_4/networks/`. The CLI accepts an explicit network path for any case. A `path.zip!/member` locator identifies the uncompressed member bytes for hashing. The parent ZIP has a separate digest. An absent file promised by a receipt is an integrity error. Without a bound process series or positive measured duration, the record retains unknown applicable fluxes and dependent sources. An excluded model direction is `not_applicable`.

The adapter differences labeled cumulative process counters across the first and last recorded physical samples. It divides by the elapsed simulation time in seconds, once for the entire simulated lattice. Event-matching multiplicities describe the mechanism. They do not rescale an observed whole-lattice count. Species-number columns independently check integrated production on coincident windows. Surface columns count molecules. Negative gas counts record cumulative net gas consumption.

The terminal event and terminal clock are separate from the final sampled row. A continuation binds its input checkpoint to the writer, uses the writer's column labels, and subtracts the counts already present at its first sample. The absorbing-state clock sentinel has no physical elapsed-time interpretation. The companion report preserves native warnings. A short trajectory with one random seed supplies a transient window average. Estimating stationary rates and uncertainties requires an appropriate sampling window and statistical evidence.

### Identity and review

The parameter `dataset_version` and `network_version` are canonical model digests. `output_binding.dataset_id` identifies the derived V2 output by hashing its content before adding this ID. `run_id` preserves the receipt's run identifier, the documented closed-cycle directory name, or the Zacros archive case key. The qualification report identifies the specific receipt. Unit validation preserves the denominator for each engine. The derived output carries `unreviewed`; native convergence and archive replay have their own evidence.

[Offline replay and Windows tests](../../reports/multiphase/stage_b1_4/completion.md)
