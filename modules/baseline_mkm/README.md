---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: MODULE_CONTRACT_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Baseline Mean-Field MKM

## Purpose

Solve the non-coverage-self-consistent mean-field mechanism for coverages, rates, TOF, selectivity, and degree of rate control.

## Primary Software

- CATKINAS is the preferred local mean-field MKM tool; its verified path, runtime, and I/O contract are in `configs/postprocessing_software.yaml`.
- As of 2026-11-19 the supplied single, curve and map examples have result files. The local quickstart log dated 2026-06-26 confirms startup. Completion is unconfirmed (完成未确认). The Fe(110) model still needs a validated input and result. See the [installed-file assessment](../../reports/multiphase/external_engine_compatibility.md).

## Entry Gate

- balanced reaction network
- validated free-energy barriers and prefactors
- temperature, pressure/feed, site density, and rate-law conventions
- CATKINAS input file generated from traceable kinetic records, not manual untracked values

## CATKINAS Input Scope

- reaction mechanism equations and site notation
- activation/free-energy inputs or approved scaling/BEP parameters
- gas pressure or concentration conditions
- initial/frozen coverages when specified
- calculation mode: single, curve, or map
- optional DRC and plotting settings

## Outputs

Phase 2.5 assembles a fixed-temperature CATKINAS single point with frozen gas partial pressures. It consumes an eligible Phase 2.4 dataset, verifies the supplied parameter table, and publishes a byte-hashed input directory. Independent text readback checks stoichiometry, indices, correction switches and both rate coefficients. The installed 20230524 P-code reported expiry before accepting the synthetic model on 2026-11-19. Native reading and numerical completion remain unconfirmed. See the [field contract and assembly command](../../reports/multiphase/phase2_5_native_contracts.md) and [validation receipt](../../reports/multiphase/phase2_5/native_validation.json).

- steady-state solution and site/mass-balance residuals
- TOF, selectivity, coverage, and DRC tables
- reproducible solver settings and provenance
- CATKINAS `result_INPUT*` folder metadata and parsed outputs, when execution is enabled

## Done Criteria

The [Phase 2.5.1 compatibility record](../../reports/multiphase/phase2_5_1/catkinas_compatibility.json) distinguishes the expired installation from the authorized November distribution. The newer P-code read the exact archived reaction and sites. Its equation generator reported no overall reaction and stopped in a symbolic assignment before returning either coefficient. See the [bounded target attempt](../../reports/multiphase/phase2_5_1/catkinas_target_attempt.json).

Mass/site balances close and the CATKINAS inputs, solver settings, rates, coverages, selectivity, and DRC outputs are reproducible and traceable.

Phase 2.5.2 verified the same adsorption equation within a closed, four-step synthetic turnover at 400 K. The native MAT file contains separate directional coefficients and fluxes. Install the `catkinas` extra for the single-point result reader. The [completion report](../../reports/multiphase/phase2_5_2/catkinas_closed_cycle_completion.md) contains the CLI workflow, balance checks, capability matrix and limits on standalone use.


## Phase 3.0 single-point workflow

Run from a source checkout with the CATKINAS optional dependencies. Prepare reads an immutable Phase 2.3 network, regenerates its Phase 2.4 dataset from the reviewed models, and uses the Phase 2.5 adapter to stage the exact input. The configuration selects frozen partial pressures in bar, initial fractions and bounded solver settings. Optional `temperature_K` and `total_pressure_bar` must match the reviewed conditions. Each supported site type has its own unit fractional inventory. The verified native syntax supports reversible equations and singly bound species. Unverified forward-only syntax, unequal site-density normalization and multidentate species require further native evidence.

```powershell
python -m scripts.baseline_mkm.single_point prepare RUN NETWORK.json DATASET.json CONFIG.json H7.sqlite TICKET_ID MATLAB.exe
python -m scripts.baseline_mkm.single_point status RUN
python -m scripts.baseline_mkm.single_point execute RUN REVIEWED_DECISION.json
python -m scripts.baseline_mkm.registration RUN REVIEWER BATCH.json
python -m scripts.registry_write plan --db ISOLATED.sqlite --manifest BATCH.json --output REGISTRY_PLAN.json
```

Use a fresh RUN path. The ticket reader opens the existing H7 database read-only and requires a bound question. The development benchmark uses a labelled synthetic H7 fixture. The status projection exposes the scientific quantities, stages, missing evidence and artifact paths. Its `ticket_handoff` body fits the Supervisor's manual `/api/tickets/handoff` interface. The authenticated viewer owns publication of the note. A qualified run waits for a separately supplied explicit decision. The reviewer checks `plan.json` and the generated model, and supplies the following fields.

```json
{
  "format": "mkm-execution-approval/1",
  "DECISION": "approve",
  "ALLOWED_ACTIONS": ["RUN_CATKINAS_SINGLE_POINT"],
  "question_id": "<existing question_id>",
  "reviewer": "<reviewer identity>",
  "state_sha256": "<exact hash from AWAITING_APPROVAL.json>",
  "source": {"path": "<absolute path to approval evidence>", "sha256": "<source SHA-256>"}
}
```

Execution rechecks the ticket and the plan, snapshots, tool hashes and native bytes. A write-once READY receipt reserves a single invocation. After interruption, inspect status and preserved native files before deciding whether another run is needed. The solver has a 210-second wall limit. An accepted point has a result, a terminal receipt and hashes for the MAT, full log, input echo and console. Numerical convergence, execution, approval and scientific scope are independently reported.

For a declared turnover, supply signed integer `overall_stoichiometry` keyed by gas species ID. The validated gas rates must agree with one reaction extent. `turnover_basis="one_event_per_reference_site"` enables a TOF for that normalization. `selectivity_products` declares the molar product set. Undefined quantities remain null. Coefficient units follow gas order. Fluxes are events per reference site per second.

Registry registration uses the existing plan, reviewed approval and apply sequence. The derived scalar rows are candidates with source-bound normalized evidence. Benchmark registration belongs in an isolated database. See the [Phase 3.0 report](../../reports/multiphase/phase3_0/completion.md) for the verified example and its limits.


## Phase 3.1 kinetic analysis

Use `python -m scripts.baseline_mkm.analysis run RUN OUTPUT` for a completed single-point run. The read-only entry point verifies the terminal acceptance, normalized result, ticket, question, plan, network, dataset and configuration bindings. It reconstructs the gas source terms from the versioned stoichiometry and the signed elementary fluxes, checks directional mass action, and verifies the declared overall extent. A trusted portable Phase 3.0 receipt can also be used with the following commands from the repository root.

```powershell
$p = "reports/multiphase/phase3_0"
$d = "reports/multiphase/phase2_5_2/cycle_dataset.json"
$o = "reports/multiphase/phase3_1/benchmark_normalization.json"
python -m scripts.baseline_mkm.analysis analyze "$p/closed_cycle_network.json" $d "$p/workflow_configuration.json" "$p/result.json" "$p/benchmark_manifest.json" --options $o OUTPUT
python -m scripts.baseline_mkm.analysis inspect NETWORK.json DATASET.json DRAFT_OUTPUT
```

The accepted output bundle contains `analysis.json`, `report.md` and an H7 manual handoff body. The draft bundle contains a structural graph and missing inputs. Repeating a command verifies existing output content. For a registered accepted point, `--registry-reviewer REVIEWER` prepares a separate derived-file batch linked to the existing calculation. Use the existing `registry_write plan` and reviewed apply interface. Analysis and H7 handoff generation do not change ticket or registry state. [Analysis schema](../../configs/kinetics/mkm_analysis.schema.json)

### Analysis options and denominators

The optional JSON supplies the exact network_version plus a source with path (relative to the options file) and sha256. The researcher establishes that the source supports the supplied conversion and scope. The analyzer verifies the file digest. One options record can cite an evidence summary documenting multiple measurements.

| Optional field | Interpretation |
| --- | --- |
| reference_basis, sites_per_reference | Explicit physical reference_site or reference_site_pair; counts of each distinct inventory per common reference. Counts enable a weighted all-site fraction. A pair contains two sites. A run with an unspecified physical basis still has a rate in model-reference units. |
| site_density_mol_per_surface_m2 | Mapping from site ID to mol of that site per m² of its own surface. Molecular coverage times this density gives local surface concentration. |
| reference_mol_per_catalyst_m2, reference_mol_per_kg, reference_mol_per_reactor_m3 | Moles of model reference units per total catalyst surface area, catalyst mass or reactor volume. Multiplication yields a dimensional production rate. |
| catalyst_m2_per_kg, catalyst_kg_per_reactor_m3 | Specific catalyst area and volumetric loading. When the upstream conversion is available, these convert area-normalized rates to mass and then volume rates. Redundant direct and derived factors must agree. |
| target_products, feed_inlet_per_reference_s | Target subset of the configured product set, and supplied inlet flows in molecules per model reference per second. Outlet is inlet plus signed gas production on this same basis. Frozen pressure alone provides no inlet flow. |

### Current kinetic analysis capability matrix

| Output | Verified scope | Interpretation limit |
| --- | --- | --- |
| Coverage and site utilization | Local species coverage, footprint-weighted occupancy, vacancy, competition rankings, phase-specific inventories and reaction vacancy factors | Absolute concentrations require site density. Fraction blocked quantifies the vacancy requirement under mean-field activities. A poisoning or rate-control diagnosis needs separate evidence. |
| Elementary rates | Pressure-based coefficients and units, evaluated activity factors, directional/net fluxes, Gibbs energies and gas source contributions | The 5% near-equilibrium flag uses absolute net divided by gross flux. Relative activity extrema are local to the point. The native runner's forward-only constraint still applies. |
| Turnover and products | Independent extent, overall and product rates, documented physical conversions, molar and elemental selectivity within the declared product set | Empty denominators remain null. Physical conversions apply to the supplied reference; unequal physical densities do not change the accepted steady state. |
| Pathways | Directed stoichiometric reaction edges, candidate feed-to-product paths, branching, dangling surface species, reversible steps, cyclic components, cross-phase site participation | Projected paths describe connectivity. Co-reactant closure is reported separately. Bounded enumeration gives witnesses; signed net event counts per turnover do not uniquely apportion cyclic pathways. |
| Atomistic priorities | Objective-bound DRC, intermediate sensitivities and constrained feed response link to [scientific priority recommendations](../sensitivity_uncertainty/README.md). | Synthetic Ni/Cu validates integration. Real rankings require compatible observables, structural evidence and objective-specific weights. |
| Real Fe(110) | Draft structural inspection and explicit evidence gaps | Kinetic quantities require an independently accepted point. |

[Benchmark report](../../reports/multiphase/phase3_1/closed_cycle/report.md) · [Fe(110) inspection](../../reports/multiphase/phase3_1/fe110/report.md)

### Molecular coverage across site inventories (Phase 3.1.1)

Run the coverage-only analysis from the repository root with a new output filename.

```shell
python -m scripts.baseline_mkm.analysis coverage reports/multiphase/phase3_1_1/network.json reports/multiphase/phase3_1_1/observations.json coverage.json
```

The observation document binds its source description and network version. Its species array uses
the network species IDs. Site multiplicities, surface IDs, interface membership and catalyst phases
come from the network. A repeated occupancy mapping on an observation must agree with that network.
The output records both input file hashes and one molecular row per adsorbate.

For a named reference R, declare the number of molecules per R as the species observation's
`coverage`, name R in `molecular_reference`, and list each independent site population in
`sites_per_molecular_reference[R]`. For species s occupying n sites of inventory i, its occupied
fraction is (molecules of s per R) times n divided by (sites of i per R). An amount per repeat
can exceed one. The same molecule can occupy several sites across an interface. Its molecular
amount appears once. Each inventory lists its own occupied shares, competitors and vacancy fraction.
For an adsorbate confined to one inventory, an omitted reference retains the Phase 3.0 convention
of molecules per site of that inventory. An explicitly null reference marks an unknown basis.

An absent molecular reference, measurement or inventory size leaves the affected conversion null
and is identified on the molecular row. Unknown footprints affect their possible surface domains.
An empty confirmed footprint consumes zero sites. An independent measurement of total occupancy
or vacancy can still be reported while species attribution is incomplete. Complete inventories
check their summed species contributions against the measured balance. Without a measured vacancy,
a complete footprint balance can supply it. Each directional vacancy factor uses the local vacancy
fraction raised to the number of vacancies consumed. Pair adjacency, correlated site availability,
molecular activity and kinetic flux require separate evidence. Coverage observations alone produce
no kinetic result, pathway percentage, or native acceptance.

### Counts on a declared inventory reference

The offline coverage command also accepts an optional `inventory_reference` in its observation file.
For this reference the existing `sites_per_molecular_reference` gives each inventory's capacity.
An observation site may instead supply an exhaustive, nonempty list of `physical_site_ids` in that
finite sample. Its length supplies the capacity. Member IDs are unique within the whole named sample.
Omit the list or use null for unknown membership. One canonical network site ID in competing species'
footprints declares their shared inventory. List its capacity once. Separate IDs denote independent
inventories even when their site type names match. When two IDs claim one physical member, the
affected inventories carry a conflict pending a corrected shared mapping.

Each adsorbate has one `molecule_count` on the named reference. Each inventory receives its own
`occupied_sites` contributions and a `site_counts` record with the reference, capacity, occupied
and vacant amounts. Counts per average repeat may be fractional. For a different declared
reference, common inventories with explicit capacities must give a consistent conversion ratio.
Site fractions use their own capacity. A missing capacity can leave the occupied count known while
the vacancy count and derived fractions are unavailable. Independent total measurements can retain
a balance even with incomplete molecular attribution. Input files without a requested count
reference keep their existing output format and coverage behavior.

The count reference is local to this observation. A catalytic turnover per reference site pair
and a KMC event count per simulation cell retain their native denominators.
[Two-system validation](../../reports/multiphase/stage_b2_1/completion.md)

Existing single-site accepted reports use kinetic analysis v1. A bound accepted result with a
cross-inventory footprint or explicit molecular reference uses v2 molecule and inventory rows.
Checking directional flux on that route requires an explicit dimensionless `surface_activity`
for each reactant with a nonlocal or explicitly specified reference. The graph continues to
report projected connectivity, all-coreactant closure and bounded path witnesses independently.

[Observation example](../../reports/multiphase/phase3_1_1/observations.json) |
[Coverage schema](../../configs/kinetics/mkm_coverage.schema.json) |
[Validated inventory report](../../reports/multiphase/phase3_1_1/validation.json)

### Phase 3.2.0 paired transition-state sensitivity

The pilot accepts the original approved four-reaction synthetic dataset and the transfer TS.
It replays the parent single-point receipt and Phase 3.1 normalization, then produces two
content-addressed derivative datasets on the identical network. The displaced TS changes both
activation Gibbs energies by the same signed increment. The endpoint reaction energy and
kinetic prefactors stay fixed. Source and scientific review fields describe the parent.
The derivative records the signed operation, parent digests and pre/post energies.

```shell
python -m scripts.baseline_mkm.drc_pair prepare PAIR_DIR ACCEPTED_BASELINE_RUN
python -m scripts.baseline_mkm.drc_pair execute PAIR_DIR ACCEPTED_BASELINE_RUN PLUS_DECISION.json MINUS_DECISION.json
python -m scripts.baseline_mkm.drc_pair report PAIR_DIR ACCEPTED_BASELINE_RUN OUTPUT_DIR
```

Use the same pair directory on repeat calls. Preparation is offline. Both decisions use the
single-point approval format above and bind their respective plan hashes. The executor checks
both plans before timing the native pair, runs positive then negative, and limits each invocation
to the smaller of 210 s and the remaining 480 s budget. The clock persists across interruptions.
An accepted member can be reused after its result, approval, raw files and conditions verify.
A claimed, unfinished or failed member cannot be retried. Keep run directories for diagnosis.

The observable is net overall turnovers per declared reference site pair per second.
The dimensionless central estimate uses `-kBT * (ln(r_plus) - ln(r_minus)) / (2 * delta_eV)`.
The sign labels refer to energy. At 400 K the benchmark uses one step size of 0.01 eV.
The product flux supplies an independent overall extent. Rates and directional/net fluxes
are tabulated separately. The fixed step samples the local response over a finite interval.
This pilot supplies neither a mechanism-wide ranking nor an infinitesimal-step convergence study.

[Signed case data and validation](../../reports/multiphase/phase3_2_0/result.json) |
[Native comparison](../../reports/multiphase/phase3_2_0/comparison.md) |
[Result schema](../../configs/kinetics/mkm_drc.schema.json)

### Transfer DRC step-size validation

Prepare the half-step pair in a new directory with `prepare PAIR BASELINE --delta-eV 0.005`.
Supply the two separately approved plans to the same sequential executor. To reproduce the
comparison, use `report PAIR BASELINE OUTPUT --reference-pair ORIGINAL_PAIR`. The report
rechecks both native pairs and their common accepted baseline. Signed one-sided estimates
use kBT ln(baseline/plus)/delta and kBT ln(minus/baseline)/delta.

| DRC capability | Validated scope | Evidence or boundary |
| --- | --- | --- |
| Central and one-sided TS sensitivities | Synthetic transfer reaction at 400 K, fixed pressures and prefactors | Both signed displacements use independent approvals and shift both activation energies. |
| Step-size stability | 0.01 and 0.005 eV, same positive net turnover per reference site pair | Absolute change 0.0004414543 within project tolerance 0.002034523. |
| Pressure-dependent TS sensitivity | Synthetic hydrogenate association, first order in NO forward and zero gas order reverse | Central DRC 0.45025755 at 0.005 eV. Step change 0.00018316 within tolerance 0.02251288. |
| Batch DRC | Four-step synthetic Ni/Cu network at 400 K | Two accepted fine-step pairs reused and two new signed pairs verified. Four measured reactions, two step-size-stable ranking entries. Real Fe kinetics remain blocked. |

[Step-size comparison](../../reports/multiphase/phase3_2_0_1/comparison.md) |
[Machine-readable evidence](../../reports/multiphase/phase3_2_0_1/result.json)

### Cross-reaction DRC validation

Select the reviewed elementary step with `drc_pair prepare PAIR BASELINE --reaction-id hydrogenate --delta-eV 0.01`.
Repeat for the 0.005 eV pair. Use directories named `coarse` and `fine` under a new common root.
The default reaction remains `transfer`. The selected parameter set and both Gibbs barriers
must match the reviewed immutable network and its located TS. Sign-specific plans bind the dataset,
native input, runtime, conditions and original H7 question. Execute the two pairs through
`python -m scripts.baseline_mkm.drc_cross_reaction ROOT BASELINE hydrogenate A_PLUS A_MINUS B_PLUS B_MINUS`
with four approved decision paths. Budgets are 210 s per invocation, 480 s per pair and 960 s total.
A failed member ends the campaign. A previously accepted member is verified before reuse.

Generate the coarse report first. For the fine report pass `--reference-pair COARSE_PAIR --reference-result COARSE_OUTPUT/result.json`.
The pressure audit records per-direction units, orders, gas/surface/vacancy factors, the native equation index,
applied energy parameters and independently reconstructed flux. DRC still uses net overall turnovers per reference site pair.
See the [pressure audit](../../reports/multiphase/phase3_2_0_2/pressure_order.md) and
[cross-reaction comparison](../../reports/multiphase/phase3_2_0_2/result.json).

### Bounded batch DRC pilot

The planner scans all reactions in an immutable network and its matching kinetic dataset.
It records TS identity and grade, reversibility, Gibbs barriers, rate-law units and gas orders per reaction.
Missing estimates are null. A blocked reaction can be inspected without constructing any native input.
The native executor retains the accepted synthetic benchmark scope of the single-point gate.

```text
python -m scripts.baseline_mkm.drc_batch prepare BATCH BASELINE SOURCES.json
python -m scripts.baseline_mkm.drc_batch execute BATCH BASELINE APPROVALS.json
python -m scripts.baseline_mkm.drc_batch report BATCH BASELINE OUTPUT
```

The sources object maps each previously studied reaction ID to `coarse` and `fine` objects.
Each object specifies the accepted native `pair` directory, published `report` path and reviewed file `sha256`.
The planner replays both pairs and checks their signed results, conditions, baseline and normalization.
The global plan contains the remaining reactions and each signed plan hash.
The approvals index binds `batch_plan_sha256` to a `decisions` map whose reaction entries contain
`plus` and `minus` paths to independent, human-approved single-point decisions.

The maximum is four new runs, 210 s per run, 840 s total native time, 960 s wall time, one process and zero retries.
Resume against the same batch directory. A verified accepted member is reused and a failed member stops the batch.
Write each partial report to a fresh output directory. A signed pair supplies central and one-sided estimates,
but ranking additionally requires accepted step-size stability evidence. The one-sided gap measures finite-step
asymmetry. A statistical error bar remains unavailable without suitable additional evidence.
[Batch approval plan](../../reports/multiphase/phase3_2_1/batch-plan.json) · [Result contract](../../configs/kinetics/mkm_batch_drc.schema.json)

### Intermediate sensitivity and gas orders

Select a registered surface species with reviewed formation Gibbs energy, TS evidence and an accepted
site mapping. An energy shift changes the energy of each side by the species stoichiometric count
times the shift. At fixed absolute TS energy the two barrier changes are minus the initial- and
final-state shifts respectively. The central derivative of log net TOF with respect to G/kBT
has a positive kBT prefactor. New datasets record the full formation-energy table and every affected
reaction. The Ni/Cu fixture supplies reviewed synthetic formation energies directly.

Gas experiments select a registered gas by ID. The `fixed_other_partial_pressures` constraint
changes only that gas and updates the declared total. The `fixed_total_proportional_remainder`
constraint preserves total pressure and the ratios among all other partial pressures. Each signed
feed must sum to its declared total and pass every parameter set's pressure validity range.
The composition derivative includes changes in the other gas activities. Both definitions use
the central derivative of log overall TOF with respect to the selected log partial pressure.

```text
python -m scripts.baseline_mkm.sensitivity_study prepare STUDY ACCEPTED_BASELINE EXPERIMENTS.json
python -m scripts.baseline_mkm.sensitivity_study execute STUDY ACCEPTED_BASELINE APPROVALS.json
python -m scripts.baseline_mkm.sensitivity_study report STUDY ACCEPTED_BASELINE OUTPUT
```

The experiments object accepts one `intermediate_G` and one `gas_order` entry, each with
`species_id`, `coarse` and `fine`. Gas experiments also require an explicit `constraint`.
Energy steps are in eV and pressure steps are natural-log increments. Each study member
requires independent single-point approval. The index binds `plan_sha256` to `decisions`
keyed by pair directory and sign. At most eight runs can execute serially within 1680 native
seconds and 1920 wall seconds. Existing accepted members are reused. Read a partial study into
a fresh report directory; incomplete pairs have null estimates. The project step-size tolerance is
the larger of 0.002 and 5% of the absolute fine derivative. An unstable estimate requires separately
authorized follow-up. [Eligibility and missing evidence](../../reports/multiphase/phase3_2_2/eligibility.json)

### Explicit composition grid on a pressure boundary

The Ni/Cu recovery uses the four archived NO grid points with fixed total pressure and proportional
redistribution among the remaining gases. Before accepting each sample, the single-point validator
checks the actual MAT vector against the signed grid, the exact decimal total and the remainder ratios.
The recovery coordinator uses four individually approved runs and stops at the first failure.

```text
python -m scripts.baseline_mkm.reaction_order prepare STUDY ACCEPTED_BASELINE
python -m scripts.baseline_mkm.reaction_order execute STUDY ACCEPTED_BASELINE APPROVALS.json
python -m scripts.baseline_mkm.composition_report STUDY ACCEPTED_BASELINE OUTPUT
```

The approval index binds `study_sha256` to separate coarse and fine decisions for each sign.
Calculate the derivative of log net turnover at the baseline using a quadratic through the three
actual log-pressure coordinates. Report both one-sided slopes and the endpoint secant alongside
the quadratic slope. The fixed-total result applies along the specified feed path.
[Native validation and limits](../../reports/multiphase/phase3_2_2_1/completion.md)

## Map a multiphase network to CATKINAS offline

`python -m scripts.baseline_mkm.network_mapping NETWORK --dataset DATASET --configuration POINT --normalization PROFILE --output-dir NEW_DIR` validates the versioned network and returns a native input and identity crosswalk. For a structural audit, omit the unavailable inputs and use `--report NEW.json`. A blocked mapping returns exit code 2 with the affected species, reaction or inventories and their evidence gaps. Passing this entry point grants no run approval.

The verified multiphase boundary is a reversible, closed turnover with the molecular and vacancy roles observed in the archived two-inventory benchmark. Each reference pair has one member of each inventory. Separate molecules occupying separate sites and a single molecule occupying two sites have different native representability. The project, phase, surface and interface IDs travel with the native indices in the manifest. Consult the [mapping specification and CLI example](../../reports/multiphase/stage_b2_3_1/mapping.md) and [native capability matrix](../../reports/multiphase/stage_b2_3_1/capabilities.md).

The CATKINAS manual (§4.3) documents multi-site species and coverage-variable syntax. A candidate oxide bridge uses `CO2#1#2` and `Q1x2_CO2`. Its coverage denominator for unequal inventories and its native solver results are unverified. The adapter continues to block this topology. See the [oxide assessment and review template](../../reports/multiphase/stage_b2_3_1_1/capability_assessment.md).
