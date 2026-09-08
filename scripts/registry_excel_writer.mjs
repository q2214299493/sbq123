/* Controlled workbook append used by scripts.registry_excel_promotion.
 * This script intentionally has no registry access: Python builds the
 * hash-bound plan, and this writer only verifies the requested worksheet and
 * appends exactly one already-resolved row with @oai/artifact-tool.
 */

import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) {
    throw new Error(`missing ${name}`);
  }
  return process.argv[index + 1];
}

function columnName(index) {
  let value = index;
  let output = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    output = String.fromCharCode(65 + remainder) + output;
    value = Math.floor((value - 1) / 26);
  }
  return output;
}

function sameHeaders(actual, expected) {
  return actual.length === expected.length && actual.every((value, index) => String(value ?? "").trim() === expected[index]);
}

const planPath = argument("--plan");
const outputPath = argument("--output");
const plan = JSON.parse(await readFile(planPath, "utf8"));
const moduleSpecifier = process.env.REGISTRY_ARTIFACT_TOOL_MODULE || "@oai/artifact-tool";
const artifact = await import(moduleSpecifier.startsWith("file:") ? moduleSpecifier : pathToFileURL(moduleSpecifier).href);
const { SpreadsheetFile, FileBlob } = artifact;
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(plan.workbook_path));
const sheet = workbook.worksheets.getItem(plan.worksheet_name);
if (!sheet || sheet.isNullObject) {
  throw new Error(`worksheet not found: ${plan.worksheet_name}`);
}
const used = sheet.getUsedRange();
const headerIndex = plan.header_row - 1;
if (!Number.isInteger(headerIndex) || headerIndex < 0 || headerIndex >= used.rowCount) {
  throw new Error("promotion plan header row is outside the used worksheet range");
}
const header = used.getRow(headerIndex).values[0];
if (!sameHeaders(header, plan.headers)) {
  throw new Error("worksheet header does not exactly match the reviewed promotion plan");
}
if (plan.row_values.length !== plan.headers.length) {
  throw new Error("promotion row does not match the reviewed header count");
}
const lastValues = used.getRow(used.rowCount - 1).values[0];
const trailingNote =
  String(lastValues[0] ?? "").trim().startsWith("说明：") &&
  lastValues.slice(1).every((value) => value === null || String(value).trim() === "");
const updatingExistingRow = Number.isInteger(plan.target_row);
const rowNumber = updatingExistingRow
  ? plan.target_row
  : trailingNote
    ? used.rowCount
    : used.rowCount + 1;
if (updatingExistingRow && (rowNumber <= plan.header_row || rowNumber > used.rowCount)) {
  throw new Error("existing-row promotion target is outside the used worksheet range");
}
if (updatingExistingRow) {
  const currentValues = sheet
    .getRange(`A${rowNumber}:${columnName(plan.headers.length)}${rowNumber}`)
    .values[0];
  for (let index = 0; index < plan.source_bindings.length; index += 1) {
    if (plan.source_bindings[index].kind !== "existing_workbook_cell") {
      continue;
    }
    const actual = currentValues[index];
    const expected = plan.row_values[index];
    const matches =
      typeof actual === "number" && typeof expected === "number"
        ? Object.is(actual, expected) || Math.abs(actual - expected) <= 1e-12
        : String(actual ?? "") === String(expected ?? "");
    if (!matches) {
      throw new Error(`existing workbook cell changed at row ${rowNumber}, column ${index + 1}`);
    }
  }
} else if (trailingNote) {
  const noteSource = sheet.getRange(`A${rowNumber}:${columnName(plan.headers.length)}${rowNumber}`);
  const noteTarget = sheet.getRange(`A${rowNumber + 1}:${columnName(plan.headers.length)}${rowNumber + 1}`);
  noteTarget.copyFrom(noteSource, "all");
  noteSource.unmerge();
}
const target = sheet.getRange(`A${rowNumber}:${columnName(plan.headers.length)}${rowNumber}`);
if (!updatingExistingRow && rowNumber > 2) {
  const formatSource = sheet.getRange(`A${rowNumber - 1}:${columnName(plan.headers.length)}${rowNumber - 1}`);
  target.copyFrom(formatSource, "all");
}
target.values = [plan.row_values];
if (!updatingExistingRow && trailingNote) {
  target.format = { font: { italic: false, color: "#000000" }, wrapText: true };
}
const bindingIndex = (predicate) => plan.source_bindings.findIndex(predicate);
const energyColumns = {
  initial: bindingIndex((item) => item.kind === "barrier_energy" && item.role === "initial"),
  ts: bindingIndex((item) => item.kind === "barrier_energy" && item.role === "ts"),
  final: bindingIndex((item) => item.kind === "barrier_energy" && item.role === "final"),
};
const formulaColumns = {
  forward: bindingIndex((item) => item.kind === "barrier_field" && item.field === "forward_barrier_ev"),
  reverse: bindingIndex((item) => item.kind === "barrier_field" && item.field === "reverse_barrier_ev"),
  reaction: bindingIndex((item) => item.kind === "barrier_field" && item.field === "reaction_energy_ev"),
};
if (Object.values(energyColumns).every((index) => index >= 0)) {
  if (formulaColumns.forward >= 0) {
    sheet.getRange(`${columnName(formulaColumns.forward + 1)}${rowNumber}`).formulas = [[
      `=${columnName(energyColumns.ts + 1)}${rowNumber}-${columnName(energyColumns.initial + 1)}${rowNumber}`,
    ]];
  }
  if (formulaColumns.reverse >= 0) {
    sheet.getRange(`${columnName(formulaColumns.reverse + 1)}${rowNumber}`).formulas = [[
      `=${columnName(energyColumns.ts + 1)}${rowNumber}-${columnName(energyColumns.final + 1)}${rowNumber}`,
    ]];
  }
  if (formulaColumns.reaction >= 0) {
    sheet.getRange(`${columnName(formulaColumns.reaction + 1)}${rowNumber}`).formulas = [[
      `=${columnName(energyColumns.final + 1)}${rowNumber}-${columnName(energyColumns.initial + 1)}${rowNumber}`,
    ]];
  }
}
if (trailingNote) {
  sheet.getRange(`I${rowNumber}`).format.numberFormat = "0.000000";
  sheet.getRange(`Q${rowNumber}`).format.numberFormat = "yyyy-mm-dd hh:mm";
  sheet.getRange(`U${rowNumber}:V${rowNumber}`).format.numberFormat = "0.00000000";
  sheet.getRange(`X${rowNumber}`).format.numberFormat = "0.00000000";
  sheet.getRange(`Y${rowNumber}:AA${rowNumber}`).format.numberFormat = "0.000000";
}
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
process.stdout.write(JSON.stringify({ row_number: rowNumber, worksheet_name: plan.worksheet_name }));
