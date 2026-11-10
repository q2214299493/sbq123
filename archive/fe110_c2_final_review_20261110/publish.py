"""Bind five accepted registry values to the existing thesis workbook gate."""
from pathlib import Path
import shutil
import json

from scripts.artifact_io import load_json_object,sha256_file,write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_excel_promotion import build_plan,apply_plan
from .collect import ROOT,OUT as SCIENCE
from .register import DB,REVIEWER

OUT=ROOT/"outputs/fe110_c2_completion_20261110_v1"
BOOK=ROOT/"outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx"
DEPS=Path("C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1104-2876-0_26.1104.2876.0_x64__3k8sg7r9htsxt/dependencies")
NODE=DEPS/"node/bin/node.exe"
MODULES=DEPS/"node/node_modules"
HEADERS=["吸附物","最终位点","吸附反应","吸附产物","任务号","F能量 (eV)","E0能量 (eV)","吸附能 Eads (eV)"]


def main():
    target=OUT/"publication_manifest.json"
    if target.exists():
        raise SystemExit("Publication manifest exists; inspect receipts before resuming.")
    baseline=load_json_object(OUT/"before.baseline.json")
    if baseline["sheets"][0]["rowCount"]!=75 or baseline["sheets"][1]["rowCount"]!=30 or baseline["sheets"][0]["headers"]!=HEADERS:
        raise ValueError("Unexpected reviewed workbook layout.")
    if (OUT/"before.xlsx").exists():
        raise ValueError("Workbook backup exists; reconcile before another write.")
    shutil.copyfile(BOOK,OUT/"before.xlsx")
    decisions=load_json_object(SCIENCE/"scientific_decisions.json")
    records={r["name"]:r for r in load_json_object(SCIENCE/"completion_geometry_review.json")["records"]}
    geometry={r["name"]:r for r in load_json_object(SCIENCE/"force_geometry_final_review.json")["records"]}
    selected={r["name"]:r for r in decisions["decisions"]}
    accepted=[]
    pending=[]
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for name in ("05_S2","07_S1","12_S1","13_S1","18_S2"):
            item=selected[name]
            cid=item["calculation_id"]
            result=db.execute("SELECT * FROM results WHERE calculation_id=? AND result_name='final_toten' AND validation_status='accepted_compatible_final_energy'",(cid,)).fetchall()
            if len(result)!=1 or db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?",(cid,)).fetchone()[0]!="accepted":
                raise ValueError("Accepted source missing.")
            labels=[]
            for atom in records[name]["measurements"]["nearest_Fe"]:
                if atom["atom"].startswith("H") or atom["neighbors"][0]["distance_A"]>2.35:continue
                index=atom["atom"][1:]
                projection=geometry[name]["projection_distances"][index]
                site=min(projection,key=projection.get)
                labels.append(atom["atom"]+"近"+site)
            site="；".join(labels)+"（邻域投影）"
            promotion="fe110-c2-supplement-20261110-"+name.lower().replace('_','-')
            request=OUT/(promotion+".request.json")
            reaction=item["target_graph"]+"*"
            note="缺兼容参考能"+("；LSF UNKNOWN（本批例外）" if item["queue_status"]=="UNKNOWN" else "")
            values=[item["formula"],site,"Fe(110) + "+item["target_graph"]+" -> "+reaction+"/Fe(110)",reaction+"/Fe(110)",records[name]["job_id"],None,"未登记",note]
            data={"schema_version":1,"promotion_id":promotion,"promotion_kind":"adsorption","registry_id":cid,
                "workbook":{"path":str(BOOK),"worksheet_name":"最终吸附数据","header_row":2,"headers":HEADERS},
                "columns":[{"header":header,"source":{"type":"result","result_id":result[0]["result_id"]} if i==5 else {"type":"reviewed_metadata","value":values[i]}} for i,header in enumerate(HEADERS)],
                "review":{"decision":"approve","reviewer":REVIEWER,"reviewed_at":decisions["reviewed_at"]},
                "receipt_path":str(OUT/(promotion+".receipt.json")),
                "notes":"Accepted compatible SIGMA0.20 final TOTEN; scheduler UNKNOWN exceptions explicit; no E0/Eads inferred."}
            write_json_exclusive(request,data)
            accepted.append({"name":name,"calculation_id":cid,"job_id":records[name]["job_id"],"toten_eV":records[name]["TOTEN_eV"],
                             "request":str(request),"promotion_id":promotion,"row":76+len(accepted)})
        for name in ("05_S1","11_S1","14_S1","06_S2","18_S1"):
            item=selected[name]
            reason=item["reason"]
            if item["duplicate_of"]:
                found=db.execute("SELECT row_number FROM excel_promotions WHERE registry_id=? ORDER BY created_at DESC LIMIT 1",(item["duplicate_of"],)).fetchone()
                reason="同态代表"+("见主表第"+str(found[0])+"行" if found else item["duplicate_of"])+"；不增加独立构型"
            status="重复来源（已审核）" if item["duplicate_of"] else "用户已停止；未接受" if name=="06_S2" else "未收敛；脱氢候选"
            pending.append([name,item["target_graph"]+"*",records[name]["job_id"],status,reason,item["calculation_id"]])
    write_json_exclusive(target,{"workbook":str(BOOK),"accepted":accepted,"pending_append":pending,"main_rows_before":75,"main_rows_after":80,
        "pending_rows_before":30,"pending_rows_after":35,"workbook_sha256_before":sha256_file(BOOK),
        "scientific_registry_receipt_sha256":sha256_file(SCIENCE/"registry_receipt.json")})
    print("PREPARED_5_EXACT_PROMOTIONS_AND_5_METADATA_ROWS",flush=True)
    for item in accepted:
        path=OUT/(item["promotion_id"]+".plan.json")
        plan=build_plan(Path(item["request"]),DB)
        if plan["row_values"][5]!=item["toten_eV"] or plan["registry_id"]!=item["calculation_id"]:
            raise ValueError("Resolved source mismatch.")
        write_json_exclusive(path,plan)
        receipt=apply_plan(path,database=DB,node=NODE,node_modules=MODULES)
        if receipt["excel_row_number"]!=item["row"]:
            raise ValueError("Publication row differs; inspect actual receipt before any retry.")
        print("PROMOTED",item["name"],item["row"],flush=True)


if __name__=="__main__":
    main()
