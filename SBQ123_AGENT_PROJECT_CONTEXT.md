# V3.2 contributor context

The replacement candidate starts at the released V3.1.0 commit `1e899d0d91e0948ed3739b9d623dbbe9e31de637`. Use the installed roles for verification and keep their environments separate. Source, package ownership, validation, limitations and evidence are documented under `docs/v32/`. The earlier V3.2 audit commit is retained separately. Historical CATKINAS and Zacros execution requires explicit approval.

---
document_class: CURRENT_REFERENCE
as_of: '2026-11-26T14:36:45+00:00'
source_scope: V3.1 contributor guidance derived from the release contracts
source_version: 32142dbd506d8400e4394fd4e7d36b0bebeda734
source_branch: codex/v31-final-architecture-closure
evidence_kind: CURRENT_CODE_STATE
---

# V3.1 historical contributor context

Start from the proposed tree and parent in the detached review package. The accepted Candidate 2 parent is `5244831ef2ea7251a19cd580e08380852c2cc88a`, tree `1b90114d41e2860231b246b86a2f13b0deba528d`. Use [the Git baseline](docs/audit/GIT_BASELINE.md) for roles and publication authority.

An edit to an active role originates at the path named by v31/roles.json. Update affected Python source maps, role versions and the role-manifest digest together. Keep original frozen hashes and source variants. Materialize both roles outside the checkout with the release tool, verify their identities, and run each role in an isolated interpreter. Archive new evidence outside source. Read the [contract definitions](docs/architecture/DATA_CONTRACTS.md) before consuming numerical fields.

The optional Reactor handles a single instantaneous isothermal balance. DRC and sensitivity need their own reviewed matched perturbations. Proposal ranking, process completion, a software regression and scientific qualification have separate evidence and owners.
