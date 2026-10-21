"""Read back the exact applied batch, verify old history and test exact retry idempotency."""
import json

from archive.fe110_coads_registry_20261021.collect import OUT
from archive.fe110_coads_registry_20261021.prepare import CHILD, DB
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_write import apply_registry_batch


def main():
    batch, plan, approval, receipt = [load_json_object(OUT / (name + ".json")) for name in
                                     ("registry_batch", "registry_plan", "registry_approval", "registry_receipt")]
    if (receipt["plan_sha256"] != plan["plan_sha256"]
            or (receipt["inserted"], receipt["updated"]) != (59, 5)):
        raise ValueError("unexpected apply receipt")
    records = []
    with open_registry(DB) as connection:
        for table, entries in batch["rows"].items():
            key = connection.execute("PRAGMA table_info(" + table + ")").fetchall()
            primary = [row["name"] for row in key if row["pk"]]
            for row in entries:
                expected = dict(row)
                if table == "calculations":
                    for change in batch["workflow_status_changes"]:
                        if change["calculation_id"] == row["calculation_id"]:
                            expected["workflow_status"] = change["new_workflow_status"]
                where = " AND ".join(name + "=?" for name in primary)
                stored = connection.execute("SELECT * FROM " + table + " WHERE " + where,
                                            tuple(row[name] for name in primary)).fetchone()
                if stored is None or any(stored[name] != value for name, value in expected.items()):
                    raise ValueError("readback mismatch:" + table)
        for change in batch["workflow_status_changes"]:
            cid = change["calculation_id"]
            if any(r["calculation_id"] == cid for r in records):
                continue
            status = connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (cid,)).fetchone()[0]
            results = [dict(r) for r in connection.execute(
                "SELECT result_name,numeric_value,text_value,validation_status FROM results WHERE calculation_id=?", (cid,))]
            records.append({"calculation_id": cid, "workflow_status": status, "results": results})
        parent = connection.execute("SELECT parent_calculation_id FROM calculations WHERE calculation_id=?", (CHILD,)).fetchone()[0]
        if connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (parent,)).fetchone()[0] != "rejected":
            raise ValueError("original intact-target rejection was not preserved")
        if connection.execute("SELECT count(*) FROM results WHERE calculation_id=?", (parent,)).fetchone()[0] != 0:
            raise ValueError("do not accept reclassified energy under the rejected original identity")
        accepted03 = connection.execute("SELECT count(*) FROM results WHERE calculation_id=? AND validation_status LIKE ?",
                                       (CHILD, "accepted%" )).fetchone()[0]
        if accepted03 != 1:
            raise ValueError("one accepted final energy expected for the reclassified state")
        old_counts = [dict(r) for r in connection.execute(
            "SELECT workflow_status,count(*) AS count FROM calculations WHERE calculation_id LIKE ? AND calculation_id<>? GROUP BY workflow_status",
            ("fe110_five_c2_adsorption_20261006_%", CHILD))]
        check = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_keys = [list(r) for r in connection.execute("PRAGMA foreign_key_check")]
        if check != "ok" or foreign_keys:
            raise ValueError("database integrity check failed")
    retry = apply_registry_batch(DB, batch, confirmed_sha256=plan["plan_sha256"], plan=plan, approval=approval)
    if not retry["already_applied"]:
        raise ValueError("exact retry was not idempotent")
    write_json_exclusive(OUT / "idempotency_receipt.json", retry)
    write_json_exclusive(OUT / "post_apply_verification.json", {"records": records,
        "original01_05_workflow_counts": old_counts, "reclassified03_parent_rejection_preserved": True,
        "quick_check": check, "foreign_key_check": foreign_keys, "exact_retry_already_applied": True,
        "receipt_sha256": sha256_file(OUT / "registry_receipt.json"), "new_scientific_jobs": 0})
    print(json.dumps({"registered_states": len(records), "inserted_rows": receipt["inserted"],
                      "accepted_new_final_energies": accepted03, "quick_check": check,
                      "foreign_keys": len(foreign_keys), "idempotent": True, "old_counts": old_counts}))


if __name__ == "__main__":
    main()
