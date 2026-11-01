# Fe(110) C2 final-state acceptance and main-table synchronization

Reviewed 2026-10-30, Asia/Shanghai, under the user's explicit request to
complete converged-record review and synchronize the main adsorption table.
The evidence package retains its start-date name `adsorption_acceptance_20261029_v1`.

## Completed scope

Six complete existing VASP output sets were collected with exact remote/local
SHA256 checks. Canonical final-SCF/ionic convergence, the locked 0.02 eV/Angstrom
movable-force limit, exact final CONTCAR/force correspondence, connectivity,
clean-Fe45 constraints, production inputs and POTCAR-bundle compatibility pass.
Historical scheduler DONE snapshots were recovered for five paired jobs; the
recent FT512 job has a current DONE observation. Observation dates are retained.

Three surface-state representatives passed formal acceptance and the separate
registry-to-Excel gate:

| Main row | State | Source job | Final movable fmax, eV/Angstrom |
|---|---|---|---:|
|65|C2HO, C-O-CH|9910781|0.017418|
|66|C2H2O, C-O-CH2|9910785|0.014906|
|67|C2H3, CH-CH2|9926807|0.018306|

The workbook is `outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx`.
New numeric F cells contain accepted final OUTCAR TOTEN values under
`fe110_converged_toten_sigma0p20_v1`. E0 remains unregistered and Eads remains
unavailable pending an accepted compatible reference tuple. Total energies
are not presented as adsorption energies, thermal free energies or proof of
vibrational/global minima. No protocol or model was promoted.

Jobs9910787,9910789 and9910791 are retained as reviewed duplicate sources.
Surface-aware comparisons use the existing clean-slab symmetry, H-permutation,
RMSD and energy rules. They add zero independent formal rows. Selection of a
numerical representative does not establish physical or model superiority.
Original06_C,09_C and10_A have verified same-state links to rows65,66 and67;
their own acceptance status is preserved separately.

## Remaining boundaries

The original15 jobs9848799-9848813 have no recorded DONE in the registry,
current bjobs/bacct queries or all-history bhist response. The bounded native
job-report check found empty output files; discovered accounting logs did not
provide these observations.13 prior numerically converged sources retain
truthful pending/duplicate status, and07_C/10_C remain nonconverged. The earlier
01-05 task-scoped scheduler exception was not extended. Paired06_C candidate
9910783 also lacks terminal scheduler evidence and remains `needs_review`,
with queue availability explicitly recorded as UNKNOWN.

The existing pending sheet retains all15 original identities, updates13
review reasons and adds four metadata-only rows for the blocked paired06_C
candidate and three duplicate sources. No unaccepted numeric energy was added.
No new calculation, continuation, stop, GPU run, training or reference job occurred.

## Verification and recovery

- 107 directly related tests passed; scoped Python compilation/Ruff and Node
  syntax checks passed. No full-repository or scientific-compute test was run.
- Independent bundled-Python/openpyxl readback verifies all original64 main
  rows, original pending identities and unchanged values/formulas/styles outside
  the declared pending-reason updates,
  original widths/heights/merges/freeze panes, three exact accepted-source rows
  and four metadata-only additions. Both changed views were rendered and reviewed.
- Canonical acceptance batch inserted84 rows and applied9 workflow changes.
  Three unique Excel receipts match exact accepted result IDs and saved values.
  Final closure inserted3 tracking rows and applied4 workflow changes: three
  `excel_promoted` states and the one blocked paired06_C source. Readback,
  SQLite quick_check, foreign keys and read-only repeat-publication rejection pass.
- The first remote external-sha256sum snapshots timed out during large OUTCAR
  hashing. Those failures are retained. A native Python streaming-hash snapshot
  and compressed copies completed with byte-exact checks; no job was retried.
  Excel initially held a write lock; the user saved and closed it. The original
  workbook hash remained unchanged before the first controlled write.

Evidence, original workbook backup, exact plans/approvals/receipts, source-code
bindings, failed-collection records and renders are local under
`outputs/adsorption_acceptance_20261029_v1/`. Important readbacks are
`workbook_verification.json`, `registry_readback.json` and
`final_verification.json`. The final workbook SHA256 is
`7d118f3d926ebc30ec76014effca6486995b85efe588a64abaedf0078c994191`.
Native Excel post-save behavior was not exercised; saved-XLSX structural and
visual checks passed. Managed state-view sync retains the pre-existing
`sbq_catalyst_agent_workflow.egg-info/PKG-INFO` classification blocker.

## Source and execution

Bounded adapters/tests are under
`archive/fe110_adsorption_acceptance_20261029/`. They execute in the canonical
`work` checkout with its existing scientific owners and archived completion
helpers, including `archive/fe110_coads_registry_20261021/prepare.py` and
`archive/fe110_adsorption_calibration_20261018/reviewed_trajectory_helpers.py`.
The source-release branch records task-owned adapters and documentation;
private workbook, registry and raw runtime outputs remain local.

Next: recover authoritative terminal scheduler evidence for the remaining
closed sources before any further formal acceptance. Preserve the current
scientific protocol and missing-reference labels.
