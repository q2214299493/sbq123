import fs from "node:fs/promises";
import crypto from "node:crypto";
import {FileBlob,SpreadsheetFile} from "@oai/artifact-tool";

const out=process.argv[2];
const manifest=JSON.parse(await fs.readFile(`${out}/publication_manifest.json`,"utf8"));
const receiptPath=`${out}/view_receipt.json`;
try{await fs.access(receiptPath);throw new Error("View receipt exists; inspect before retry.");}
catch(error){if(error.code!=="ENOENT")throw error;}
const digest=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
const original=await fs.readFile(manifest.workbook);
const finalPromotion=JSON.parse(await fs.readFile(`${out}/${manifest.accepted.at(-1).promotion_id}.receipt.json`,"utf8"));
if(digest(original)!==finalPromotion.workbook_sha256_after)throw new Error("Workbook changed after final promotion.");
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(manifest.workbook));
const main=wb.worksheets.getItem("最终吸附数据");
const pending=wb.worksheets.getItem("已登记待接受");
if(main.getUsedRange().rowCount!==80||pending.getUsedRange().rowCount!==30)throw new Error("Sheet scope changed.");
for(const item of manifest.accepted){
  const values=main.getRange(`E${item.row}:F${item.row}`).values[0];
  if(String(values[0])!==item.job_id||values[1]!==item.toten_eV)throw new Error("Published job/energy mismatch.");
}
main.getRange("A76:H80").format.rowHeight=60;
main.getRange("A76:H80").format.wrapText=true;
main.getRange("F76:F80").setNumberFormat("0.00000000");
for(let i=0;i<manifest.pending_append.length;i++){
  const row=31+i,range=pending.getRange(`A${row}:F${row}`);
  range.copyFrom(pending.getRange("A30:F30"),"all");
  range.values=[manifest.pending_append[i]];
  range.format.rowHeight=84;
  range.format.wrapText=true;
}
wb.recalculate();
const errorScan=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:30},maxChars:1600});
await fs.writeFile(`${out}/after.error_scan.ndjson`,errorScan.ndjson);
for(const [label,sheetName,range] of [["main","最终吸附数据","A74:H80"],["pending","已登记待接受","A29:F35"]]){
  const preview=await wb.render({sheetName,range,scale:1.2,format:"png"});
  await fs.writeFile(`${out}/after.${label}.png`,new Uint8Array(await preview.arrayBuffer()));
}
const temporary=`${out}/metadata_view.pending.xlsx`;
await(await SpreadsheetFile.exportXlsx(wb)).save(temporary);
if(!original.equals(await fs.readFile(manifest.workbook)))throw new Error("Concurrent workbook change.");
await fs.copyFile(temporary,manifest.workbook);
await fs.writeFile(receiptPath,JSON.stringify({workbook:manifest.workbook,workbook_sha256_before:digest(original),
  workbook_sha256_after:digest(await fs.readFile(manifest.workbook)),publication_manifest_sha256:digest(await fs.readFile(`${out}/publication_manifest.json`)),
  accepted_rows:[76,77,78,79,80],pending_rows_added:5,existing_cells_outside_scope_intended_unchanged:true},null,2)+"\n");
console.log("SAVED_5_ACCEPTED_ROWS_AND_5_NONNUMERIC_STATUS_ROWS");
