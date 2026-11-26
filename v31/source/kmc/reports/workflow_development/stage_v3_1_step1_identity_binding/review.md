# SBQ123 V3.1 Step 1 independent-review handoff

The two engines now expose read-only result bindings and share an oriented elementary-reaction identity check. The reviewed `ads` pair fails that check in both worktrees. The same two inventory labels occur on each side of the comparison, while the molecular products differ. This handoff covers identity and evidence binding through the existing native readers. [Contracts](identity-and-evidence-contracts.md) · [Archived counterexample](ads-counterexample.json)

## Evidence read back

| Record | Verified identity | Observation |
|---|---|---|
| [MKM point](mkm-point.json) | Accepted 400 K CATKINAS point, total pressure 1.6 bar. Three approved inputs, native MAT/log and receipt, normalization, initial state, endpoint and residuals are bound. | The point identifies the solution from this specific execution. A separate archived legacy point passed with a supplied normalization profile. |
| [KMC seed 73411](kmc-window-73411.json) | One validated native receipt, 400 K, pure H2 at 1 bar, window 0.05 to 1.55 s on the event clock. | 641 forward and 641 reverse events. Time-weighted occupied fraction 0.9278179714 on each inventory. |
| [KMC checkpoint window](kmc-window-continuation.json) | Three linked segments ending at global events 7, 13 and 24. Each child supplies the previous receipt and checkpoint input digest. | Window 0 to 0.0001 s. Terminal times were 0.0000449236504, 0.0000721897813 and 0.000132209505 s. |

Each saved example was reconstructed again with its engine's `--verify` entry point. The window example values are measurements on a previously run synthetic model.

## Source ownership and verification

Both dirty worktrees started from commit `44e547fae2440a013fad29cf57aa8de5e89b88ea`. Each patch is the delta from the working bytes immediately before Step 1. Applying each patch to its preimages in a temporary directory reproduced all post-change bytes. All 68 entries in the previous planning source inventory were checked against their original bytes or, for the edited KMC reader, its captured preimage. The planning and independent-design-review manifests were also verified. [MKM patch](mkm-step1.patch) · [KMC patch](kmc-step1.patch) · [Preimage and result hashes](source-hashes.json)

| Worktree | Source or test | Reason |
|---|---|---|
| Both | `scripts/kinetic_data/scientific_identity.py` | Reuse catalog fingerprints, elemental/site totals, oriented directions, native pattern validation, canonical hashing and duplicate-key-safe JSON. |
| Both | `tests/test_scientific_identity.py` | Exercise molecular identity independently from inventory, parameter identity and local geometry. |
| MKM | `scripts/baseline_mkm/result_binding.py` | Bind the existing accepted-point/root replay to its plan, approved inputs, conditions, normalization and execution. |
| MKM | `tests/test_mkm_result_binding.py` | Check independent starts, legacy profile attribution and tamper rejection. |
| KMC | `scripts/surface_kmc/study.py` | Collect receipt identities during the existing replay, check writer boundary fields and validate evidence used for binding. Default replay retains its existing return shape. |
| KMC | `scripts/surface_kmc/result_binding.py` | Use the existing exposure/counter integration and issue a digest for one fully identified window. |
| KMC | `tests/test_kmc_result_binding.py` | Distinguish equal-valued windows and verify multi-segment ancestry and rejection cases. |

The two shared files are maintained as identical bytes in their respective checkouts. All implementation and test files listed above are hashed alongside this package. The original V2.1 schemas and accepted archives received no task edits. No commits or pushes were made. [MKM Git status](mkm-git-status.txt) · [KMC Git status](kmc-git-status.txt) · [SHA-256 manifest](SHA256SUMS.txt)

## Offline regression and outstanding boundaries

MKM had 286 passes and one intentionally skipped live CATKINAS test. KMC had 222 passes. Ruff passed on the changed paths in both worktrees. The reports include the exact commands and raw test outcomes. [Regression report](regression-report.md)

- The endpoint digest describes a numerical solution with its separately bound model/conditions. Another attractor, global uniqueness and dynamical stability require additional scientific evidence.
- The KMC examples preserve the compiled network version. They lack independent byte-level qualification of an original source-network file in this interface. Step 1 emits a sidecar for an explicitly requested window. It does not produce an integrated V2.1 rate dataset or authorize cross-engine flux/TOF comparisons.
- Exact encoded site, phase and geometry matches are conservative. A proposed nontrivial site crosswalk, reversed orientation, relabeled embedding, normalization conversion or aggregation needs explicit evidence before comparison. Source/review digests identify existing evidence. Verification assumes the reviewed trust anchor and stable files during replay.
- Sampling precision, cross-seed convergence, Fe qualification and fixed-time spatial sampling remain outside this verification. The evidence comes from synthetic fixtures and archived synthetic benchmark trajectories.
- The repository-state audit in each worktree reported existing managed-projection drift at the `transition_state_search` row in `docs/06_MODULE_MAP.md`. The read-only sync preview applied zero changes and listed 44 pending repository-state proposals in each tree. Exact IDs and offered choices are retained for separate review. [MKM preview](sbq123-mkm-v244-state-preview.json) · [KMC preview](sbq123-kmc-v300-state-preview.json)

Step 1 is ready for independent review.
