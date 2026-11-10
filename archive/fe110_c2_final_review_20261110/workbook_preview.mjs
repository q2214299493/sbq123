import fs from "node:fs/promises";
import {FileBlob, SpreadsheetFile} from "@oai/artifact-tool";

const book=process.argv[2], out=process.argv[3], tag=process.argv[4];
const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(book));
const summary=await workbook.inspect({kind:"sheet",include:"id,name",maxChars:2000});
await fs.mkdir(out,{recursive:true});
await fs.writeFile(`${out}/${tag}.sheets.ndjson`,summary.ndjson);
const records=[];
for(const name of ["最终吸附数据","已登记待接受"]){
  const sheet=workbook.worksheets.getItem(name);
  const used=sheet.getUsedRange();
  const columns=name==="最终吸附数据"?"H":"F";
  const row=used.rowCount;
  const range=`A${Math.max(1,row-7)}:${columns}${row}`;
  const preview=await workbook.render({sheetName:name,range,scale:1.3,format:"png"});
  await fs.writeFile(`${out}/${tag}.${name}.png`,new Uint8Array(await preview.arrayBuffer()));
  records.push({name,rowCount:row,columnCount:used.columnCount,headers:sheet.getRange(`A2:${columns}2`).values[0],lastRows:sheet.getRange(range).values});
}
await fs.writeFile(`${out}/${tag}.baseline.json`,JSON.stringify({book,sheets:records},null,2)+"\n");
console.log(JSON.stringify(records.map(({name,rowCount,columnCount,headers})=>({name,rowCount,columnCount,headers}))));
