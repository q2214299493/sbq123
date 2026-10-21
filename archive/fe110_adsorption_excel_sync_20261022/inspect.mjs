import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const bookPath = path.resolve('outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx');
const output = path.resolve('outputs/adsorption_table_sync_20261022_v1');
await fs.mkdir(output, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(bookPath));
console.log((await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 1000 })).ndjson);
for (const [name, range] of [['before_header', 'A1:H12'], ['before_tail', 'A43:H55']]) {
  const blob = await workbook.render({ sheetName: '最终吸附数据', range, scale: 1.5, format: 'png' });
  await fs.writeFile(path.join(output, name + '.png'), new Uint8Array(await blob.arrayBuffer()));
}
console.log((await workbook.inspect({ kind: 'table', range: '最终吸附数据!A50:H55',
  include: 'values,formulas', tableMaxRows: 6, tableMaxCols: 8, maxChars: 1800 })).ndjson);
