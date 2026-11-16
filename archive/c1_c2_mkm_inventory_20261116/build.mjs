import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile, FileBlob } from '@oai/artifact-tool';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const output=path.join(root,'outputs/c1_c2_mkm_inventory_20261116');
const data=JSON.parse(await fs.readFile(path.join(output,'inventory.json'),'utf8'));
const wb=Workbook.create();
const main=wb.worksheets.add('反应与缺口');
const energy=wb.worksheets.add('已登记电子能垒');
main.tabColor='#263D55';
for(const s of [main,energy]) s.showGridLines=false;

main.getRange('A2').values=[['Fe(110) C₁至C₂反应与数据缺口']];
main.getRange('A3').values=[['2026-11-16　网络审核草案。化学变化不代表位点化学计量已批准；不用于直接运行MKM。']];
main.getRange('A4').values=[['首版：CH＋CO局部可逆转化。先研究瞬态或给定活度响应，不假设人为产物汇，不报告整体稳态TOF。']];
const heads=['编号','模型范围','化学变化示意','选用结构与作业','已有证据','正向电子能垒 / eV','缺失参数','下一步'];
main.getRange('A6:H6').values=[heads];
const rows=data.rows.map(r=>[r.step_id,r.scope,r.chemical_change,r.selected_structures,r.evidence,null,r.missing_parameters,r.next_action]);
main.getRange(`A7:H${6+rows.length}`).values=rows;
const byId=new Map(data.registered_barriers.map((r,i)=>[r.barrier_set_id,i+5]));
for(let i=0;i<data.rows.length;i++){
  const record=data.rows[i];
  if(record.barrier_set_id) main.getRange(`F${i+7}`).formulas=[[`='已登记电子能垒'!D${byId.get(record.barrier_set_id)}`]];
}
main.getRange('A2:H20').format.font={name:'Arial',size:11,color:'#172B3A'};
main.getRange('A2').format.font={size:16,bold:true};
main.getRange('A3:A4').format.font={size:10,color:'#5A6875'};
main.getRange('A6:H6').format={fill:'#263D55',font:{name:'Arial',size:11,color:'#FFFFFF',bold:true},horizontalAlignment:'center',verticalAlignment:'center',wrapText:true};
main.getRange('A7:H20').format.wrapText=true;
main.getRange('A7:H20').format.verticalAlignment='top';
main.getRange('A6:H6').format.rowHeight=32;
main.getRange('A7:H20').format.rowHeight=42;
for(const [col,width] of [['A',8],['B',13],['C',34],['D',43],['E',34],['F',17],['G',48],['H',47]]) main.getRange(`${col}6:${col}20`).format.columnWidth=width;
main.getRange('F7:F20').setNumberFormat('0.000000');
main.getRange('F7:F20').format.horizontalAlignment='right';
main.getRange('A7:H20').conditionalFormats.add('expression',{formula:'MOD(ROW(),2)=0',format:{fill:'#F1F5F8'}});
main.freezePanes.freezeRows(6);
main.freezePanes.freezeColumns(2);
main.getRange('A23').values=[['共同缺口：物种/位点占用、A/最低参考态及共吸附反应池对齐、一致局部活性集热校正、T/p/初始覆盖度。']];
main.getRange('A24').values=[['缺失数值保留空白，不按零处理。电子能垒仅供探索；整体TOF、产物选择性和C₃至C₆链增长不在首版范围。']];
main.getRange('A25').values=[['优先事项：核对R05和R07已有TOTEN链；核验L01状态连接与R06后续归档；随后再列最少补算清单。']];

energy.getRange('A2').values=[['已登记电子能垒来源']];
energy.getRange('A3').values=[['来源：project_registry.sqlite3 的 accepted ts_barriers。仅电子能，非自由能；未登记步骤不填预测值。']];
energy.getRange('A4:H4').values=[['反应标识','IS结果ID','TS结果ID','正向 / eV','反向 / eV','反应能 / eV','FS结果ID','能量约定']];
energy.getRange(`A5:H${4+data.registered_barriers.length}`).values=data.registered_barriers.map(r=>[r.reaction_id,r.initial_result_id,r.ts_result_id,r.forward_barrier_ev,r.reverse_barrier_ev,r.reaction_energy_ev,r.final_result_id,r.energy_convention]);
energy.getRange('A2:H8').format.font={name:'Arial',size:11,color:'#172B3A'};
energy.getRange('A2').format.font={size:16,bold:true};
energy.getRange('A4:H4').format={fill:'#263D55',font:{name:'Arial',size:11,color:'#FFFFFF',bold:true},horizontalAlignment:'center',wrapText:true};
energy.getRange('A4:H4').format.rowHeight=32;
energy.getRange('A5:H8').format.rowHeight=48;
energy.getRange('A5:H8').format.wrapText=true;
energy.getRange('A5:H8').format.verticalAlignment='top';
for(const col of ['A','B','C','G']) energy.getRange(`${col}4:${col}8`).format.columnWidth=48;
for(const col of ['D','E','F']) energy.getRange(`${col}4:${col}8`).format.columnWidth=16;
energy.getRange('H4:H8').format.columnWidth=39;
energy.getRange('D5:F8').setNumberFormat('0.000000');
energy.getRange('D5:F8').format.horizontalAlignment='right';
wb.recalculate();
const keys=await wb.inspect({kind:'region',sheetId:main.name,range:'E9:F16',maxChars:1800,tableMaxRows:8,tableMaxCols:2});
console.log(keys.ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:500});
console.log(errors.ndjson);
for(const [sheetName,range,name] of [[main.name,'A1:H25','review'],[energy.name,'A1:H8','energy']]){
 const image=await wb.render({sheetName,range,scale:1,format:'png'});
 await fs.writeFile(path.join(output,`${name}.png`),new Uint8Array(await image.arrayBuffer()));
}
const destination=path.join(output,'C1-C2微观动力学反应与缺口.xlsx');
await (await SpreadsheetFile.exportXlsx(wb)).save(destination);
const saved=await SpreadsheetFile.importXlsx(await FileBlob.load(destination));
saved.recalculate();
const check=saved.worksheets.getItem(main.name);
for(const [cell,expected] of [['F9',data.rows[2].forward_electronic_barrier_ev],['F10',data.rows[3].forward_electronic_barrier_ev],['F15',data.rows[8].forward_electronic_barrier_ev],['F16',data.rows[9].forward_electronic_barrier_ev]]){
 const actual=check.getRange(cell).values[0][0];
 if(typeof actual!=='number'||Math.abs(actual-expected)>1e-12) throw new Error(`Saved value mismatch ${cell}`);
}
for(const cell of ['F11','F14']) if(check.getRange(cell).values[0][0]!==null) throw new Error(`Missing value replaced at ${cell}`);
await fs.writeFile(path.join(output,'workbook_verification.json'),JSON.stringify({status:'PASS',sheet_count:2,review_rows:14,accepted_barriers:4,saved_cross_sheet_values_verified:4,missing_barrier_blanks_verified:2,native_Excel_not_run:true}),{flag:'wx'});
console.log(destination);
