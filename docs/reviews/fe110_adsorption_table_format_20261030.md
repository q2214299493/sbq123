# Adsorption workbook presentation correction —2026-10-30

The user requested a consistent table and explicitly required missing values
to remain empty. The canonical workbook is
`outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx`.

- Cleared24 textual placeholders in G56:H67. Existing missing cells remain
  empty; no scientific number was added or changed.
- Applied the existing blue/white alternating-row pattern to all65 data rows,
  with consistent Arial11 font, middle alignment and42-point row height.
  The final-site column was widened to26 to avoid isolated wrapped characters.
- Energy columns display six decimal places. All underlying numeric values,
  identifiers, text outside those placeholders, formulas and data types are
  preserved. The pending sheet retains its content, styles and dimensions.
- Independent saved-XLSX readback passed for all179 existing numeric cells,
  all65 row bands and all24 cleared cells. Header, join and tail views were
  rendered and inspected. Python compilation/Ruff and Node syntax checks pass.
  No scientific workflow, registry update or broad test suite was run.

Original-byte backup, manifests, initial/final previews, final verification and
publication receipt are local under
`outputs/adsorption_table_format_20261030_v1/`. The original workbook SHA256 is
`7d118f3d926ebc30ec76014effca6486995b85efe588a64abaedf0078c994191`;
the corrected workbook SHA256 is
`7cb9eb8e6323c7f87abe8de47d59bb224dc8f720e2a81b138454cef79a745eb6`.
Historical numeric-promotion receipts remain immutable; the format receipt
binds the authorized text/style revision and verifies zero numeric changes.

Bounded adapters are in `archive/fe110_adsorption_table_format_20261030/`.
Excel initially held the workbook; the user saved and closed it before the
guarded atomic replacement. Native Excel post-save rendering is unverified;
artifact previews and saved-file readback passed. The pre-existing PKG-INFO
classification conflict still prevents managed repository-view sync.
