# Phase 1 · contract delivery

**Status:** the ten requested record contracts and their bundle validator are implemented for offline file interchange, version 1.0.0. Phase 0 evidence is indexed in [the baseline audit](phase0_baseline_audit.md).

## Files and functionality

- `configs/catalysis/{catalyst_project,catalyst_material,phase,surface,active_site,interface,common}.schema.json` define six catalyst records and shared types.
- `configs/kinetics/{species,reaction,kinetic_parameter,simulation_run,bundle}.schema.json` define four kinetics records and a bundle envelope.
- `scripts/multiphase_contracts.py` checks schema, identities, references, physical balances, energy arithmetic, review metadata and engine-specific input roles. It reuses `scripts/runtime_resources.py`, `scripts/scientific_validation.py` and the existing JSON Schema dependency.
- `configs/release_resources.json` and `MANIFEST.in` list all twelve schemas for distribution.
- `tests/fixtures/multiphase/{valid,invalid}.json` and `tests/test_multiphase_contracts.py` give reproducible examples and negative controls.
- The owning module README links to the interface. [Schema documentation and CLI usage](../../modules/kinetic_data/multiphase_contracts.md) describe the fields, units, nulls, review boundary and limitations.

A researcher can distinguish adsorption states at different sites on different phases and check a candidate elementary step before constructing a kinetic network. The fixture balances H₂ adsorption across a two-material interface, includes two site types and carries all three engine manifests. Its parameters and structures are synthetic. This work produced no reaction barrier, thermochemistry, catalytic rate or spatial simulation result.

## Verification and handoff

The development checkout and separate release worktree each passed the same 110 tests. The five test files cover the new contracts (69 cases), registry schema, artifact I/O, Python package contract and B7 release resources. Coverage includes all ten record schemas, gas/liquid/surface species, stoichiometric coefficients, signed charge, per-site balance, cross-interface references, each engine's input roles, reversible/irreversible rates, energy units and references, missing data, incompatible Gibbs conditions, reviewed versus synthetic sources, malformed JSON and independent run states. Python compilation, import and scoped Ruff checks passed. A source distribution was built with the configured setuptools backend, then a wheel was built from that archive without network dependencies. All twelve schemas were present in both distributions. The installed wheel resolved its own validator outside the checkout, accepted the valid fixture (exit 0) and rejected the dangling reference (exit 1). The existing temporary-database tests exercise registry compatibility. Phase 0 separately verified the archived runner timeout with a fake process.

Scientific benchmarks and native runtime integration were outside these phases. See the [engine capability matrix](external_engine_compatibility.md) for evidence on installed examples and gaps. The outstanding scientific dependency is an externally reviewed, compatible thermochemical record and its trusted provenance. The exchange validator does not promote records into SQLite or turn a declaration into approval. The active scientific checkpoint retains its own task identity.

Next executable step: review the Phase 1 field, unit and reference mappings against one existing read-only registry case before authorizing any later phase.
