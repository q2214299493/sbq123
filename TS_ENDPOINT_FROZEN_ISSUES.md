# TS Endpoint Frozen Issues

Date: 2026-07-27
Scope: regression confirmation only; no repair authorized

> Historical Phase 3B record. The authorized post-Phase-4 correction is
> documented in `TS_ENDPOINT_ISSUE_CLOSURE_REPORT.md`; the current code no
> longer has the close-contact or empty-`reaction_id` behavior described below,
> and actual surface-normal desorption now requires review.

## 1. Near-contact endpoint

Classification: **PRE_EXISTING_CONFIRMED**

- Pre-Phase-3B behavior: the Phase 3A baseline records a sampled 0.2 Å C–O
  contact as `VALID` with no reason.
- Current behavior: `VALID`, reasons `()`, score `1.0`.
- Regression result: identical; Phase 3B did not introduce it.
- Test:
  `test_validator_current_close_contact_and_detachment_behavior_is_frozen`.
- Cause boundary: `minimum_bond_distance_A` excludes the contact from
  connectivity evidence but is not a collision-rejection rule.
- Future category: scientific defect correction requiring an element-aware
  collision protocol, expected status/reason changes, and scientific review.

This issue must not be repaired as a responsibility refactor.

## 2. Sampled desorption/opposite-motion endpoint

Classification: **PRE_EXISTING_CONFIRMED**

- Pre-Phase-3B behavior: `VALID_WITH_WARNING` with only
  `REACTIVE_ATOM_DISPLACEMENT_WARNING`.
- Current behavior: the same status and exact reason tuple; the sampled COM
  displacement is `0.25493752231345973 Å` because opposite displacement
  vectors partially cancel.
- Regression result: identical; Phase 3B did not introduce it.
- Test:
  `test_validator_current_close_contact_and_detachment_behavior_is_frozen`.
- Future category: scientific-protocol revision. A desorption/surface-distance
  definition, periodic cases, and multi-adsorbate counterexamples require
  separate authorization and scientific review.

This issue must not be repaired by changing the collector's COM formula.

## 3. Empty reaction identity

Classification: **PRE_EXISTING_CONFIRMED**

- Pre-Phase-3B behavior: empty `reaction_id`, `surface`, `reaction_type`, and
  `reactant_id` pass through when geometry validates.
- Current behavior: the empty request fields remain present and the sampled
  result is `VALID`.
- Regression result: identical; Phase 3B did not introduce it.
- Test: `test_empty_reaction_identity_is_currently_passed_through`.
- Future category: input Schema/API validation hardening. It is not evidence
  collection and should not be mixed with scientific endpoint classification.

## Summary

| Issue | Classification | Introduced by Phase 3B | Current test | Future owner |
|---|---|---|---|---|
| 0.2 Å contact | PRE_EXISTING_CONFIRMED | no | yes | scientific defect/protocol task |
| sampled desorption | PRE_EXISTING_CONFIRMED | no | yes | scientific protocol task |
| empty reaction identity | PRE_EXISTING_CONFIRMED | no | yes | input Schema/API hardening |

No `REGRESSION` or `INSUFFICIENT_EVIDENCE` item was found. No frozen issue was
modified during independent acceptance.
