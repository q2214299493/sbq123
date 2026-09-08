from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from scripts.registry_excel_promotion import (
    WRITER_TIMEOUT_SECONDS,
    _parse_writer_output,
    _run_writer,
    build_plan,
)
from scripts.registry_schema import migrate_registry


def _seed_accepted_adsorption(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO calculations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ads_static", "adsorption_workflow", "final static", "Fe(110)+CO", None, "static_accepted", "2026-08-07T00:00:00Z", None, None),
        )
        connection.execute(
            "INSERT INTO calculation_compatibility VALUES (?, ?, ?, ?, ?)",
            ("ads_static", "fingerprint", "{}", "reviewer", "2026-08-07T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("job_ads", "ads_static", "1001", "LSF", "sunboquan-codex", "normal", "/remote/ads", None, None, None, None),
        )
        connection.execute(
            "INSERT INTO job_status_history (job_record_id, scheduler_status, scientific_status, checked_at) VALUES (?, ?, ?, ?)",
            ("job_ads", "DONE", "Reviewed", "2026-08-07T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("outcar", "ads_static", "job_ads", "output", "OUTCAR", None, "/remote/ads/OUTCAR", "remote", 1, None, "a" * 64, "confirmed", None, None, None),
        )
        connection.execute(
            "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ads_energy",
                "ads_static",
                "adsorption_energy",
                -1.25,
                None,
                "eV",
                None,
                None,
                "matched-static",
                "outcar",
                None,
                None,
                "accepted_matched_static",
                None,
                "2026-08-07T00:00:00Z",
                None,
            ),
        )


def _request(workbook: Path, receipt: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "promotion_id": "ads-co-001",
        "promotion_kind": "adsorption",
        "registry_id": "ads_static",
        "workbook": {"path": str(workbook), "worksheet_name": "Adsorption", "header_row": 1, "headers": ["species", "energy_eV"]},
        "columns": [
            {"header": "species", "source": {"type": "reviewed_metadata", "value": "CO*"}},
            {"header": "energy_eV", "source": {"type": "result", "result_id": "ads_energy"}},
        ],
        "review": {"decision": "approve", "reviewer": "user", "reviewed_at": "2026-08-07T00:00:00Z"},
        "receipt_path": str(receipt),
    }


def _seed_accepted_barrier(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        for calculation_id, purpose in (
            ("is_calc", "initial state"),
            ("ts_calc", "transition state"),
            ("fs_calc", "final state"),
            ("vfa_calc", "frequency validation"),
        ):
            connection.execute(
                "INSERT INTO calculations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    calculation_id,
                    "transition_state_search",
                    purpose,
                    "Fe(110) C+H to CH",
                    None,
                    "accepted",
                    "2026-08-22T00:00:00Z",
                    None,
                    None,
                ),
            )
        connection.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "freq_out",
                "vfa_calc",
                None,
                "frequency_output",
                "OUTCAR",
                "freq/OUTCAR",
                None,
                "local",
                1,
                None,
                "f" * 64,
                "confirmed",
                None,
                None,
                None,
            ),
        )
        result_ids = []
        for role, calculation_id, energy in (
            ("is", "is_calc", -10.0),
            ("ts", "ts_calc", -9.1),
            ("fs", "fs_calc", -9.8),
        ):
            file_id = f"{role}_out"
            result_id = f"{role}_energy"
            result_ids.append(result_id)
            connection.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    calculation_id,
                    None,
                    "output",
                    "OUTCAR",
                    f"{role}/OUTCAR",
                    None,
                    "local",
                    1,
                    None,
                    role[0] * 64,
                    "confirmed",
                    None,
                    None,
                    None,
                ),
            )
            connection.execute(
                "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result_id,
                    calculation_id,
                    "final_energy",
                    energy,
                    None,
                    "eV",
                    None,
                    None,
                    "fe110_converged_toten_sigma0p20_v1",
                    file_id,
                    None,
                    None,
                    "accepted_compatible_final_energy",
                    None,
                    "2026-08-22T00:00:00Z",
                    None,
                ),
            )
        connection.execute(
            """
            INSERT INTO ts_validations
            (ts_validation_id, calculation_id, source_saddle_calculation_id,
             source_method, frequency_output_file_id, contract_sha256,
             atom_map_sha256, compatibility_fingerprint,
             imaginary_frequency_count, imaginary_frequencies_cm1,
             principal_mode_assignment, geometry_status, grade,
             kinetic_eligible, reviewed_at, reviewer)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tsv_a",
                "vfa_calc",
                "ts_calc",
                "dimer",
                "freq_out",
                "c" * 64,
                "a" * 64,
                "compatibility",
                1,
                "[-842.194583]",
                "accepted",
                "pass",
                "A",
                1,
                "2026-08-22T00:00:00Z",
                "user",
            ),
        )
        connection.execute(
            """
            INSERT INTO ts_barriers
            (barrier_set_id, reaction_id, source_calculation_id, ts_validation_id,
             initial_result_id, ts_result_id, final_result_id,
             compatibility_fingerprint, energy_convention, forward_barrier_ev,
             reverse_barrier_ev, reaction_energy_ev, validation_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "barrier_a",
                "c_h_to_ch",
                "ts_calc",
                "tsv_a",
                *result_ids,
                "compatibility",
                "fe110_converged_toten_sigma0p20_v1",
                0.9,
                0.7,
                0.2,
                "accepted",
                "2026-08-22T00:00:00Z",
            ),
        )


def test_build_barrier_plan_resolves_endpoint_energies_and_ts_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_barrier(database)
    workbook = tmp_path / "barrier.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    receipt = tmp_path / "receipt.json"
    request = {
        "schema_version": 1,
        "promotion_id": "barrier-001",
        "promotion_kind": "barrier",
        "registry_id": "barrier_a",
        "workbook": {
            "path": str(workbook),
            "worksheet_name": "TS记录",
            "header_row": 1,
            "headers": ["IS", "TS", "FS", "虚频数", "主模", "审核时间", "能垒"],
        },
        "columns": [
            {"header": "IS", "source": {"type": "barrier_energy", "role": "initial"}},
            {"header": "TS", "source": {"type": "barrier_energy", "role": "ts"}},
            {"header": "FS", "source": {"type": "barrier_energy", "role": "final"}},
            {
                "header": "虚频数",
                "source": {"type": "ts_validation_field", "field": "imaginary_frequency_count"},
            },
            {
                "header": "主模",
                "source": {
                    "type": "ts_validation_field",
                    "field": "principal_imaginary_frequency_cm1",
                },
            },
            {
                "header": "审核时间",
                "source": {
                    "type": "ts_validation_field",
                    "field": "reviewed_at_excel_serial",
                },
            },
            {
                "header": "能垒",
                "source": {"type": "barrier_field", "field": "forward_barrier_ev"},
            },
        ],
        "review": {
            "decision": "approve",
            "reviewer": "user",
            "reviewed_at": "2026-08-22T00:00:00Z",
        },
        "receipt_path": str(receipt),
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    plan = build_plan(request_path, database)

    assert plan["row_values"] == [-10.0, -9.1, -9.8, 1, 842.194583, 46256.0, 0.9]
    assert plan["source_bindings"][4]["ts_validation_id"] == "tsv_a"


def test_build_plan_binds_excel_values_to_accepted_registry_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    request_path = tmp_path / "request.json"
    receipt = tmp_path / "receipt.json"
    request_path.write_text(json.dumps(_request(workbook, receipt)), encoding="utf-8")

    plan = build_plan(request_path, database)

    assert plan["row_values"] == ["CO*", -1.25]
    assert plan["source_bindings"][1]["result_id"] == "ads_energy"
    assert plan["workbook_sha256_before"]
    assert not receipt.exists()


def test_plan_rejects_numeric_review_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    receipt = tmp_path / "receipt.json"
    request = _request(workbook, receipt)
    request["columns"][0]["source"]["value"] = 1.0  # type: ignore[index]
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(ValueError, match="reviewed_metadata"):
        build_plan(request_path, database)


def test_plan_rejects_transition_state_endpoint_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE calculations SET module='transition_state_search' WHERE calculation_id='ads_static'")
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    receipt = tmp_path / "receipt.json"
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request(workbook, receipt)), encoding="utf-8")

    with pytest.raises(ValueError, match="adsorption_workflow"):
        build_plan(request_path, database)


def test_build_plan_accepts_reviewed_compatible_relaxation_energy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE calculations SET workflow_status='energy_accepted' WHERE calculation_id='ads_static'"
        )
        connection.execute(
            "UPDATE results SET validation_status='accepted_compatible_final_energy', "
            "reference_convention='fe110_converged_toten_sigma0p20_v1' "
            "WHERE result_id='ads_energy'"
        )
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    request_path = tmp_path / "request.json"
    receipt = tmp_path / "receipt.json"
    request_path.write_text(json.dumps(_request(workbook, receipt)), encoding="utf-8")

    plan = build_plan(request_path, database)

    assert plan["row_values"] == ["CO*", -1.25]


def test_build_plan_accepts_compatible_adsorption_energy_for_existing_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE calculations SET workflow_status='energy_accepted' "
            "WHERE calculation_id='ads_static'"
        )
        connection.execute(
            "UPDATE results SET result_name='adsorption_energy', "
            "validation_status='accepted_compatible_adsorption_energy', "
            "reference_convention='Eads=E(CO*)-E(clean)-E(CO_gas)' "
            "WHERE result_id='ads_energy'"
        )
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    receipt = tmp_path / "receipt.json"
    request = _request(workbook, receipt)
    request["workbook"]["target_row"] = 3  # type: ignore[index]
    request["columns"][0]["source"] = {  # type: ignore[index]
        "type": "existing_workbook_cell",
        "expected_value": "CO*",
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    plan = build_plan(request_path, database)

    assert plan["target_row"] == 3
    assert plan["row_values"] == ["CO*", -1.25]
    assert plan["source_bindings"][0]["kind"] == "existing_workbook_cell"
    assert plan["source_bindings"][1]["result_name"] == "adsorption_energy"


def test_build_plan_accepts_recorded_unknown_historical_scheduler_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE job_status_history SET scheduler_status='UNKNOWN' "
            "WHERE job_record_id='job_ads'"
        )
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    receipt = tmp_path / "receipt.json"
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request(workbook, receipt)), encoding="utf-8")

    plan = build_plan(request_path, database)

    assert plan["registry_id"] == "ads_static"


def test_plan_rejects_existing_workbook_cell_for_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.registry_excel_promotion as promotion

    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    workbook = tmp_path / "adsorption.xlsx"
    workbook.write_bytes(b"not parsed during planning")
    receipt = tmp_path / "receipt.json"
    request = _request(workbook, receipt)
    request["columns"][0]["source"] = {  # type: ignore[index]
        "type": "existing_workbook_cell",
        "expected_value": "CO*",
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(ValueError, match="existing-row promotion"):
        build_plan(request_path, database)


def test_writer_output_parser_ignores_artifact_tool_diagnostic_line() -> None:
    output = (
        "Inspect result written to file: temporary.xlsx.inspect.ndjson\n"
        '{"row_number":2,"worksheet_name":"Adsorption"}'
    )

    assert _parse_writer_output(output) == {"row_number": 2, "worksheet_name": "Adsorption"}


def test_excel_writer_has_finite_timeout_and_preserves_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node_modules = tmp_path / "node_modules"
    artifact_module = node_modules / "@oai" / "artifact-tool" / "dist" / "artifact_tool.mjs"
    artifact_module.parent.mkdir(parents=True)
    artifact_module.write_text("export {};", encoding="ascii")

    def time_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == WRITER_TIMEOUT_SECONDS
        assert kwargs["encoding"] == "utf-8"
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=WRITER_TIMEOUT_SECONDS)

    monkeypatch.setattr(subprocess, "run", time_out)
    with pytest.raises(RuntimeError, match="Excel writer timed out") as error:
        _run_writer(
            tmp_path / "plan.json",
            tmp_path / "output.xlsx",
            node=tmp_path / "node.exe",
            node_modules=node_modules,
            writer=tmp_path / "writer.mjs",
        )
    assert isinstance(error.value.__cause__, subprocess.TimeoutExpired)
