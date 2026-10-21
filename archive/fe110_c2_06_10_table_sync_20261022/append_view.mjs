import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const output = path.resolve('outputs/adsorption_table_06_10_sync_20261022_v1');
const manifestPath = path.join(output, 'sheet_manifest.json');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
const original = await fs.readFile(manifest.workbook);
if (digest(original) !== manifest.workbook_sha256_before) throw new Error('reviewed workbook changed');
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(manifest.workbook));
const sheet = workbook.worksheets.getItem('已登记待接受');
if (sheet.getUsedRange().rowCount !== 7) throw new Error('pending view already extended or changed; do not duplicate');
const existing = sheet.getRange('A5:F7').values;
if (existing.map(row => row[0]).join(',') !== manifest.expected_existing_names.join(',')) throw new Error('existing06 records changed');
if (process.argv[2] === 'inspect') {
  const image = await workbook.render({ sheetName: '已登记待接受', range: 'A1:F7', scale: 1.1, format: 'png' });
  await fs.writeFile(path.join(output, 'before_pending.png'), new Uint8Array(await image.arrayBuffer()));
  console.log('BEFORE:formal64 rows,pending3 records');
} else if (process.argv[2] === 'apply') {
  const receipt = JSON.parse(await fs.readFile(path.join(output, 'registry_receipt.json'), 'utf8'));
  if (receipt.inserted !== 168 || receipt.updated !== 13) throw new Error('reviewed registry batch must be applied first');
  const names = [...existing, ...manifest.append_rows].map(row => row[0]);
  if (new Set(names).size !== 15 || names.join(',') !== manifest.all15_names.join(',')) throw new Error('exact15 records required');
  for (let i = 0; i < manifest.append_rows.length; i++) {
    const row = 8 + i;
    const target = sheet.getRange(`A${row}:F${row}`);
    target.copyFrom(sheet.getRange('A7:F7'), 'all');
    target.values = [manifest.append_rows[i]];
    target.format.rowHeight = 48;
  }
  sheet.getRange('D8:E19').format.fill = '#FFF2CC';
  for (const row of [10, 19]) sheet.getRange(`D${row}:E${row}`).format.fill = '#FCE4D6';
  sheet.getRange('D15:E15').format.fill = '#E7E6E6';
  workbook.recalculate();
  for (const [label, range] of [['after_top', 'A1:F11'], ['after_bottom', 'A12:F19']]) {
    const image = await workbook.render({ sheetName: '已登记待接受', range, scale: 1.1, format: 'png' });
    await fs.writeFile(path.join(output, label + '.png'), new Uint8Array(await image.arrayBuffer()));
  }
  const temp = path.join(output, 'extended_view.pending.xlsx');
  await (await SpreadsheetFile.exportXlsx(workbook)).save(temp);
  if (!original.equals(await fs.readFile(manifest.workbook))) throw new Error('concurrent workbook change');
  await fs.copyFile(temp, manifest.workbook);
  await fs.writeFile(path.join(output, 'view_receipt.json'), JSON.stringify({
    workbook: manifest.workbook, workbook_sha256_before: digest(original),
    workbook_sha256_after: digest(await fs.readFile(manifest.workbook)),
    metadata_rows_added: 12, all06_10_records: 15, accepted_numeric_values_added: 0,
    sheet_manifest_sha256: digest(await fs.readFile(manifestPath)),
  }, null, 2));
  console.log('SAVED:06–10 all15 records;formal energy sheet unchanged');
} else {
  throw new Error('select inspect or apply');
}
