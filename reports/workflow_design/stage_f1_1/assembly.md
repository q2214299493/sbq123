# Minimal project assembly and F1.2 recommendation

Use the existing two-document project/task layout as the **human-facing root**. Add only references to existing domain artifacts when composing a new project. Today a researcher can follow them manually, run Scientific Intake per reaction, inspect a draft network and analyze eligible archives. No common reader was identified that takes this root and returns the eight requested project attributes with verified bindings and missing-data diagnostics.

## Existing root candidates

| Candidate examined | Actual scope / consumer | Assembly decision |
| --- | --- | --- |
| [Research project](../../../calculations/fe110_co_dissociation_neb_20260718/.research/project.yaml) and [task](../../../calculations/fe110_co_dissociation_neb_20260718/.research/tasks/01_co_dissociation.yaml) | Existing calculation-local versioned objective/system/criteria and task-specific stage, constraints, jobs and paths. Specific example concerns CO dissociation. Searching tracked runtime/config sources for the literal project path found the public source index only. | Use as the starting layout for a *new* project. No evidence that these historical files already drive a generic pipeline. Leave their bytes intact. |
| [Catalyst project](../../../configs/catalysis/catalyst_project.schema.json) and [V1 bundle](../../../configs/kinetics/bundle.schema.json) | Catalog identity and reviewed domain exchange for downstream network validation. Project schema has closed properties. | Reference by project ID and file digest. Adding workflow intent here would change a shared scientific exchange contract. |
| [Scientific Intake](../../../scripts/scientific_intake.py) | Merges evidence documents for one reaction and operation. Validates conditions, review and correction routes. | Use per reaction. Its input cannot represent the full project’s tasks, multi-reaction route and independent run receipts. |
| [Named priority sources](../../../tests/fixtures/multiphase/priority_benchmark.json) | Real example of named `path`/`sha256` pairs. Priority import also expects model, protocol, scoring and candidate inputs. | Reuse the reference pattern. For raw MAT/OUTCAR bytes use the existing byte hasher. Priority scoring/registration is unnecessary for assembly. |
| [H7 ticket](../../multiphase/phase3_0/benchmark_ticket_fixture.json) and [run manifest](../../multiphase/phase3_0/benchmark_manifest.json) | Bind one question to a particular single-point plan and record its run, inputs, outputs and validation. | Link where applicable. Projects without a qualified run still need an identifiable root. Engine execution stays behind its existing plan gate. |

## Minimum contents of a project view

These are roles for composing existing documents. They describe a proposed convention for new project inputs. F1.1 does not install a file format or claim that historical projects implement it.

| Required information | Source of truth | If unavailable |
| --- | --- | --- |
| Research objective | Project objective, task ID and success criteria | Report missing objective. |
| Catalyst system | Catalog project ID, material/phase/surface/interface/site records in a bound catalog or network | Report unresolved ownership at the relevant record. |
| Evidence inventory | Named references to one or more intake, structure, calculation, mapping and review artifacts per reaction/state | Report missing data per operation. Distinguish a missing local file from absent scientific evidence. |
| Reaction network version | Reference to the snapshot plus its internal version and project ID | Allow planning or partial identity assessment; record any version conflict. |
| Operating conditions | Referenced kinetic dataset/model and operating-point configuration with units and standard states | Report which condition is missing or inconsistent. Never borrow defaults from another case. |
| Requested observables | Task success criteria or explicit task request, e.g. electronic barrier, ZPE, TOF, selectivity or inventory occupancy | Display requested and available observables separately. Preserve normalization and uncertainty per result. |
| Requested engine route | Explicit task choice of MKM, KMC, both or neither, each with its own optional config and dataset binding | An absent route is unspecified. Read-only evidence inspection remains possible. |
| Execution constraints | Task exclusions, qualification and any separately bound plan/decision/receipt | A route request grants no execution permission. Surface a consumed/stale/failed plan distinctly. |

Resolve each path against its declared base and verify its exact SHA before parsing. A project can explicitly select a local evidence root for protected raw inputs; portable report inventories may refer to sources unavailable in a publication checkout. Preserve such records as unavailable locally. Reject ambiguous roles, traversal outside the declared evidence base, cross-project or wrong-network matches, changed bytes and unsupported versions. Keep the unaffected case evidence visible. Support several reactions or operating points by linking repeated records under their own IDs. Keep original structures, native inputs, reviews and scientific data at their original locations.

## Demonstrated gaps

| Observation | Classification | Owner and smallest response |
| --- | --- | --- |
| YAML supplies project intent; the priority fixture verifies named JSON/YAML references; Intake assesses one reaction. None of the inspected public entry points joins these into a project overview. | Functional integration gap for a single-entry read-only view. Manual project assembly already works. | Kinetic Data owns Scientific Intake and shared exchange. Extend its existing intake CLI with a disjoint inspection path that resolves references, calls the owners and prints readiness per requested observable. Keep `report(documents, operation)` unchanged. |
| Fe IS/FS corrections, shared thermodynamic conditions, reviewed site assignments and rate-law evidence are absent. | Scientific evidence and qualification. | Thermochemistry, reaction network and kinetic owners already provide precise diagnostics. The view should propagate them. |
| Ni/Cu has validated single-point results and two stable DRC rankings. Absolute rates on another denominator require a physical mapping; other DRC step-size checks remain open. | Scope of existing evidence. | Read the existing result and review, preserve native basis and applicability. |
| Oxide topology/counts are available, while the sole native receipt records failed initialization. | Synthetic modeling assumption and native qualification boundary. | Surface KMC exposes the archived diagnostics. An input fix leaves the corrected bundle without an execution receipt. |
| A genuinely different physical model may exceed an adapter’s site, event or rate-law representation. | Conditional limitation. No new requirement demonstrated by these three projects. | Surface only the existing renderer’s diagnostic. A new implementation would require a specific unsupported case and owner test. |

## One bounded F1.2 task

**Add read-only project inspection to the existing Scientific Intake entry point.** Agree the minimal named-reference convention for new task manifests and add an opt-in CLI mode accepting the project/task pair. Reuse existing hash, identity, network, scientific intake and result readers; return a view to stdout. Keep optional inputs absent until an observable requires them. Historical root/task files can still be interpreted as context-only. No migration or new persistent state is necessary.

The smallest meaningful acceptance test is a parameterized, offline inspection of the three mappings plus a tampered reference:

1. Fe returns its three electronic energies, reported TS-local ZPE, missing endpoint corrections and blocked export. Missing literature or raw files in the publication checkout remain visibly scoped.
2. Ni/Cu resolves the exact network, operating point, accepted archive, native denominator and two stable DRC rankings using only referenced data.
3. Oxide returns two molecules and two separate site occupancies, the assumed graph and failed consumed initialization. The corrected bundle has no successful receipt.
4. A supplied file with a changed byte or a network from another case invalidates dependent claims. A genuinely absent optional engine config leaves verified evidence available. Check the same source hashes and state stores before/after and preserve existing positional intake CLI behavior.

A passing result is one command that explains what a new project can support, which source establishes it and what is missing. F1.2 is a recommendation only.
