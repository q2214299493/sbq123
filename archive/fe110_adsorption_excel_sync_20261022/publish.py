"""Apply only the nine reviewed accepted-result requests through the existing Excel gate."""
from pathlib import Path

from archive.fe110_adsorption_excel_sync_20261022.prepare import DB, OUT
from scripts.artifact_io import canonical_json, load_json_object, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_excel_promotion import apply_plan, build_plan

RUNTIME = Path("C:/Users/86177/.cache/codex-runtimes/codex-primary-runtime/dependencies/node")


def main():
    manifest = load_json_object(OUT / "sync_manifest.json")
    for item in manifest["accepted"]:
        request_path = Path(item["request"])
        request = load_json_object(request_path)
        receipt_path = Path(request["receipt_path"])
        if receipt_path.exists():
            receipt = load_json_object(receipt_path)
            with open_registry(DB) as connection:
                registered = connection.execute("SELECT registry_id FROM excel_promotions WHERE promotion_id=?",
                                                (receipt["promotion_id"],)).fetchone()
            if registered is None or registered[0] != item["calculation_id"]:
                raise ValueError("existing receipt requires reconciliation")
            print("REUSED", item["name"], flush=True)
            continue
        plan = build_plan(request_path, DB)
        if (plan["registry_id"] != item["calculation_id"] or plan["row_values"][5] != item["toten_eV"]
                or plan["source_bindings"][5]["result_id"] != item["accepted_result_id"]):
            raise ValueError("approved identity/value binding changed")
        plan_path = OUT / (request["promotion_id"] + ".plan.json")
        if plan_path.exists():
            if canonical_json(load_json_object(plan_path)) != canonical_json(plan):
                raise ValueError("saved plan is stale; do not silently replace")
        else:
            write_json_exclusive(plan_path, plan)
        receipt = apply_plan(plan_path, database=DB, node=RUNTIME / "bin/node.exe",
                             node_modules=RUNTIME / "node_modules")
        print("PUBLISHED", item["name"], "ROW", receipt["excel_row_number"], flush=True)


if __name__ == "__main__":
    main()
