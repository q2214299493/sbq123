# Stage B.1.3 · State Handoff

The immutable history event records the implementation, offline Ni/Cu replay and focused Windows tests. It binds the SHA-256 of the completion report, replay JSON and mathematical contract. The owning CLI generated both proposals locally from the current checkout state.

| Checkout | Pending proposal | Requested projection |
| --- | --- | --- |
| Development | `proposal-69edf50a2f79d7b785d0bca3` | Append the B.1.3 history item to `docs/08_HISTORICAL_RESULTS.md` and update its projection manifest. |
| Publication | `proposal-db93dcf70e54ac5c8ef0bd54` | Apply the same history item against this checkout's own history document and manifest. |

The review choices in each corresponding checkout are `approve` and `reject`. Both remain pending. No decision was recorded for either proposal.

## Global safe-only synchronization

- **Development.** The startup audit returned 0 errors and 81 warnings. Global sync subsequently exited 1 on the existing evidence hash conflict for `configs/kinetics/scientific_intake.schema.json`. The current file hash is `45dc70815b0e9ec072909f32bb634859b2c9d50c4dc2f556fed0437d9193e9ec`. Earlier kinetic-data and thermochemistry events independently bind `cac5550c382a2bafcf2a20c4f7f90b46331de6fbe9f701ca35cf32200151baf4` and `feabcbe76179d3624cead8d6469fcdd6a4796ba8e11c1dbaee30944487f5acab`. Resolving those historical bindings requires a separate evidence review.
- **Publication.** The startup audit returned 1 error and 80 warnings, with a pre-existing managed transition-state module row conflict. Global sync exited 1 during proposal generation for `state-history-compacted-7ca5604cfc573d419007f891`. Its historical input hash for `docs/02_CURRENT_STATE.md` is `f6eee7315643818ddd25c238bc18db07598db7ef48227fda1fdb2f603f8b71ed`. The observed file hash is `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`. A reviewer must decide how to reconcile that historical compaction with the current document.

The task-owned proposals were generated before global synchronization. Neither historical conflict changed the B.1.3 replay or test results. [Completion report](completion.md)
