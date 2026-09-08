# Phase 3B Changeset Manifest

Date: 2026-07-27
Comparison parent: Phase 3A endpoint hashes and additive Review Baseline v3

## Method

The endpoint modules are untracked in the repository's current Git state, so a
plain Git diff cannot establish their Phase 3A parent. This manifest compares
current bytes against the prechange SHA-256 values recorded in
`PHASE_3B_PRECHANGE_SNAPSHOT.md`, `PHASE_3A_CHANGESET_MANIFEST.md`, and the
append-only source baseline. Git was used only for worktree status and
`git diff --check`; no file was staged or committed.

## Production changes

| Before SHA-256 | After SHA-256 | After bytes | Path | Change |
|---|---|---:|---|---|
| not present | `51822d18e5a61793f40c5f49253d572471327bc4ecc2437d43823af430bdabf2` | 2985 | `modules/ts_endpoint_evidence.py` | new raw-only structure/evidence collector |
| `b0bc707a97c3a032bd5d7d610cb96a961034e17ad763cc1ccb3e7d645f808882` | `04e0a33d98d3317e9c3bec094f854651b1aab5ddc8dd831e173baa3f52c50fa5` | 17710 | `modules/ts_endpoint_validator.py` | delegate raw loading/metrics; retain scientific evaluator |

Production delta within the authorized endpoint scope:

- lines: `+102 -27 = +75` net;
- bytes: `+2985 -929 = +2056` net;
- modules: `+1`;
- public API removals: `0`.

## Test changes

| Before SHA-256 | After SHA-256 | After bytes | Path | Change |
|---|---|---:|---|---|
| `eb02490f8da047e6c5bd2abfe2e6fc32644deba37b3300bb4b6e2139ae8d7615` | `998e85ce61844fa7cb4a7c38d693a13bb380bfb80d2110f06b5a53d39fcf9997` | 30302 | `tests/test_ts_endpoint_contracts.py` | 17 -> 20 contracts; raw collector, exact call count/equivalence, exception/no-write |
| `372bea24306d3555a18ed8a7f0e020255e5cced742236aecca4b022099858cb7` | `14fe6e6ea5a1178659156616089fb9c41c0a4f1d6a5537230c8fba88af68156e` | 22550 | `tests/test_structure_purpose_manager.py` | temp Schema fixture; blocked-migration execution replaced by no-implicit-migration boundary test |

The second before hash is the append-only source-baseline value; Phase 3A
records that the file was unchanged in that phase.

## Phase documents

| SHA-256 | Bytes | Path | Purpose |
|---|---:|---|---|
| `9109ab8858dc57052f3bf1cad64bd32c6911e7bf6797ca9d03b093d2a55b342a` | 3799 | `TS_ENDPOINT_DUPLICATION_AUDIT.md` | restore missing required audit and constrain duplicate removal |
| `25d54beb41ba4091a6524927524d7070c79a5fab552a2d97559d354f4fb3aa93` | 4681 | `PHASE_3B_PRECHANGE_SNAPSHOT.md` | pre-production-change hashes and behavior |
| `a7906dfeda5550bed33685151de88d23f683366e0e25e98b682f9e1a1df75878` | 5312 | `TS_ENDPOINT_REFACTORED_ARCHITECTURE.md` | resulting responsibility and dependency boundary |
| `983254690651876ffa334c40106e50ae01b8e29d21fc6eff05d6fcc54bfb9189` | 5986 | `PHASE_3B_BEHAVIOR_COMPATIBILITY.md` | frozen-sample before/after comparison |
| `785aa6a34a685fa434a052cfca31710f2d8b5ab08e53894ea322bc51d158750e` | 10811 | `PHASE_3B_IMPLEMENTATION_REPORT.md` | implementation and validation report |

This manifest intentionally does not hash itself.

## Byte-identical protected files

| SHA-256 | Bytes | Path | Protection |
|---|---:|---|---|
| `db07eea4541cfdb414cc8957a50dd14b5881264c5310d20df7f6900c28ddc1da` | 6015 | `modules/ts_endpoint_generator.py` | production plan exclusion |
| `f68fbb78a7e5f4926cb0531a5b4b0e38211fc839bd8304f1ad96d846651749b5` | 9668 | `modules/structure_purpose_manager.py` | production plan exclusion |
| `8145e739bf80b0eee5e017a28b3caf4e0dac9310b85090f60d6bcef77208a702` | 7763 | `modules/ts_endpoint_database.py` | production plan exclusion |
| `a4bc47e51e21a612e067b8a4fd123703db3da207219c3ebc7a28f16164ad5315` | 441 | `configs/structure_purpose_routing.yaml` | configuration frozen |
| `43427e5bd1a7950d7ee6defc0ce43c14c80b37b04175ee790fba1f61c629fe88` | 300 | `configs/ts_connectivity_gate.yaml` | configuration frozen |
| `cbbedb50005d1bc57a821d5e983e2578c2d8e43c8f0cfe774f710af91ce1093f` | unchanged | `modules/calculation_registry/migrations/001_ts_endpoint_records.sql` | blocked; not executed |
| `6fdd989767a58aea76987cdbff4b0fa77182f1d4fd8cb2477ae10dacaa4808d5` | unchanged | `modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql` | blocked; not executed |
| `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb` | 958464 | `data/project_registry.sqlite3` | real database; read-only hash only |
| `92d10e9dfc5566ac4bc8ba7766be34342e40d00d0fd5baffc6d99cc673b038b0` | 1696 | `AGENT_RULE_TS_ENDPOINT.md` | governance frozen |
| `ef09dc46dfed65dc573e8268c63a0763c99e17c83290a273136cae7125f8983a` | 2443 | `GOVERNANCE_DOCUMENT_DECISION.md` | governance frozen |
| `221ad9d81d1a0daab4e54702b7b96c25663d43dac4ea8e09f300c30f3e9c57e4` | 1767 | `MIGRATION_REVISION_BACKLOG.md` | migration status frozen |

## Historical baseline-chain controls

No historical baseline file or manifest was written. Current binding-file
hashes are:

| SHA-256 | Path |
|---|---|
| `4dd963fc31e65e8f7f5ebd1e56d9958100547918f9817d180e45632ebcf3b86a` | `artifacts/source_baseline/baseline_sha256.txt` |
| `c4755b9291093e42cb8e26c9a5839a5d9d4d89484717b308afbb63af3876719b` | `artifacts/review_baseline_v2/baseline_v2_sha256.txt` |
| `3e395bac41f647ddd9b8f7b2887c7554f9f8647aa513581c642c0219b0099307` | `artifacts/review_baseline_v3/baseline_v3_sha256.txt` |
| `0726c986fa35e2ab847f3efb92f1fe5cdb9f64af4b023c1b13669c41030ec6ab` | `REVIEW_BASELINE_V3.md` |

## Phase 2B protection spot-check

The five production hashes bound by Review Baseline v3 remain exact:

| SHA-256 | Path |
|---|---|
| `12b277f51a1a9add4c82422ff7024c031dde1ceeca2b6330d80cb06d99d4b523` | `scripts/neb_agent/path_quality_control.py` |
| `0f306f106615ff0524aee590c9dc9b467700ac6e1d19d83ba7db663840feaf20` | `scripts/neb_agent/path_quality_service.py` |
| `9177d24b018549028c075a641f3ab4c5176b9bfab2cea43f780665b56b2c15e9` | `scripts/neb_agent/path_quality_cli.py` |
| `8c280cb54e405bf215d10705213a25f25193bdf3e79730a9921838c53aef969d` | `scripts/neb_agent/pilot_validation.py` |
| `014397403cf9a05c7b44d3aad6d9e11da99bd789c19bc674da60d7872fef1a51` | `scripts/ts_strategy_engine/workflow.py` |

## Excluded runtime and unrelated worktree content

Calculation directories, runtime outputs, scheduler state, generated artifacts,
unrelated tracked modifications, and unrelated untracked files are not part of
this Phase 3B changeset. No SSH, LSF, `bsub`, `bkill`, VASP, NEB, submission,
real-database, or migration action was executed.
