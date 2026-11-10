"""Independent read-only workbook and registry readback after the approved closeout."""
from copy import copy
from pathlib import Path
import json

from openpyxl import load_workbook

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/fe110_c2_completion_20261110_v1"
SCIENCE = ROOT / "calculations/fe110_c2_site_supplement_20261106/final_review_20261110_v1"


def main():
    publication = load_json_object(OUT / "publication_manifest.json")
    view = load_json_object(OUT / "view_receipt.json")
    book = Path(publication["workbook"])
    if sha256_file(book) != view["workbook_sha256_after"]:
        raise ValueError("Saved workbook changed after the reviewed export.")
    before = load_workbook(OUT / "before.xlsx", data_only=False)
    after = load_workbook(book, data_only=False)
    if before.sheetnames != after.sheetnames:
        raise ValueError("Workbook sheets changed.")
    differences = []
    style_differences = []
    layout_differences = []
    checked = 0
    for old in before:
        new = after[old.title]
        for row in old:
            for cell in row:
                target = new[cell.coordinate]
                checked += 1
                if (cell.value, cell.data_type) != (target.value, target.data_type):
                    differences.append([old.title, cell.coordinate])
                if any(copy(getattr(cell, key)) != copy(getattr(target, key)) for key in
                       ("font", "fill", "border", "alignment", "number_format", "protection")):
                    style_differences.append([old.title, cell.coordinate])
        for key in ("freeze_panes", "sheet_state"):
            if getattr(old, key) != getattr(new, key):
                layout_differences.append([old.title, key])
        if str(old.merged_cells) != str(new.merged_cells):
            layout_differences.append([old.title, "merged_cells"])
        if old.auto_filter != new.auto_filter:
            layout_differences.append([old.title, "auto_filter"])
        for key, dimension in old.column_dimensions.items():
            if dimension.width != new.column_dimensions[key].width:
                layout_differences.append([old.title, "column_width", key])
        for key, dimension in old.row_dimensions.items():
            if dimension.height != new.row_dimensions[key].height:
                layout_differences.append([old.title, "row_height", key])
        if list(old.tables) != list(new.tables):
            layout_differences.append([old.title, "tables"])
    if differences:
        raise ValueError("Pre-existing cell values/formulas changed: " + repr(differences[:10]))
    main_sheet = after["最终吸附数据"]
    pending = after["已登记待接受"]
    if main_sheet.max_row != 80 or pending.max_row != 35:
        raise ValueError("Unexpected final row counts.")
    accepted_ids = set()
    for item in publication["accepted"]:
        row = item["row"]
        if str(main_sheet.cell(row, 5).value) != str(item["job_id"]):
            raise ValueError("Workbook job identity differs.")
        if main_sheet.cell(row, 6).value != item["toten_eV"]:
            raise ValueError("Workbook accepted TOTEN differs.")
        if "缺兼容参考能" not in main_sheet.cell(row, 8).value:
            raise ValueError("Uncomputed Eads not explicitly identified.")
        accepted_ids.add(item["calculation_id"])
        receipt = load_json_object(OUT / (item["promotion_id"] + ".receipt.json"))
        if receipt["excel_row_number"] != row:
            raise ValueError("Workbook promotion receipt differs.")
    for i, expected in enumerate(publication["pending_append"], 31):
        if [pending.cell(i, c).value for c in range(1, 7)] != expected:
            raise ValueError("Non-numeric pending status rows differ.")
    batch = load_json_object(SCIENCE / "registry_batch.json")
    count = 0
    with open_registry(ROOT / "data/project_registry.sqlite3") as db:
        db.execute("PRAGMA query_only=ON")
        for table, rows in batch["rows"].items():
            columns = {row[1]: row for row in db.execute('PRAGMA table_info("' + table + '")')}
            for row in rows:
                if not set(row) <= columns.keys():
                    raise ValueError("Unknown batch fields.")
                names = list(row)
                found = db.execute('SELECT COUNT(*) FROM "' + table + '" WHERE ' +
                    ' AND '.join('"' + key + '" IS ?' for key in names), tuple(row[key] for key in names)).fetchone()[0]
                if found != 1:
                    raise ValueError("Registry scientific readback differs: " + table)
                count += 1
        for item in load_json_object(SCIENCE / "scientific_decisions.json")["decisions"]:
            status = db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (item["calculation_id"],)).fetchone()[0]
            expected = "accepted" if item["calculation_id"] in accepted_ids else "duplicate" if item["duplicate_of"] else "failed" if item["name"] == "06_S2" else "needs_review"
            if status != expected:
                raise ValueError("Workflow readback differs: " + item["name"])
        for item in publication["accepted"]:
            saved = db.execute("SELECT registry_id, row_number FROM excel_promotions WHERE promotion_id=?", (item["promotion_id"],)).fetchone()
            if saved is None or tuple(saved) != (item["calculation_id"], item["row"]):
                raise ValueError("Excel promotion registry evidence differs.")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Registry integrity check failed.")
    result = {"status": "PASS" if not style_differences and not layout_differences else "REVIEW",
        "preexisting_cells_values_formulas_checked": checked, "value_differences": differences,
        "preexisting_style_differences": style_differences, "layout_differences": layout_differences,
        "registry_scientific_rows_read_back": count, "accepted_TOTEN_rows": 5,
        "pending_metadata_rows": 5, "numeric_Eads_added": 0, "workbook_sha256": sha256_file(book)}
    write_json_exclusive(OUT / "verification.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
