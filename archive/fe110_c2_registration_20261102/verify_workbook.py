"""Independent saved-XLSX readback with bundled Python/openpyxl; never author."""
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook

from archive.fe110_adsorption_acceptance_20261029.verify_workbook import check_preserved_sheet

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/fe110_c2_registration_20261102_v1"


def main():
    manifest = json.loads((OUT / "publication_manifest.json").read_text(encoding="utf-8"))
    before = load_workbook(OUT / "before.xlsx")
    after = load_workbook(manifest["workbook"])
    errors = []
    if before.sheetnames != after.sheetnames:
        errors.append("sheet names/order changed")
    for name, count, columns in (("最终吸附数据", manifest["main_rows_before"], "ABCDEFGH"),
                                 ("已登记待接受", manifest["pending_rows_before"], "ABCDEF")):
        errors.extend(check_preserved_sheet(before[name], after[name], count, columns, set()))
        if before[name].auto_filter.ref != after[name].auto_filter.ref:
            errors.append("existing filter changed: " + name)
        if set(before[name].tables) != set(after[name].tables):
            errors.append("existing table identities changed: " + name)
    sheet = after["最终吸附数据"]
    if sheet.max_row != manifest["main_rows_after"]:
        errors.append("main row count differs")
    for item in manifest["accepted"]:
        request = json.loads(Path(item["request"]).read_text(encoding="utf-8"))
        expected = [item["toten_eV"] if column["source"]["type"] == "result" else column["source"]["value"]
                    for column in request["columns"]]
        actual = [sheet.cell(item["row"], col).value for col in range(1, 9)]
        if actual != expected or sheet.cell(item["row"], 6).data_type != "n":
            errors.append("numeric/metadata/source mismatch: " + item["name"])
        receipt = json.loads((OUT / (item["promotion_id"] + ".receipt.json")).read_text(encoding="utf-8"))
        if receipt["registry_id"] != item["calculation_id"] or receipt["excel_row_number"] != item["row"]:
            errors.append("promotion receipt mismatch: " + item["name"])
        if isinstance(sheet.cell(item["row"], 8).value, (int, float)):
            errors.append("unaccepted adsorption energy was published")
    pending = after["已登记待接受"]
    if pending.max_row != manifest["pending_rows_after"]:
        errors.append("pending row count differs")
    for index, expected in enumerate(manifest["pending_append"]):
        row = manifest["pending_rows_before"] + index + 1
        if [pending.cell(row, col).value for col in range(1, 7)] != expected:
            errors.append("pending metadata mismatch at row " + str(row))
    if any(cell.data_type == "e" for ws in after for row in ws for cell in row):
        errors.append("saved workbook contains an Excel error cell")
    result = {"status": "PASS" if not errors else "FAIL", "errors": errors[:30],
        "original_main_rows_preserved": manifest["main_rows_before"],
        "original_pending_rows_preserved": manifest["pending_rows_before"],
        "original_values_styles_dimensions_merges_freeze_preserved": not errors,
        "accepted_numeric_rows_verified": len(manifest["accepted"]),
        "pending_metadata_rows_added": len(manifest["pending_append"]),
        "main_rows": sheet.max_row, "pending_rows": pending.max_row,
        "existing_filter_refs": {ws.title: ws.auto_filter.ref for ws in before},
        "workbook_sha256": hashlib.sha256(Path(manifest["workbook"]).read_bytes()).hexdigest(),
        "native_Excel_runtime_tested": False}
    target = OUT / "workbook_verification.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2)
    print(json.dumps(result, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
