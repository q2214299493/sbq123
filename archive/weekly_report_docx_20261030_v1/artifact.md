# Word weekly report authoring contract

- Subject: Fe110 NequIP training and AQCat25 fine tuning, 26–30 October 2026.
- Retained reference: `reports/Fe110_模型训练周报_20261019-20261023.docx`.
- Reference SHA256: `078e43cbece55c303f170b653c3e89dc28cd431ced627fa042825d96c69b4bf5`.
- Task-local `reference.docx` is an exact copy for reproducibility. The original stays unchanged.
- Reference render: `archive/weekly_report_docx_20261023_v1/final_render_v2/page-1.png` and `page-2.png`; both inspected. Existing visual QA binds the same reference hash and two-page render. Section audit confirms one portrait Letter section, 0.85 inch top/left/right margins, 0.80 inch bottom margin.
- Preserve section XML, styles, theme, numbering, page geometry, header/footer distances and all unrelated package parts byte-for-byte.
- Reuse reference paragraph 0 for the Title, paragraph 1 for subtitle, paragraph 3 for Heading 1 and paragraph 4 for body. The existing title uses 22 pt direct typography; body is 10.5 pt Microsoft YaHei with the reference paragraph rhythm. Reuse heading and title black text and no title rule.
- Reuse the light blue table header, visible D9D9D9 borders, flexible row heights, repeated header, padded cells and body font. Deliberate column widths vary with content. Numeric cells are centered and descriptive cells left aligned.
- Editable slots: all `word/document.xml` body paragraphs and tables except `w:sectPr`; header/footer text; core title/subject/author/date metadata; new source hyperlink relationships. No images, content controls or field refresh is needed. Other package parts and relationships are preserve-only.
- Content flow: conclusion and data coverage, training comparison and ML checks, DFT comparison, uncertainty and next-week priorities. Use natural pagination and repeated table headers; do not force page breaks or shrink the body text.
- Replace all old scientific text and dates. Old weekly figures are not comparison baselines for the new 512-frame trial.
- Main distinctions: saved epoch versus final epoch, partial versus completed training, development selection versus independent evaluation, ML force versus DFT force, user cancellation versus numerical failure, convergence versus scientific acceptance.
- Build gate: verify reference and source existence, compare the native training summary and stop review, validate tabulated metrics and all links, preserve unrelated package parts, preserve section XML, and confirm no stale dates or old values remain.
- Render gate: attempt the packaged renderer. This Windows runtime has no bundled LibreOffice. If unavailable, reuse the established read-only Microsoft Word PDF export plus the packaged renderer's rasterizer with bundled Poppler. Inspect every final page.
- Scope: report creation only. No new inference, training, calculation, queue polling, model promotion, private-data upload or scientific state changes.
