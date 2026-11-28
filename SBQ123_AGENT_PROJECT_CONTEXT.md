---
document_class: CURRENT_REFERENCE
as_of: '2026-11-26T14:36:45+00:00'
source_scope: V3.1 contributor guidance derived from the release contracts
source_version: 32142dbd506d8400e4394fd4e7d36b0bebeda734
source_branch: codex/v31-final-architecture-closure
evidence_kind: CURRENT_CODE_STATE
---

# Agent project context

## Scientific scope across catalyst systems

Follow the [Universal Catalysis System Adaptability Principle](AGENTS.md#universal-catalysis-system-adaptability-principle).
Use the registered profile, the available evidence, and the selected method to
decide which operations can proceed. For example:

| Missing evidence | Work that can proceed when its own requirements are met |
| --- | --- |
| NEB barriers | Independent adsorption analysis |
| Surface-site topology | Empirical kinetic analysis |
| Surface coverage | Gas-phase conversion analysis |
| Experimental validation | Analytical model development, with experimental validation still open |
| Native microkinetic solver results | Independent kinetic-data inspection |

For each outcome, report the evidence used, the applicable domain, and any
limitations. Record blocked operations individually.

## V3.1 release context

Start from the proposed tree and parent in the detached review package. The accepted Candidate 2 parent is `5244831ef2ea7251a19cd580e08380852c2cc88a`, tree `1b90114d41e2860231b246b86a2f13b0deba528d`. Use [the Git baseline](docs/audit/GIT_BASELINE.md) for roles and publication authority.

An edit to an active role originates at the path named by v31/roles.json. Update affected Python source maps, role versions and the role-manifest digest together. Keep original frozen hashes and source variants. Materialize both roles outside the checkout with the release tool, verify their identities, and run each role in an isolated interpreter. Archive new evidence outside source. Read the [contract definitions](docs/architecture/DATA_CONTRACTS.md) before consuming numerical fields.

The optional Reactor handles a single instantaneous isothermal balance. DRC and sensitivity need their own reviewed matched perturbations. Proposal ranking, process completion, a software regression and scientific qualification have separate evidence and owners.
