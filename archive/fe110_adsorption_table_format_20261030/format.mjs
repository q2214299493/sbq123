import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const output = path.resolve('outputs/adsorption_table_format_20261030_v1');
const spec = JSON.parse(await fs.readFile(path.join(output, 'manifest.json'), 'utf8'));
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
if (digest(await fs.readFile(path.join(output, 'before.xlsx'))) !== spec.before_sha256) throw new Error('Source backup changed');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(output, 'before.xlsx')));
const sheet = wb.worksheets.getItem('最终吸附数据');
const phase = process.argv[2];
if (phase === 'before') {
  const blob = await wb.render({sheetName: sheet.name, range: 'A49:H60', scale: 1.1, format: 'png'});
  await fs.writeFile(path.join(output, 'before.png'), new Uint8Array(await blob.arrayBuffer()));
} else if (phase === 'format') {
  for (const item of spec.clear_placeholders) {
    if (sheet.getRange(item.cell).values[0][0] !== item.before) throw new Error('Placeholder changed: ' + item.cell);
    sheet.getRange(item.cell).values = [[null]];
  }
  const body = sheet.getRange(`A3:H${spec.rows}`);
  body.format = {font: {name: 'Arial', size: 11, bold: false, italic: false, color: '#000000'},
    verticalAlignment: 'center', wrapText: true, rowHeight: 42};
  body.format.borders = {preset: 'none'};
  sheet.getRange(`A3:D${spec.rows}`).format.horizontalAlignment = 'left';
  sheet.getRange(`B1:B${spec.rows}`).format.columnWidth = 26;
  sheet.getRange(`E3:E${spec.rows}`).format.horizontalAlignment = 'center';
  sheet.getRange(`F3:H${spec.rows}`).format.horizontalAlignment = 'right';
  sheet.getRange(`F3:H${spec.rows}`).setNumberFormat('0.000000');
  for (let row = 3; row <= spec.rows; row++) {
    sheet.getRange(`A${row}:H${row}`).format.fill = row % 2 ? '#B7DEE8' : '#FFFFFF';
  }
  sheet.getRange('A1:H1').format.font = {name: 'Arial', size: 14, bold: true};
  sheet.getRange('A2:H2').format = {font: {name: 'Arial', size: 11, bold: true, color: '#FFFFFF'},
    fill: '#4472C4', horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 28};
  wb.recalculate();
  console.log((await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',
    options: {useRegex: true, maxResults: 10}, maxChars: 500})).ndjson);
  for (const [name, range] of [['after_header', 'A1:H7'], ['after_join', 'A49:H59'], ['after_tail', 'A60:H67']]) {
    const blob = await wb.render({sheetName: sheet.name, range, scale: 1.1, format: 'png'});
    await fs.writeFile(path.join(output, name + '.png'), new Uint8Array(await blob.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(output, 'formatted.final.xlsx'));
  console.log('STAGED:24 missing-energy placeholders removed;65 uniformly formatted body rows');
} else {
  throw new Error('Use before or format');
}
