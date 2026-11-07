"""Bounded tests;never submit jobs or invoke either potential model."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.artifact_io import load_json_object, sha256_file
from scripts.aqcat25_handoff import validate_handoff
from scripts.vasp_result_gate import read_incar_values
from archive.fe110_c2_supplement_vasp_20261107 import dft
from archive.fe110_c2_supplement_vasp_20261107.review import OUT, PACKAGE, SELECTED


def test_latest_exact_ten_and_omissions():
    rows = dft.selection()
    assert len(rows) == 10
    assert [row["name"] for row in rows] == SELECTED
    assert not {"06_S1", "09_S1"}.intersection(SELECTED)
    assert sum(row["source_role"] == "ML_pre_relaxed" for row in rows) == 9


def test_original_fallback_is_byte_exact_not_failed_ML():
    row = next(row for row in dft.selection() if row["name"] == "06_S2")
    assert row["source_role"] == "reviewed_original_no_ML"
    assert sha256_file(Path(row["selected_for_DFT"])) == sha256_file(Path(row["original_POSCAR"]))
    assert sha256_file(Path(row["selected_for_DFT"])) != sha256_file(Path(row["ML_final_POSCAR"]))


def test_all_twelve_return_handoffs_and_failed_graph_evidence_retained():
    for path in (OUT / "return_handoffs").glob("*.json"):
        validate_handoff(path, root=OUT, schema_path=PACKAGE / "handoff.schema.json")
    assert len(list((OUT / "return_handoffs").glob("*.json"))) == 12
    review = load_json_object(OUT / "ML_results_review.json")
    assert {row["name"] for row in review["cases"] if not row["exact_target_graph_retained"]} == {"06_S1", "06_S2", "09_S1"}


def test_all_ten_canonical_inputs_exact_current_profile():
    for row in dft.selection():
        report = dft.validate_input(dft.PREP / row["name"], row)
        assert report["passed"]
        values = read_incar_values(dft.PREP / row["name"] / "INCAR")
        assert float(values["SIGMA"]) == .20 and values["ALGO"].lower() == "fast"
        assert float(values["EDIFFG"]) == -.02 and int(values["NSW"]) == 300


@pytest.mark.parametrize("change", ["include_cancelled", "wrong_original", "unreviewed_ML"])
def test_scope_or_fallback_changes_rejected(change):
    data = deepcopy(load_json_object(OUT / "selection_review.json"))
    if change == "include_cancelled":
        data["cases"].append({**data["cases"][0], "name": "06_S1"})
    elif change == "wrong_original":
        row = next(row for row in data["cases"] if row["name"] == "06_S2")
        row["selected_for_DFT"] = row["ML_final_POSCAR"]
        row["selected_POSCAR_sha256"] = sha256_file(Path(row["ML_final_POSCAR"]))
    else:
        data["cases"][0]["ML_initial_structure_eligible"] = False
    with patch.object(dft, "load_json_object", return_value=data), patch.object(dft, "source_file_manifest_valid", return_value=True), pytest.raises(ValueError):
        dft.selection()


def test_existing_reservation_blocks_before_any_submission():
    ready = load_json_object(dft.SUBMISSION / "ready_for_submission.json")
    with patch.object(dft, "selection"), patch.object(dft, "load_json_object", return_value=ready), \
            patch.object(dft, "source_file_manifest_valid", return_value=True), \
            patch.object(dft, "submission_status", return_value={"status": "SUBMITTED"}), \
            patch.object(dft, "submit") as submit, pytest.raises(ValueError, match="prior reservation"):
        dft.execute()
    submit.assert_not_called()
