# TS Endpoint Implementation

This package implements the transition-state endpoint boundary owned by
`modules/transition_state_search/`:

- `evidence.py` loads structures and derives geometry/connectivity evidence;
- `validator.py` is the endpoint scientific-validation authority;
- `generator.py` evaluates and selects endpoint candidates;
- `purpose.py` routes explicit structure purposes and orchestrates the services;
- `database.py` persists already-validated endpoint records and owns no science.

Dependencies flow from orchestration to generation and validation, then to raw
evidence. The database adapter is independent of scientific validation. Legacy
imports from `modules.ts_endpoint_*` and `modules.structure_purpose_manager`
remain compatibility aliases; new production code imports this package.
