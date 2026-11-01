from pathlib import Path
from unittest.mock import MagicMock

from archive.fe110_c2_registration_20261102 import publish
from scripts.artifact_io import write_json_exclusive


def example(tmp_path):
    row = {"name": "test", "promotion_id": "one", "calculation_id": "test_cid", "row": 68,
           "toten_eV": -1.25, "request": str(tmp_path / "request.json")}
    write_json_exclusive(tmp_path / "publication_manifest.json", {"accepted": [row]})
    return row


def test_promotion_uses_canonical_excel_row_key(tmp_path, monkeypatch):
    row = example(tmp_path)
    monkeypatch.setattr(publish, "OUT", tmp_path)
    monkeypatch.setattr(publish, "build_plan", lambda *_: {"row_values": [None] * 5 + [-1.25], "registry_id": "test_cid"})
    calls = []

    def apply(plan, **kwargs):
        calls.append(plan)
        return {"registry_id": "test_cid", "excel_row_number": 68}

    monkeypatch.setattr(publish, "apply_plan", apply)
    publish.promote()
    assert calls == [tmp_path / (row["promotion_id"] + ".plan.json")]


def test_saved_receipt_is_checked_and_never_reapplied(tmp_path, monkeypatch):
    example(tmp_path)
    write_json_exclusive(tmp_path / "one.receipt.json", {"registry_id": "test_cid", "excel_row_number": 68})
    monkeypatch.setattr(publish, "OUT", tmp_path)
    opened = MagicMock()
    opened.__enter__.return_value.execute.return_value.fetchone.return_value = ("test_cid", 68)
    monkeypatch.setattr(publish, "open_registry", lambda _: opened)
    apply = MagicMock()
    monkeypatch.setattr(publish, "apply_plan", apply)
    publish.promote()
    apply.assert_not_called()
    assert not (tmp_path / "one.plan.json").exists()


def test_existing_unreceipted_plan_cannot_be_blindly_retried(tmp_path, monkeypatch):
    import pytest
    example(tmp_path)
    write_json_exclusive(tmp_path / "one.plan.json", {})
    monkeypatch.setattr(publish, "OUT", tmp_path)
    with pytest.raises(FileExistsError, match="prior plan without receipt"):
        publish.promote()
    assert Path(tmp_path / "one.plan.json").read_text().strip() == "{}"
