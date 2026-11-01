"""Prepare explicit Excel bindings and use the canonical per-row promotion gate."""
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_excel_promotion import build_plan, apply_plan

from .prepare import ACCEPT, BOOK, DB, DUPLICATES, MISSING, OUT, REVIEWER

NODE = Path("C:/Users/86177/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
MODULES = Path("C:/Users/86177/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules")
HEADERS = ["吸附物", "最终位点", "吸附反应", "吸附产物", "任务号", "F能量 (eV)", "E0能量 (eV)", "吸附能 Eads (eV)"]


def prepare():
    target = OUT / "publication_manifest.json"
    if target.exists():
        raise FileExistsError(target)
    baseline = load_json_object(OUT / "workbook_baseline.json")
    initial = load_json_object(OUT / "request.json")
    if sha256_file(BOOK) != initial["workbook_sha256_before"] or baseline["headers"] != HEADERS:
        raise ValueError("saved workbook baseline/header changed")
    decisions = load_json_object(OUT / "decisions.json")
    rows = {r["name"]: r for r in load_json_object(OUT / "analysis.json")["records"]}
    accepted = []
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for index, name in enumerate(ACCEPT):
            row = rows[name]
            cid = row["calculation_id"]
            calc = db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (cid,)).fetchone()
            results = db.execute("SELECT * FROM results WHERE calculation_id=? AND result_name='final_toten' AND validation_status='accepted_compatible_final_energy'", (cid,)).fetchall()
            if calc[0] != "accepted" or len(results) != 1 or results[0]["numeric_value"] != row["toten_eV"]:
                raise ValueError("accepted registry binding missing: " + name)
            if db.execute("SELECT 1 FROM excel_promotions WHERE registry_id=?", (cid,)).fetchone():
                raise ValueError("already published; inspect the existing receipt")
            identity = row["target_graph"] + "*"
            labels = [row["formula"], decisions["decisions"][name]["final_site"],
                "Fe(110) + " + row["target_graph"] + " -> " + identity + "/Fe(110)",
                identity + "/Fe(110)", row["job_id"], None, "未登记", "缺兼容参考能"]
            promotion_id = "fe110-c2-11-15-table-20261102-" + name.lower().replace("_", "-")
            request_path = OUT / (promotion_id + ".request.json")
            request = {"schema_version": 1, "promotion_id": promotion_id, "promotion_kind": "adsorption", "registry_id": cid,
                "workbook": {"path": str(BOOK), "worksheet_name": "最终吸附数据", "header_row": 2, "headers": HEADERS},
                "columns": [{"header": header, "source": {"type": "result", "result_id": results[0]["result_id"]}
                    if i == 5 else {"type": "reviewed_metadata", "value": labels[i]}} for i, header in enumerate(HEADERS)],
                "review": {"decision": "approve", "reviewer": REVIEWER, "reviewed_at": decisions["reviewed_at"]},
                "receipt_path": str(OUT / (promotion_id + ".receipt.json")),
                "notes": "Accepted final OUTCAR TOTEN, SIGMA0.20 only; no E0/Eads inference or duplicate result."}
            write_json_exclusive(request_path, request)
            accepted.append({"name": name, "calculation_id": cid, "job_id": row["job_id"],
                "result_id": results[0]["result_id"], "toten_eV": row["toten_eV"],
                "row": baseline["main_rows"] + index + 1, "request": str(request_path), "promotion_id": promotion_id})
    targets = {r["name"]: r for r in accepted}
    pending = []
    for name in [r["name"] for r in load_json_object(OUT / "analysis.json")["records"] if r["name"] not in ACCEPT]:
        row = rows[name]
        if name in DUPLICATES:
            representative = targets[DUPLICATES[name]]
            status, reason = "重复来源（已审核）", f"同态代表见主表第{representative['row']}行；不增加独立构型"
        elif name in MISSING:
            status, reason = "待正式接受", "缺历史LSF DONE证据；计算收敛与调度UNKNOWN分别保留"
        elif name == "13_A":
            status, reason = "未达到力阈值", "300步力未收敛；几何被13_B覆盖，保留记录，不续算"
        else:
            raise ValueError("unreviewed pending identity")
        pending.append([name, row["target_graph"] + "*", row["job_id"], status, reason, row["calculation_id"]])
    write_json_exclusive(target, {"workbook": str(BOOK), "accepted": accepted, "pending_append": pending,
        "main_rows_before": baseline["main_rows"], "main_rows_after": baseline["main_rows"] + len(accepted),
        "pending_rows_before": baseline["pending_rows"], "pending_rows_after": baseline["pending_rows"] + len(pending),
        "baseline_sha256": sha256_file(OUT / "workbook_baseline.json"), "registry_receipt_sha256": sha256_file(OUT / "registry_receipt.json"),
        "decisions_sha256": sha256_file(OUT / "decisions.json")})
    print("PREPARED 8 exact accepted-result Excel requests;7 metadata-only rows")


def promote():
    manifest = load_json_object(OUT / "publication_manifest.json")
    for row in manifest["accepted"]:
        receipt_path = OUT / (row["promotion_id"] + ".receipt.json")
        if receipt_path.exists():
            receipt = load_json_object(receipt_path)
            if receipt["registry_id"] != row["calculation_id"] or receipt["excel_row_number"] != row["row"]:
                raise ValueError("existing receipt requires reconciliation")
            with open_registry(DB) as db:
                db.execute("PRAGMA query_only=ON")
                saved = db.execute("SELECT registry_id,row_number FROM excel_promotions WHERE promotion_id=?", (row["promotion_id"],)).fetchone()
                if saved is None or tuple(saved) != (row["calculation_id"], row["row"]):
                    raise ValueError("saved receipt/database disagree; no repeat publication")
            print("ALREADY_RECEIPTED", row["name"], flush=True)
            continue
        plan_path = OUT / (row["promotion_id"] + ".plan.json")
        if plan_path.exists():
            raise FileExistsError("prior plan without receipt: inspect actual workbook/registry before resuming")
        plan = build_plan(Path(row["request"]), DB)
        if plan["row_values"][5] != row["toten_eV"] or plan["registry_id"] != row["calculation_id"]:
            raise ValueError("resolved numeric/identity binding differs")
        write_json_exclusive(plan_path, plan)
        receipt = apply_plan(plan_path, database=DB, node=NODE, node_modules=MODULES)
        if receipt["excel_row_number"] != row["row"]:
            raise ValueError("promotion succeeded at unexpected row; inspect receipt before continuing")
        print("PROMOTED", row["name"], "row", receipt["excel_row_number"], flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "promote"))
    args = parser.parse_args()
    {"prepare": prepare, "promote": promote}[args.phase]()
