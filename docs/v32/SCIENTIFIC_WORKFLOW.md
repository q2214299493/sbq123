# V3.2 scientific analysis, interpretation and discovery

The installed command `python -I -m sbq123.analysis --help` lists independent read-only entries. Use an MKM interpreter for a point or perturbation study, and a separate KMC interpreter for a window or the historical six-observable comparison. Saved Cantera reports can be read with common alone. The optional Reactor distribution retains ownership of simulation. The discussion below applies to the condition, denominator, catalyst and evidence actually named by each source.

| Entry | Input and scientific output |
| --- | --- |
| `rates ROLE FILE SHA256` | Release-reviewed directional elementary rates. Computes gross molecular formation and consumption including exchange on both sides, retains the independently projected net source and native denominator. Reports competing formation channels with source fractions and identification limits. |
| `point RUN BINDING_SHA256 [--options FILE]` | Replays the owned CATKINAS point and its binding; provides coverage, site utilization, directional flux, product selectivity, native and separately qualified physical TOFs. Local inventory and competition explanations retain the source identity. |
| `window MANIFEST SHA256` | Replays the owning Zacros reader and exposes the observed time window, site use, molecular population and sampling statistics. |
| `retained-window RELATIVE_FILE FILE_SHA256` | Reads a release-indexed historical window report. The evidence class explicitly identifies archive inspection. It does not grant native execution or mark a fresh replay successful. |
| `study MKM_FIXTURE_ROOT` | Reads independently pinned perturbation evidence for the published control, including signed TS DRC, intermediate energy sensitivity and constrained feed order. Scientific conventions and source digests travel with the values. For a new study the existing DRC and sensitivity owners compute derivatives using the appropriate observable, perturbations, conditions, branch and step checks. |
| `reactor RESULT RESULT_SHA256` | Reads all axial PFR samples or separate steady CSTR outlets, gas flows, local directional and net sources, conversion, molar yield and selectivity, and local coverage where present. In dynamic mode re-evaluates the registered kinetics at each recorded MKM state and compares volumetric source terms. |
| `contrast LEFT LEFT_SHA RIGHT RIGHT_SHA VARIABLE` | Outlet differences in conversion, yield and selectivity for a matched single change in temperature or pressure. Feed, flow, geometry, model, mode and other inputs must match. Multiroot CSTR results require a separate branch study. A change in residence time can contribute to an outlet contrast. |
| `comparison MKM_FIXTURE_ROOT REQUEST REQUEST_SHA [--reactor RESULT --reactor-sha256 SHA]` | Existing six MKM/KMC observables with each side's evidence and comparison eligibility. Optional Reactor output supplies local source consistency and integral outlet observations. A native TOF and outlet conversion have different dimensions. Missing optional Reactor evidence leaves the original comparisons available. Set `SBQ123_MKM_PYTHON` to the separate installed worker. |
| `follow-up MKM_FIXTURE_ROOT RATE_FILE RATE_SHA OUTPUT` | Joins the identified native observation to the archived perturbation study, checks the original native output, ranks candidates using the existing priority owner, and writes the proposals and deferred reasons. |

## Evidence and interpretation

Trust comes from the producing environment or an independently retained review. A digest submitted alongside a newly written file only establishes internal consistency. For the file-based Reactor CLI, published trace-correction controls have retained result identities. Other submitted Reactor files are labeled reported-only. A trusted application can call `analyze_profile`, `compare_operating_points` or `compare_local_mkm` with an independently retained producer digest. A changed report fails replay against that digest. Chemical qualification additionally requires appropriate catalyst, conditions and evidence.

Elementary gross traffic uses the integer molecular coefficients of each reaction side and its directional rate. A participant on both sides can have finite gross traffic and zero net production. Missing directional evidence limits the affected sums. The exchange diagnostic reports min(forward, reverse)/max(forward, reverse) for positive traffic when the ratio reaches 0.5. This is a descriptive selection threshold. Rate control requires perturbation evidence. Formation-route shares include recycled molecules. Isotope origin, resolved directions and competing-channel perturbations can distinguish pathway hypotheses.

For archived MKM selectivity, the denominator is the declared product set. Reactor molar yield uses reactant fed and Reactor selectivity uses reactant consumed. For a zero or unavailable denominator the corresponding ratio stays null. A local kinetic source, an event-weighted count, and a time-integrated material flow have different physical meanings. Separate hypothesis, alternative and validation fields accompany supported observations. Missing experimental validation leaves the experimental scope open.

## Mechanism discovery and returned calculations

The existing priority engine checks network reaction and endpoint identities and supplied local geometry. It produces separate ranked, reused and deferred recommendations. Analysis of an univariate flux or concentration can proceed without an atomic structure. A structural calculation proposal requires appropriate structural evidence. Human decisions use the existing `review` action and its write-once decisions directory. Each decision retains its reason. An approved proposal remains planning-only until a separate owning execution gate issues authorization.

The existing priority command now also accepts `ingest-return DIRECTORY REVIEW SHA256 NETWORK_DIRECTORY` through its installed role compatibility entry. The Python entry is `sbq123.discovery.ranking.scientific_priority.returned_result.ingest` after activating the owning role. The scientific review must be independently pinned in `DISCOVERY_RETURN_APPROVALS`. The default set is empty. The review binds the issued proposal and ranking, effective planning decision, original result bytes, owner validation, parent network and validated successor. A completed calculation additionally requires a matching owner execution authorization. An already archived result uses its reviewed provenance. A successor must cite the returned result, preserve unrelated reaction records and pass the original network-version check. The owner publishes the successor to a new content-addressed local path. No current-network pointer or scheduler is changed. Repeating ingestion of the same accepted return yields the same artifact.

Each file reference in a return review has `path` (relative to the review or absolute) and `sha256` of the bytes. See the integration test for the complete `scientific-return-review/1` example, including the test-only approval, a refused unapproved import and altered-source rejection.

## Offline demonstration

Materialize authenticated fixtures with `tools/v32/prepare_history.py v31 mkm FIXTURES/mkm` and the corresponding KMC command using their installed environments. Run:

```text
python tools/v32/scientific_example.py --mkm-python MKM_PYTHON --kmc-python KMC_PYTHON --fixtures FIXTURES --output NEW_DIRECTORY --reactor-evidence TRACE_WINDOWS_ORIGINALS
```

The Fe(110) branch reads the original registered CH + CO evidence, rebuilds a parent and an intake-enriched network with the owning builder, reports electronic energy differences, and retains the missing requirements for kinetics. The separate synthetic point, stochastic sample, retained mock window, perturbation study and Reactor controls demonstrate supported numerical paths. The four-column Fe archive records its own closure and rate-qualification limits. The experiment supplies no missing BADCH clearance.

## Limitations and technical debt for independent audit

- On the previously tested Debian runtime the archived Windows point's three reverse coefficients can differ by one binary64 ULP. Preserve the original hash and rejection. The portable mass contract and original Windows public-entry coverage use their own evidence.
- The frozen synthetic comparison window records a test executable with a different digest from the native Zacros engine. The retained historical window is inspectable. Its native replay remains ineligible. KMC rates have a separate independently reviewed replay route.
- The supplied perturbation and priority benchmark establish software behavior at their specified operating point. Independent KMC sampling and perturbation data are required for stochastic control claims. Physical Fe kinetics, complete free energies and closed-cycle Fe turnover remain unqualified.
- The return mechanism consumes owner-validated revisions. Node-specific preparation, scientific result validation and execution authority stay with the existing owners. No deployment approval for a new physical calculation return is installed.
- The orchestration workspace has a separately tracked scientific-intake schema hash mismatch. Its state sync is outside the candidate's scientific evidence chain.
