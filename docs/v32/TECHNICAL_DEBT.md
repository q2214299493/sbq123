# Technical debt and scientific limits

| Item | Disposition for this candidate | Evidence or follow-up condition |
|---|---|---|
| Two historical roles with overlapping imports | One common implementation per identical module; separate differing variants and explicit per-process adapters | Canonical ownership and independent installed-role checks |
| Native process timeout | POSIX process group termination and reaping; Windows process-tree termination and bounded reap | Inert parent/child timeout control; no native engine run |
| Case publication and long paths | Verify in a sibling staging directory, use a writer lock, publish by rename; extended Windows paths | Mid-batch failure, retry, existing destination and deep-path controls. The kernel releases a crashed writer’s lock. Its authenticated staging path is recoverable on retry. Legacy locks without ownership metadata require inspection |
| Reproducible packaging | Verify record digests, normalize wheel container metadata and recheck an existing destination | Two builds per OS and wheel identities in the external evidence |
| Original source-root assumptions | Explicit data directories, namespaced distributions and historical compatibility views | Historical regression JUnit and paired replay |
| Scientific inputs for an operating plant | Current release contains analytical and archived benchmark evidence. No new physical catalyst approval was issued | Reviewed dataset, applicable domain and independently reviewed catalyst/site conversion |
| CSTR and surface multiplicity | Report locally converged solutions with seed/continuation receipts, residuals and uncertainty scope | Global continuation or a stability eigenanalysis would require its own validated implementation |
| Transport, energy and pressure drop | Isothermal homogeneous gas balances and intrinsic kinetics | Validated transport properties, pressure-drop or energy model before extension |
| KMC coupling | KMC windows retain their original authority; stochastic source protocol reserved | Independent sampling/uncertainty and coupling validation |
| Historical execution authority | No native CATKINAS/Zacros operation, automatic evidence promotion or scheduler submission belongs to this validation | Production execution and qualification remain separate decisions |


| P2, surface engine upgrade | Cantera 3.2.0 spatial wall-flux handling needs the zero-flux inert coordinate described in the architecture contract | Requalify or retire this workaround when changing the pin |
| P2, scientific qualification | Release-owned synthetic thermodynamics and validated dimensional conversions cover the analytical families only | Obtain independent thermochemistry, site inventory and kinetic qualification for an application |
| P3, resource use | Dynamic results retain local evaluation receipts, including solver trial states. Memory grows with RHS evaluations and multistart count | Bound requested output and retain records when comparing performance |
