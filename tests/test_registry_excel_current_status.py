import json

import pytest

from scripts.registry_excel_promotion import build_plan
from scripts.registry_schema import migrate_registry
from tests.registry_fixture_mutation import fixture_connection
from tests.test_registry_excel_promotion import _request, _seed_accepted_adsorption


def prepared(tmp_path, monkeypatch, status):
    monkeypatch.setattr("scripts.registry_excel_promotion.ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    with fixture_connection(database) as connection:
        connection.execute("UPDATE calculations SET workflow_status=? WHERE calculation_id=?", (status, "ads_static"))
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"plan checks provenance only; writer validates XLSX")
    request = _request(workbook, tmp_path / "receipt.json")
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return database, path, request


@pytest.mark.parametrize("status", ["accepted", "static_accepted", "energy_accepted"])
def test_current_and_legacy_accepted_workflow_states(tmp_path, monkeypatch, status):
    database, path, _ = prepared(tmp_path, monkeypatch, status)
    assert build_plan(path, database)["row_values"] == ["CO*", -1.25]


@pytest.mark.parametrize("status", ["submitted", "needs_review", "duplicate", "rejected"])
def test_unaccepted_workflow_stays_blocked(tmp_path, monkeypatch, status):
    database, path, _ = prepared(tmp_path, monkeypatch, status)
    with pytest.raises(ValueError, match="workflow_status"):
        build_plan(path, database)


def test_accepted_workflow_cannot_promote_reviewed_only_energy(tmp_path, monkeypatch):
    database, path, _ = prepared(tmp_path, monkeypatch, "accepted")
    with fixture_connection(database) as connection:
        connection.execute("UPDATE results SET validation_status='reviewed'")
    with pytest.raises(ValueError, match="not an accepted"):
        build_plan(path, database)


@pytest.mark.parametrize("source_job,parent,allowed", [("job_ads", "ads_static", True),
                                                     (None, "ads_static", False),
                                                     ("job_ads", None, False)])
def test_reclassified_state_requires_exact_parent_output_job_link(tmp_path, monkeypatch, source_job, parent, allowed):
    database, path, request = prepared(tmp_path, monkeypatch, "rejected")
    with fixture_connection(database) as connection:
        connection.execute("INSERT INTO calculations VALUES (?,?,?,?,?,?,?,?,?)",
                           ("child", "adsorption_workflow", "reviewed reclassification", "CH*+CO*", parent, "accepted",
                            "2026-10-22T00:00:00Z", None, "same output, not a second run"))
        connection.execute("INSERT INTO calculation_compatibility VALUES (?,?,?,?,?)",
                           ("child", "fingerprint", "{}", "reviewer", "2026-10-22T00:00:00Z"))
        connection.execute("INSERT INTO files SELECT ?,?, ?,role,filename,local_path,remote_path,storage_mode,byte_size,modified_at,sha256,existence_status,license_or_sensitivity,source_file_id,notes FROM files WHERE file_id=?",
                           ("child_outcar", "child", source_job, "outcar"))
        connection.execute("INSERT INTO results SELECT ?,?,result_name,numeric_value,text_value,unit,temperature_k,pressure_pa,reference_convention,?,source_locator,extraction_method,validation_status,uncertainty_text,created_at,notes FROM results WHERE result_id=?",
                           ("child_energy", "child", "child_outcar", "ads_energy"))
        connection.execute("UPDATE results SET validation_status='accepted_compatible_final_energy' WHERE result_id='child_energy'")
    request["registry_id"] = "child"
    request["columns"][1]["source"]["result_id"] = "child_energy"
    path.write_text(json.dumps(request), encoding="utf-8")
    if allowed:
        assert build_plan(path, database)["calculation_id"] == "child"
    else:
        with pytest.raises(ValueError, match="recorded scheduler status"):
            build_plan(path, database)
