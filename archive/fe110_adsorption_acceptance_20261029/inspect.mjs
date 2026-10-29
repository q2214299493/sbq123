import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve('outputs/adsorption_acceptance_20261029_v1');
const phase = process.argv[2];
if (!['before', 'after'].includes(phase)) throw new Error('Specify before or after');
const book = phase === 'before'
  ? path.join(root, 'before.xlsx')
  : path.resolve('outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(book));
console.log((await wb.inspect({kind: 'sheet', include: 'id,name', maxChars: 600})).ndjson);
const ranges = phase === 'before'
  ? [['main', '最终吸附数据', 'A54:H64'], ['pending', '已登记待接受', 'A8:E19']]
  : [['main', '最终吸附数据', 'A65:H85'], ['pending', '已登记待接受', 'A5:E19']];
for (const [label, sheetName, range] of ranges) {
  const blob = await wb.render({sheetName, range, scale: 1.2, format: 'png'});
  await fs.writeFile(path.join(root, `${phase}_${label}.png`), new Uint8Array(await blob.arrayBuffer()));
}
console.log((await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',
  options: {useRegex: true, maxResults: 15}, maxChars: 800})).ndjson);
