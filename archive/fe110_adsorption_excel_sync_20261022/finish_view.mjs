import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const output = path.resolve('outputs/adsorption_table_sync_20261022_v1');
const manifest = JSON.parse(await fs.readFile(path.join(output, 'sync_manifest.json'), 'utf8'));
const before = await fs.readFile(manifest.workbook);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(manifest.workbook));
const main = workbook.worksheets.getItem('最终吸附数据');
if (main.getUsedRange().rowCount !== 64) throw new Error('expected55 preserved rows plus9 accepted rows');
const rowData = main.getRange('A56:H64').values;
for (let i = 0; i < manifest.accepted.length; i++) {
  if (rowData[i][5] !== manifest.accepted[i].toten_eV || String(rowData[i][4]) !== manifest.accepted[i].source_job_id) {
    throw new Error('accepted source value/job changed before metadata view');
  }
}
// Only newly appended rows receive layout adjustments. Existing55 rows stay intact.
main.getRange('A56:H64').format.rowHeight = 48;
main.getRange('A56:H64').format.wrapText = true;
main.getRange('F56:F64').setNumberFormat('0.00000000');
const sheet = workbook.worksheets.add('已登记待接受');
sheet.getRange('A1:F1').merge();
sheet.getRange('A1').values = [['Fe(110) 已登记待接受记录']];
sheet.getRange('A1:F1').format.font = { name: 'Arial', size: 14, bold: true };
sheet.getRange('A2:F2').merge();
sheet.getRange('A2').values = [['以下仅展示登记状态；未接受的总能不写入正式能量列。重复记录不增加独立构型数。']];
sheet.getRange('A2:F2').format.font = { name: 'Arial', size: 10 };
sheet.getRange('A4:F4').values = [['构型', '最终物种', '任务号', '登记状态', '尚缺条件 / 重复关联', '数据库记录ID']];
sheet.getRange('A5:F7').values = manifest.pending_metadata_rows;
sheet.getRange('A4:F4').format = { fill: '#4472C4', font: { name: 'Arial', size: 11, bold: true, color: '#FFFFFF' }, rowHeight: 28 };
sheet.getRange('A5:F7').format = { font: { name: 'Arial', size: 10 }, verticalAlignment: 'center', wrapText: true, rowHeight: 48 };
for (const [column, width] of [['A', 12], ['B', 23], ['C', 14], ['D', 28], ['E', 43], ['F', 75]]) {
  sheet.getRange(`${column}1:${column}7`).format.columnWidth = width;
}
sheet.getRange('D5:E7').format.fill = '#FFF2CC';
sheet.showGridLines = false;
sheet.freezePanes.freezeRows(4);
workbook.recalculate();
console.log((await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
  options: { useRegex: true, maxResults: 20 }, maxChars: 1000 })).ndjson);
for (const [name, sheetName, range] of [['after_accepted', '最终吸附数据', 'A56:H64'], ['after_pending', '已登记待接受', 'A1:F7']]) {
  const blob = await workbook.render({ sheetName, range, scale: 1.4, format: 'png' });
  await fs.writeFile(path.join(output, name + '.png'), new Uint8Array(await blob.arrayBuffer()));
}
const temp = path.join(output, 'reviewed_view.pending.xlsx');
await (await SpreadsheetFile.exportXlsx(workbook)).save(temp);
if (!before.equals(await fs.readFile(manifest.workbook))) throw new Error('workbook changed during metadata-view rendering');
await fs.copyFile(temp, manifest.workbook);
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
await fs.writeFile(path.join(output, 'view_export_receipt.json'), JSON.stringify({
  workbook: manifest.workbook, workbook_sha256_before: digest(before),
  workbook_sha256_after: digest(await fs.readFile(manifest.workbook)),
  accepted_numeric_rows_unchanged: true, pending_rows_are_nonnumeric_metadata_only: true,
  new_scientific_jobs: 0,
}, null, 2));
