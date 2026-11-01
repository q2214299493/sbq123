import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const output = path.resolve('outputs/adsorption_acceptance_20261029_v1');
const manifestPath = path.join(output, 'publication_manifest.json');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const receiptPath = path.join(output, 'view_receipt.json');
try {
  await fs.access(receiptPath);
  throw new Error('Metadata view already written; inspect its receipt before resuming');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
const original = await fs.readFile(manifest.workbook);
const finalPromotion = JSON.parse(await fs.readFile(
  path.join(output, manifest.accepted.at(-1).promotion_id + '.receipt.json'), 'utf8'));
if (digest(original) !== finalPromotion.workbook_sha256_after) throw new Error('Workbook changed after final promotion');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(manifest.workbook));
const main = wb.worksheets.getItem('最终吸附数据');
if (main.getUsedRange().rowCount !== manifest.formal_last_row) throw new Error('Unexpected main-sheet row count');
for (const item of manifest.accepted) {
  const values = main.getRange(`E${item.row}:F${item.row}`).values[0];
  if (String(values[0]) !== item.job_id || values[1] !== item.toten_eV) throw new Error('Accepted value/job binding changed');
}
main.getRange('A65:H67').format.rowHeight = 48;
main.getRange('A65:H67').format.wrapText = true;
main.getRange('F65:F67').setNumberFormat('0.00000000');
const pending = wb.worksheets.getItem('已登记待接受');
if (pending.getUsedRange().rowCount !== manifest.pending_original_rows) throw new Error('Pending view changed');
const current = pending.getRange('A5:F19').values;
for (let index = 0; index < manifest.expected_pending.length; index++) {
  const [name, job, cid] = manifest.expected_pending[index];
  if (current[index][0] !== name || String(current[index][2]) !== job || current[index][5] !== cid) {
    throw new Error('Existing pending identity changed');
  }
}
for (const update of manifest.pending_updates) {
  if (String(pending.getRange(`C${update.row}`).values[0][0]) !== update.job_id) throw new Error('Pending job changed');
  pending.getRange(`E${update.row}`).values = [[update.reason]];
}
for (let index = 0; index < manifest.pending_append.length; index++) {
  const row = 20 + index;
  const range = pending.getRange(`A${row}:F${row}`);
  range.copyFrom(pending.getRange('A7:F7'), 'all');
  range.values = [manifest.pending_append[index]];
  range.format.rowHeight = 48;
}
wb.recalculate();
console.log((await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',
  options: {useRegex: true, maxResults: 20}, maxChars: 1000})).ndjson);
for (const [name, sheetName, range] of [
  ['after_main', '最终吸附数据', 'A65:H67'],
  ['after_pending_top', '已登记待接受', 'A5:E13'],
  ['after_pending_bottom', '已登记待接受', 'A14:E23'],
]) {
  const preview = await wb.render({sheetName, range, scale: 1.2, format: 'png'});
  await fs.writeFile(path.join(output, name + '.png'), new Uint8Array(await preview.arrayBuffer()));
}
const temporary = path.join(output, 'metadata_view.pending.xlsx');
await (await SpreadsheetFile.exportXlsx(wb)).save(temporary);
if (!original.equals(await fs.readFile(manifest.workbook))) throw new Error('Concurrent workbook change');
await fs.copyFile(temporary, manifest.workbook);
await fs.writeFile(receiptPath, JSON.stringify({workbook: manifest.workbook,
  workbook_sha256_before: digest(original), workbook_sha256_after: digest(await fs.readFile(manifest.workbook)),
  publication_manifest_sha256: digest(await fs.readFile(manifestPath)),
  accepted_main_rows: 3, original_main_rows: 64, pending_metadata_rows_added: 4,
  new_scientific_jobs: 0}, null, 2));
console.log('SAVED three accepted main rows and four nonnumeric pending records');
