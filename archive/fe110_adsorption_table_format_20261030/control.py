"""Back up, verify and atomically publish a presentation-only workbook edit."""
import argparse
from copy import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
BOOK = ROOT / "outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx"
OUT = ROOT / "outputs/adsorption_table_format_20261030_v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def prepare():
    with BOOK.open("r+b"):
        pass
    OUT.mkdir(exist_ok=False)
    shutil.copyfile(BOOK, OUT / "before.xlsx")
    sheet = load_workbook(OUT / "before.xlsx")["最终吸附数据"]
    placeholders = []
    for row in sheet.iter_rows(min_row=3, min_col=6, max_col=8):
        for cell in row:
            if isinstance(cell.value, str) and cell.data_type != "f":
                if cell.value not in {"未登记", "缺兼容参考能"}:
                    raise ValueError("Preserve unexpected energy-column text: " + cell.coordinate)
                placeholders.append({"cell": cell.coordinate, "before": cell.value})
    save_json(OUT / "manifest.json", {"workbook": str(BOOK), "before_sha256": digest(BOOK),
        "rows": sheet.max_row, "clear_placeholders": placeholders,
        "scope": "User-authorized uniform presentation and empty missing-energy cells; all existing numeric values preserved."})
    print("PREPARED", len(placeholders), "text placeholders; numeric values are read-only")


def verify_pending(first, second):
    for row in first:
        for cell in row:
            other = second[cell.coordinate]
            assert cell.number_format == other.number_format
            for field in ("font", "fill", "border", "alignment", "protection"):
                assert copy(getattr(cell, field)) == copy(getattr(other, field)), cell.coordinate
    assert [(r, d.height) for r, d in first.row_dimensions.items()] == [(r, d.height) for r, d in second.row_dimensions.items()]
    assert [(c, d.width) for c, d in first.column_dimensions.items()] == [(c, d.width) for c, d in second.column_dimensions.items()]


def verify():
    spec = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    before, after = [load_workbook(OUT / name) for name in ("before.xlsx", "formatted.final.xlsx")]
    assert before.sheetnames == after.sheetnames
    cleared = {x["cell"] for x in spec["clear_placeholders"]}
    numeric_count = 0
    for name in before.sheetnames:
        first, second = before[name], after[name]
        assert (first.max_row, first.max_column) == (second.max_row, second.max_column)
        assert first.freeze_panes == second.freeze_panes
        assert set(map(str, first.merged_cells.ranges)) == set(map(str, second.merged_cells.ranges))
        for row in first:
            for cell in row:
                other = second[cell.coordinate]
                expected = None if name == "最终吸附数据" and cell.coordinate in cleared else cell.value
                assert other.value == expected, (name, cell.coordinate)
                if cell.value is not None and not (name == "最终吸附数据" and cell.coordinate in cleared):
                    assert other.data_type == cell.data_type, (name, cell.coordinate, "type")
                numeric_count += isinstance(cell.value, (int, float))
        if name != "最终吸附数据":
            verify_pending(first, second)
    sheet = after["最终吸附数据"]
    for row in sheet.iter_rows(min_row=3, max_col=8):
        for cell in row:
            expected_fill = "FFB7DEE8" if cell.row % 2 else "FFFFFFFF"
            assert cell.fill.fgColor.rgb == expected_fill, cell.coordinate
            assert cell.font.name == "Arial" and cell.font.sz == 11 and cell.alignment.vertical == "center"
        assert sheet.row_dimensions[row[0].row].height == 42
    for row in sheet.iter_rows(min_row=3, min_col=6, max_col=8):
        for cell in row:
            assert cell.value is None or isinstance(cell.value, (int, float)) or cell.data_type == "f"
    result = {"status": "PASS", "all_existing_values_types_formulas_preserved_except_placeholders": True,
        "numeric_cells_preserved": numeric_count, "placeholders_cleared": len(cleared),
        "uniform_body_rows": sheet.max_row - 2, "pending_sheet_preserved": True,
        "before_sha256": spec["before_sha256"], "after_sha256": digest(OUT / "formatted.final.xlsx")}
    save_json(OUT / "verification.final.json", result)
    print(json.dumps(result, ensure_ascii=True))


def publish():
    spec = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    verification = json.loads((OUT / "verification.final.json").read_text(encoding="utf-8"))
    assert verification["status"] == "PASS" and digest(BOOK) == spec["before_sha256"]
    staged = OUT / "formatted.final.xlsx"
    assert digest(staged) == verification["after_sha256"]
    temporary = BOOK.with_name(BOOK.name + ".format-v1.tmp")
    temporary.resolve().relative_to(ROOT)
    if temporary.exists():
        raise FileExistsError(temporary)
    shutil.copyfile(staged, temporary)
    if digest(BOOK) != spec["before_sha256"]:
        raise ValueError("Concurrent workbook edit; preserve both versions")
    os.replace(temporary, BOOK)
    assert digest(BOOK) == verification["after_sha256"]
    save_json(OUT / "publication_receipt.json", {"workbook": str(BOOK), "before_sha256": spec["before_sha256"],
        "after_sha256": digest(BOOK), "placeholder_cells_cleared": sorted(x["cell"] for x in spec["clear_placeholders"]),
        "scientific_numeric_values_changed": 0, "registry_records_changed": 0})
    print("PUBLISHED uniform table; missing energy cells empty; existing numbers preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify", "publish"))
    args = parser.parse_args()
    {"prepare": prepare, "verify": verify, "publish": publish}[args.phase]()
