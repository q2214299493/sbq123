# Stage A.2.5 State Handoff

Each checkout independently proposed the P5 parser and historical replay record for `docs/08_HISTORICAL_RESULTS.md`. Both proposals require a researcher decision. Available choices are `approve` and `reject`.

| Checkout | P5 proposal | Previous projection SHA-256 | Proposed projection SHA-256 |
| --- | --- | --- | --- |
| dev | `proposal-146f2b9556bb74079934ad7b` | `95856a08d0ce2d0330edcdf51bc316fb4839d18ba54b6551b197a62c437446d9` | `97dc2df111179f2d6921807c857153e6563273f6e4c090dd54604b78f6d48f81` |
| rel | `proposal-c16a0636d2cb63145f831965` | `a637553de4fdae286ec355475372567761d775c932e3634b1dc5ac753f20d155` | `5e17bf660cfd52f8d401940370472b0d0bf6e21b504ee0c9ac07b923486c7593` |

Both `repo-state sync --safe-only` runs returned exit code 2 on existing historical preconditions.

- The development checkout reported `ERROR: evidence hash changed: configs/kinetics/scientific_intake.schema.json`. Event `module-kinetic-data-flexible-intake-frequency-audit-20261119` binds `configs/kinetics/scientific_intake.schema.json` to `cac5550c382a2bafcf2a20c4f7f90b46331de6fbe9f701ca35cf32200151baf4`. The current file hashes to `45dc70815b0e9ec072909f32bb634859b2c9d50c4dc2f556fed0437d9193e9ec`.

- The publication checkout reported `ERROR: state history source changed before proposal generation`. Event `state-history-compacted-7ca5604cfc573d419007f891` binds `docs/02_CURRENT_STATE.md` to `f6eee7315643818ddd25c238bc18db07598db7ef48227fda1fdb2f603f8b71ed`. The current file hashes to `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`.

The P5 event and evidence remain available for review. The existing source conflicts require reconciliation of the recorded revision or a separately reviewed successor. The P5 record conveys parser compatibility only.
