# Governance Document Decision

Date: 2026-07-27
Approved by: project owner

## Decision

| File | Classification | Status |
| --- | --- | --- |
| `AGENT_RULE_TS_ENDPOINT.md` | project governance document | `FORMAL_GOVERNANCE_DOCUMENT` |

The document governs agent behavior, approval boundaries, and the endpoint
generation and validation workflow. Its reference in
`modules/transition_state_search/README.md` as the stable-product endpoint rule
authority is interpreted within that governance scope.

It does not replace or override:

- configuration Schemas and their validated configuration values;
- formal scientific protocols;
- tested validation logic implemented in code;
- human scientific review.

A threshold mentioned by this governance document is authoritative only when
it cites a formal configuration or protocol. Future changes to the document
must record version, date, reason, compatibility impact, and approver.
Formalization does not change the rules currently written in
`AGENT_RULE_TS_ENDPOINT.md`; that file was not edited in Phase 2A.1.

## Independent content review

| Check | Evidence | Result |
| --- | --- | --- |
| Conflict with configuration or code | The required mapping, reaction-event, path-connectivity, local-stability, and priority semantics agree with `configs/structure_purpose_routing.yaml`, `modules/ts_endpoint_validator.py`, `modules/ts_endpoint_generator.py`, and the transition-state module README. | No conflict found. |
| Unsupported scientific threshold | The document contains no numeric scientific threshold. Configured thresholds remain owned by formal configuration and tested code. | None found. |
| Automatic approval of high-risk structures | The document requires all preceding validation gates before energy can influence selection and states that lowest energy is neither automatic acceptance nor rejection. | None found. |
| Execution-gate bypass | The document grants no NEB action and does not alter the requirement that `execution_gate.py` and its hash-bound `ALLOWED_ACTIONS` authorize execution. | None found. |
| Automatic migration, submission, or deletion | The document contains no rule that performs or authorizes migration, job submission, file deletion, or database deletion. | None found. |

This review establishes the document's identity and authority boundary only. It
does not approve a calculation, modify a scientific rule, or authorize an
endpoint migration.
