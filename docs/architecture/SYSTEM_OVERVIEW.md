# V3.1 implemented scientific flow

This diagram shows data flow. Import arrows and source owners are recorded separately.

```mermaid
flowchart TD
  L[Knowledge and literature] --> E[Reviewed scientific evidence and identity]
  E --> N[Reaction network]
  E --> T[Thermochemistry]
  N --> K[Engine-independent kinetic dataset]
  T --> K
  K --> M[CATKINAS adapter]
  K --> Z[Zacros adapter]
  M --> I[Point and window integration]
  Z --> I
  I --> C[Six-observable comparison]
  M --> S[Validated rate observations]
  Z --> S
  S --> A[Shared scientific analysis]
  S --> R[Optional instantaneous gas balance]
  R --> A
  C --> J[Scientific interpretation]
  A --> J
  J --> D[Mechanism discovery proposals]
  D --> H[Researcher decision and owner preflight]
```

Workflow orchestration selects domain operations. Execution governance checks authority for operations with side effects. Artifact Lifecycle Phase 1 owns test artifact classification, manifests, sealing and cleanup proposals. Existing evidence registry transactions and raw execution receipts keep their respective owners. A discovery handoff carries a reviewed proposal to a DFT, NEB/DIMER or model workflow; a new computation and its returned evidence would require separate approval.
