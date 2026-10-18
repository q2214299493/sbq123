# Three06_C exact-force labels submitted

Date:2026-10-18 Asia/Shanghai.

The configured sunboquan-codex SSH login now succeeds as nsgkn_chengdj3 on
ycn03. No credentials,account,SSH configuration,structure or DFT parameter was
changed. The cause of the earlier public-key rejection remains unverified;
the earlier failure evidence is retained,not overwritten.

Remote read-only prerequisites confirm the unchanged authorized POTCAR hash,
VASP executable,Intel environment and absence of duplicate targets. All three
current canonical SUBMIT_DIAGNOSTIC_VASP gates validate. The canonical
submission executor returned exactly these three independent receipts:

| Frozen sample | VASP job | Ranks | Live queue observation |
| --- | --- | ---: | --- |
| 06C_before_003 | 9896148 | 32 | PEND |
| 06C_after_004 | 9896149 | 32 | PEND |
| 06C_final_057 | 9896150 | 32 | PEND |

The observation is from `ssh sunboquan-codex bjobs -a 9896148 9896149 9896150`.
Queue state is not electronic convergence or force-label acceptance.
All three retain SIGMA=0.20 eV,NSW=0 and the exact frozen input bundles.
Remote parent:
`~/sbq/Fe110/diagnostics/adsorption_06c_boundary_labels_20261018_v1/`.

Local authoritative package:
`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_boundary_labels_20261018_v1/`.
`submission_summary.json` SHA256:
`4795c80cdefe7af0c66cba351503ca2286531f53eae4d37e453f50b4cc18bbaa`.
It references each reservation,job ID,input bundle,POTCAR and canonical gate.
`ready_for_authorized_submission_v2.json` SHA256:
`3b42f7f11ad5433c6951e07ba9c629aaa7043789e2a8af9d41ab5e16f661ab57`.

## Local adapter correction and verification

The first local gate draft failed self-validation before any reservation or
submission. Its in-memory geometry graph contained tuples whereas the saved
JSON contained lists;source binding therefore disagreed before/after reload.
The adapter now re-reads the owning Python writer's saved JSON before binding.
The failed draft is preserved and revised evidence uses distinct `_v2` names.
No execution authority,scientific threshold or core gate implementation changed.

`py_compile` and focused Ruff checks passed. Seventeen focused tests passed:
the existing14 source/geometry-selection tests plus3 new JSON binding,
exclusive-write and distinct-evidence-path tests. An initial test collection
error from a relative namespace import was corrected to the existing absolute
import convention before the successful run. The actual three prepared gates
also passed canonical require_action validation and the executor's live
hash/POTCAR/duplicate checks. No full repository test suite was run.

## Remaining boundary

These jobs diagnose actual ML motif-loss forces;they are not new adsorption
optimizations,accepted adsorption energies or TS calculations. No GPU inference,
training,checkpoint promotion,old-job mutation or database backfill occurred.
Wait for normal termination,EDIFF convergence and complete compatible forces;
then compare originalAQCat25/frozen2185 at these exact saved structures before
deciding whether further training is justified. Existing16 observed heldout
exclusions and24 untrained DFT frames remain unchanged.
