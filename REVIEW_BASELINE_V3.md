# Review Baseline v3

Date: 2026-07-27  
Type: additive post-Phase-2B review baseline

## Conclusion

Review Baseline v3 extends, and does not replace, Review Baseline v2. It binds
the production sources, tests, and reports accepted by the independent Phase 2B
verification. Phase 3A endpoint auditing starts from this baseline.

## Parent chain

- Direct parent:
  `artifacts/review_baseline_v2/baseline_v2_sha256.txt`
- Parent report: `REVIEW_BASELINE_V2.md`
- Parent hashes are recorded in
  `artifacts/review_baseline_v3/parent_v2_sha256.txt`.
- Review Baseline v1, v2, the Phase 2A source baseline, and their hash files
  were not edited.

## Phase 2B binding

The following additive manifests bind the independently accepted Phase 2B
state:

- `phase_2b_verified_source_manifest.txt`
- `phase_2b_verified_test_manifest.txt`
- `phase_2b_verified_document_manifest.txt`

The source manifest records the authorized
`scripts/neb_agent/pilot_validation.py` transition from the Phase 2A hash
`db0d00bc286138bb8a772fb292011845b1b3219f617524b25ca15f963de2e90d`
to the Phase 2B verified hash
`8c280cb54e405bf215d10705213a25f25193bdf3e79730a9921838c53aef969d`.
The historical Phase 2A source baseline therefore remains 24/25 against the
current tree; v3 explains the one authorized difference instead of rewriting
the old baseline.

## Scope and exclusions

Included:

- five Phase 2B verified production sources;
- three Phase 2B verified tests;
- Phase 2B behavior, architecture, implementation, independent review, and
  verified-changeset records;
- the direct Review Baseline v2 parent binding.

Excluded:

- calculation directories and calculation outputs;
- runtime state, scheduler output, SSH/LSF evidence, and temporary files;
- SQLite databases and database contents;
- SQL migrations and migration execution state;
- scientific configurations not modified by Phase 2B;
- endpoint Phase 3A tests and reports, which are later audit outputs rather
  than part of the post-Phase-2B starting point.

## Integrity rule

`artifacts/review_baseline_v3/baseline_v3_sha256.txt` binds the four v3
manifests and this report. It intentionally does not hash itself. Any future
change must be represented by another additive changeset or baseline; v1, v2,
and v3 must not be silently updated.

