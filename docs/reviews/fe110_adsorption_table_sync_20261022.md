# Fe(110) adsorption registry-to-table completion —2026-10-22

## Completed result

The user-facing workbook
`outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx` is now updated in
place. Database registration and the Excel view are separate stores; the prior
handoff registered results without completing the visible table. This task
corrects that omission for the bounded01–05/06 records discussed with the user.

- Original55 rows: all values, formulas, cell fonts/fills/borders/alignments/
  formats/protection, column widths, original row heights, merges and freeze
  panes verified unchanged in the saved XLSX.
- `最终吸附数据`,rows56–64:9 accepted final-TOTEN records, comprising the8
  previously accepted01–05 target representatives plus the recovered CH*+CO*
  interpretation. Each numeric TOTEN is bound to its exact accepted registry
  result and a canonical SQLite/JSON Excel-promotion receipt.
- `已登记待接受`,rows5–7:06_A/B/C identities, job IDs, pending status,
  missing-LSF-history reason and06_C duplicate association. This page contains
  text metadata only, no unaccepted numeric energies.
- E0 and Eads for the added rows are explicitly unavailable, not fabricated
  zeroes. Accepted total energies are not claimed to be adsorption energies.

| Main-sheet row | Source | Job |
|---|---|---|
|56|01_cfg2|9839748|
|57|02_cfg2|9839750|
|58|02_extra2|9842106|
|59|03_cfg0_direct_vasp,CH*+CO* interpretation|9839757|
|60|03_extra2_repair_v1|9842136|
|61|04_cfg0|9839751|
|62|04_cfg2|9839755|
|63|05_cfg0|9839753|
|64|05_cfg1|9839754|

The rejected original intact03 interpretation remains rejected. No new VASP,
GPU, model training, reference-energy calculation or scientific acceptance
exception was introduced.

## Minimal compatibility correction

`scripts/registry_excel_promotion.py` now recognizes the current canonical
workflow state `accepted` as well as the supported legacy accepted states.
Unaccepted, duplicate and rejected workflow states remain blocked, and numeric
cells still require accepted compatible result records.

A reviewed reclassification may reuse its declared parent's scheduler history
only through the accepted result's exact OUTCAR file/job link. This supports
the existing03 child interpretation without inventing a second calculation/job
or accepting an unrelated parent's evidence. Missing parent/file/job links are
explicit negative regression cases.

`modules/adsorption_workflow/README.md` now makes the two completion checks
explicit: accepted data pass the existing Excel gate; blocked identities/status
may be visible in a separate metadata-only view. Database-only completion must
not be reported as successful table synchronization.

## Verification and recovery

-50 scoped tests passed, including current/legacy accepted workflow states,
  unaccepted energy rejection, parent/output association, Excel gates, registry
  writes and adsorption-completion rules. Scoped Ruff/compilation passed.
-Saved workbook readback verified all original cells/styles,9 exact
  accepted-source rows,3 metadata-only pending rows and both sheet names.
-Nine unique database Excel-promotion receipts match the written values.
  Repeat publication is rejected. Database quick_check is `ok`; foreign-key
  check is empty.
-Both original and changed views were rendered and visually reviewed. No
  spreadsheet formula errors were reported in the changed view.

Evidence and backup:
`outputs/adsorption_table_sync_20261022_v1/` contains the original-byte
`课题一吸附_最终.before_sync.xlsx`, exact requests/plans/receipts,
`sync_manifest.json`,`view_export_receipt.json`,`verification.json`, test XML
and bounded before/after renders. These are local artifacts, not a claim of
off-machine workbook backup. Source adapters are in
`archive/fe110_adsorption_excel_sync_20261022/`.

The first saved-XLSX verifier imported project-only YAML/jsonschema dependencies
into the bundled spreadsheet runtime. Verification was split into bundled
spreadsheet readback and the project-runtime canonical repeat guard; no
dependency installation or repeated publication was used. The repeat guard
correctly rejects at the existing receipt check before the registry check.

Repository-state projection sync remains blocked by the pre-existing
`sbq_catalyst_agent_workflow.egg-info/PKG-INFO` classification conflict. Workbook
publication, saved-file verification and database receipts above succeeded;
no unrelated classification repair was included.
