import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const out = path.resolve('outputs/fe110_c2_registration_20261102_v1');
const request = JSON.parse(await fs.readFile(path.join(out, 'request.json'), 'utf8'));
const phase = process.argv[2];
if (!['before', 'finish'].includes(phase)) throw new Error('Specify before or finish');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const original = await fs.readFile(request.workbook);
if (phase === 'before' && digest(original) !== request.workbook_sha256_before) throw new Error('Saved workbook baseline changed');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(request.workbook));
const main = wb.worksheets.getItem('最终吸附数据');
const pending = wb.worksheets.getItem('已登记待接受');

async function preview(label, sheetName, range) {
  const blob = await wb.render({sheetName, range, scale: 1.1, format: 'png'});
  await fs.writeFile(path.join(out, label + '.png'), new Uint8Array(await blob.arrayBuffer()), {flag: 'wx'});
}

if (phase === 'before') {
  const baseline = {workbook_sha256: digest(original), main_rows: main.getUsedRange().rowCount,
    pending_rows: pending.getUsedRange().rowCount, headers: main.getRange('A2:H2').values[0],
    pending_headers: pending.getRange('A4:F4').values[0],
    original_main_values: main.getUsedRange().values, original_pending_values: pending.getUsedRange().values};
  await fs.writeFile(path.join(out, 'workbook_baseline.json'), JSON.stringify(baseline, null, 2), {flag: 'wx'});
  await preview('before_main', '最终吸附数据', `A${Math.max(3, baseline.main_rows - 7)}:H${baseline.main_rows}`);
  await preview('before_pending', '已登记待接受', `A${Math.max(5, baseline.pending_rows - 8)}:E${baseline.pending_rows}`);
  console.log(JSON.stringify({main_rows: baseline.main_rows, pending_rows: baseline.pending_rows, headers: baseline.headers}));
} else {
  const manifest = JSON.parse(await fs.readFile(path.join(out, 'publication_manifest.json'), 'utf8'));
  const finalReceipt = JSON.parse(await fs.readFile(path.join(out, manifest.accepted.at(-1).promotion_id + '.receipt.json'), 'utf8'));
  if (digest(original) !== finalReceipt.workbook_sha256_after) throw new Error('Workbook changed after controlled promotions');
  const receiptPath = path.join(out, 'view_receipt.json');
  try { await fs.access(receiptPath); throw new Error('View already saved; reconcile receipt'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (main.getUsedRange().rowCount !== manifest.main_rows_after || pending.getUsedRange().rowCount !== manifest.pending_rows_before) {
    throw new Error('Unexpected saved worksheet row counts');
  }
  for (const row of manifest.accepted) {
    const values = main.getRange(`E${row.row}:F${row.row}`).values[0];
    if (String(values[0]) !== row.job_id || values[1] !== row.toten_eV) throw new Error('Accepted numeric binding changed');
    main.getRange(`A${row.row}:H${row.row}`).format.rowHeight = 56;
    main.getRange(`A${row.row}:H${row.row}`).format.wrapText = true;
    main.getRange(`F${row.row}`).setNumberFormat('0.00000000');
  }
  for (let index = 0; index < manifest.pending_append.length; index++) {
    const row = manifest.pending_rows_before + index + 1;
    const target = pending.getRange(`A${row}:F${row}`);
    target.copyFrom(pending.getRange('A7:F7'), 'all');
    target.values = [manifest.pending_append[index]];
    target.format.rowHeight = 64;
    target.format.wrapText = true;
  }
  wb.recalculate();
  const errors = await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
    options: {useRegex: true, maxResults: 20}, maxChars: 1200});
  await fs.writeFile(path.join(out, 'artifact_error_scan.ndjson'), errors.ndjson, {flag: 'wx'});
  await preview('after_main', '最终吸附数据', `A${manifest.main_rows_before + 1}:H${manifest.main_rows_after}`);
  await preview('after_pending', '已登记待接受', `A${manifest.pending_rows_before + 1}:E${manifest.pending_rows_after}`);
  const temporary = path.join(out, 'metadata_view.pending.xlsx');
  await (await SpreadsheetFile.exportXlsx(wb)).save(temporary);
  if (!original.equals(await fs.readFile(request.workbook))) throw new Error('Concurrent workbook change; original not overwritten');
  await fs.copyFile(temporary, request.workbook);
  await fs.writeFile(receiptPath, JSON.stringify({workbook: request.workbook,
    workbook_sha256_before: digest(original), workbook_sha256_after: digest(await fs.readFile(request.workbook)),
    publication_manifest_sha256: digest(await fs.readFile(path.join(out, 'publication_manifest.json'))),
    accepted_main_rows: manifest.accepted.length, pending_metadata_rows_added: manifest.pending_append.length}, null, 2), {flag: 'wx'});
  console.log('SAVED controlled accepted rows and metadata-only pending view');
}
