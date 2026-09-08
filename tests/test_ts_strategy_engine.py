from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import yaml

from scripts.neb_agent.utils_structure import Poscar, write_poscar
from scripts.ts_strategy_engine.contract import normalize_contract
from scripts.ts_strategy_engine.connectivity_evidence import validate_source_saddle_job
from scripts.ts_strategy_engine.evidence import (
    record_matched_static_barrier,
    record_ts_validation,
    register_calculation_compatibility,
    validate_endpoint_evidence,
)
from scripts.ts_strategy_engine.fingerprint import build_fingerprint, rank_templates
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review
from scripts.ts_strategy_engine.matched_static_evidence import (
    matched_static_convention,
    matched_static_rows,
)
from scripts.ts_strategy_engine.strategy import compose_strategy, decide_search
from scripts.ts_strategy_engine.templates import load_templates, record_template, validate_record
from scripts.ts_strategy_engine.workflow import PlanRequest, _resolve_constraints, plan


ROOT = Path(__file__).resolve().parents[1]


def test_source_saddle_done_history_does_not_require_redundant_finished_at(
    tmp_path: Path,
) -> None:
    db = tmp_path / "registry.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            (ROOT / "modules" / "calculation_registry" / "schema.sql").read_text(
                encoding="utf-8"
            )
        )
        _insert_calculation(connection, "calc_dimer")
        connection.execute(
            """
            INSERT INTO jobs
            (job_record_id, calculation_id, scheduler_job_id, scheduler, server_alias,
             remote_directory, finished_at)
            VALUES ('job_dimer', 'calc_dimer', '123', 'LSF',
                    'sunboquan-codex', 'remote/dimer', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO job_status_history
            (job_record_id, scheduler_status, scientific_status, checked_at)
            VALUES ('job_dimer', 'DONE', 'technically_converged', '2026-08-22T00:00:00Z')
            """
        )
        connection.row_factory = sqlite3.Row
        validate_source_saddle_job(
            connection,
            {
                "source_job_record_id": "job_dimer",
                "source_saddle_calculation_id": "calc_dimer",
            },
        )


def authoritative_gate(database_path: Path, validation: dict) -> tuple[Path, str]:
    decision = decide_search(
        {"status": "PASS"},
        {
            "path_binding_valid": True,
            "image_sequence_complete": True,
            "images": [],
        },
        {},
        True,
        True,
        validation=validation,
    )
    path = database_path.with_name(f"{database_path.stem}_authoritative_gate.json")
    path.write_text(json.dumps(decision), encoding="utf-8")
    return path, decision["state_sha256"]


def barrier_validation(**updates: str) -> dict:
    claim = {
        "barrier_set_id": "barrier_a",
        "reaction_id": "co_split",
        "source_calculation_id": "calc_ts",
        "ts_validation_id": "validation_a",
        "initial_result_id": "is_energy",
        "ts_result_id": "ts_energy",
        "final_result_id": "fs_energy",
    }
    claim.update(updates)
    return {
        "frequency_grade": "A",
        "frequency_structure_hash_valid": True,
        "bidirectional_connectivity_valid": True,
        "compatible_final_energy_barrier_valid": True,
        "barrier_claim": claim,
    }


def contract(**overrides: object) -> dict:
    payload = {
        "reaction_id": "co_split",
        "reaction_family": "co_dissociation",
        "reactant_id": "co*/fe45",
        "product_id": "c*+o*/fe45",
        "index_base": 0,
        "atom_map": [[0, 0], [1, 1], [2, 2]],
        "reaction_atoms": [1, 2],
        "broken_bonds": [[1, 2]],
        "formed_bonds": [],
        "site_changes": ["O:molecular->hollow"],
        "compatibility": {
            "material": "Fe",
            "surface": "Fe110",
            "branch": "true_fe110_5layer_5x5x1",
            "slab_model": "Fe45_bottom18_fixed",
            "xc": "PBE",
            "potcar_family": "PAW_PBE",
            "encut_ev": 400,
            "kmesh": [5, 5, 1],
            "magnetic_state": "ISPIN2_ferromagnetic_Fe",
            "coverage": "3x3_single_reaction_complex",
            "ismear": 1,
            "sigma_ev": 0.1,
            "fixed_atom_indices_zero_based": [0],
            "ldipol": False,
            "vacuum_thickness_angstrom": 15.0,
            "final_energy_convention": "fe110_final_static_v1",
        },
        "endpoints": {
            "initial": {"calculation_id": "calc_is", "structure_file_id": "is_structure", "static_result_id": "is_energy"},
            "final": {"calculation_id": "calc_fs", "structure_file_id": "fs_structure", "static_result_id": "fs_energy"},
        },
    }
    payload.update(overrides)
    return normalize_contract(payload)


def fingerprint() -> dict:
    return build_fingerprint(contract())


def _insert_calculation(connection: sqlite3.Connection, calculation_id: str) -> None:
    connection.execute(
        """
        INSERT INTO calculations
        (calculation_id, module, purpose, scientific_system, workflow_status, created_at)
        VALUES (?, 'transition_state_search', 'test', 'Fe110', 'validated', '2026-01-01')
        """,
        (calculation_id,),
    )


def _insert_file(connection: sqlite3.Connection, file_id: str, calculation_id: str, role: str) -> None:
    connection.execute(
        """
        INSERT INTO files
        (file_id, calculation_id, role, filename, remote_path, storage_mode, byte_size, sha256, existence_status)
        VALUES (?, ?, ?, 'OUTCAR', 'remote/file', 'external', 1, ?, 'confirmed')
        """,
        (file_id, calculation_id, role, f"sha256-{file_id}"),
    )


def database(path: Path) -> Path:
    active_contract = contract()
    saddle_path = path.parent / "saddle.vasp"
    frequency_poscar = path.parent / "frequency.POSCAR"
    frequency_outcar = path.parent / "frequency.OUTCAR"
    saddle_path.write_text("saddle\n", encoding="ascii")
    frequency_poscar.write_text("frequency structure\n", encoding="ascii")
    frequency_outcar.write_text("frequency output\n", encoding="ascii")
    vfa_handoff_path = path.parent / "vfa_handoff.json"
    vfa_handoff_path.write_text(
        json.dumps(
            {
                "source_sha256": hashlib.sha256(saddle_path.read_bytes()).hexdigest(),
                "frequency_poscar_sha256": hashlib.sha256(
                    frequency_poscar.read_bytes()
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    connectivity_path = path.parent / "connectivity_report.json"
    connectivity_path.write_text(
        json.dumps(
            {
                "document_kind": "vasp_bidirectional_ts_connectivity",
                "status": "PASS",
                "grade_a_connectivity_eligible": True,
                "connects_to_is": True,
                "connects_to_fs": True,
                "contract_sha256": active_contract["contract_sha256"],
                "atom_map_sha256": active_contract["atom_map_sha256"],
                "compatibility_sha256": active_contract["compatibility_sha256"],
                "source_saddle": {
                    "path": str(saddle_path),
                    "sha256": hashlib.sha256(saddle_path.read_bytes()).hexdigest(),
                },
                "frequency_poscar": {
                    "path": str(frequency_poscar),
                    "sha256": hashlib.sha256(frequency_poscar.read_bytes()).hexdigest(),
                },
                "frequency_outcar": {
                    "path": str(frequency_outcar),
                    "sha256": hashlib.sha256(frequency_outcar.read_bytes()).hexdigest(),
                },
                "branches": [
                    {"direction": "positive", "job_id": "scheduler_connectivity_plus"},
                    {"direction": "negative", "job_id": "scheduler_connectivity_minus"},
                ],
            }
        ),
        encoding="utf-8",
    )
    connectivity_sha = hashlib.sha256(connectivity_path.read_bytes()).hexdigest()
    with sqlite3.connect(path) as connection:
        connection.executescript((ROOT / "modules" / "calculation_registry" / "schema.sql").read_text(encoding="utf-8"))
        for calculation_id in (
            "calc_ts",
            "calc_vfa",
            "calc_is",
            "calc_ts_static",
            "calc_fs",
            "calc_connectivity_plus",
            "calc_connectivity_minus",
        ):
            _insert_calculation(connection, calculation_id)
        for direction in ("plus", "minus"):
            connection.execute(
                """
                INSERT INTO jobs
                (job_record_id, calculation_id, scheduler_job_id, scheduler, server_alias,
                 remote_directory, finished_at)
                VALUES (?, ?, ?, 'LSF', 'sunboquan-codex', 'remote/connectivity', '2026-01-01')
                """,
                (
                    f"job_connectivity_{direction}",
                    f"calc_connectivity_{direction}",
                    f"scheduler_connectivity_{direction}",
                ),
            )
            connection.execute(
                """
                INSERT INTO job_status_history
                (job_record_id, scheduler_status, scientific_status, checked_at)
                VALUES (?, 'DONE', 'connectivity_branch_converged', '2026-01-01')
                """,
                (f"job_connectivity_{direction}",),
            )
        connection.execute(
            """
            INSERT INTO jobs
            (job_record_id, calculation_id, scheduler_job_id, scheduler, server_alias,
             remote_directory, finished_at)
            VALUES ('job_ts_source', 'calc_ts', 'scheduler_ts_source', 'LSF',
                    'sunboquan-codex', 'remote/ts', '2026-01-01')
            """
        )
        connection.execute(
            """
            INSERT INTO job_status_history
            (job_record_id, scheduler_status, scientific_status, checked_at)
            VALUES ('job_ts_source', 'DONE', 'saddle_converged', '2026-01-01')
            """
        )
        for calculation_id in ("calc_is", "calc_ts_static", "calc_fs"):
            connection.execute(
                "UPDATE calculations SET workflow_status='static_accepted' WHERE calculation_id=?",
                (calculation_id,),
            )
            job_record_id = f"job_{calculation_id}"
            connection.execute(
                """
                INSERT INTO jobs
                (job_record_id, calculation_id, scheduler_job_id, scheduler, server_alias,
                 remote_directory, finished_at)
                VALUES (?, ?, ?, 'LSF', 'sunboquan-codex', 'remote/static', '2026-01-01')
                """,
                (job_record_id, calculation_id, f"scheduler_{calculation_id}"),
            )
            connection.execute(
                """
                INSERT INTO job_status_history
                (job_record_id, scheduler_status, scientific_status, checked_at)
                VALUES (?, 'DONE', 'accepted_matched_static', '2026-01-01')
                """,
                (job_record_id,),
            )
        for file_id, calculation_id, role in (
            ("ts_file", "calc_ts", "ts_structure"),
            ("is_structure", "calc_is", "endpoint_structure"),
            ("ts_structure_static", "calc_ts_static", "ts_structure"),
            ("fs_structure", "calc_fs", "endpoint_structure"),
            ("is_outcar", "calc_is", "OUTCAR"),
            ("ts_outcar", "calc_ts_static", "OUTCAR"),
            ("fs_outcar", "calc_fs", "OUTCAR"),
            ("vfa_outcar", "calc_vfa", "frequency_output"),
            ("mode_plus", "calc_vfa", "mode_positive_displacement"),
            ("mode_minus", "calc_vfa", "mode_negative_displacement"),
            ("connectivity_report", "calc_vfa", "bidirectional_connectivity_report"),
        ):
            _insert_file(connection, file_id, calculation_id, role)
        connection.execute(
            "UPDATE files SET sha256=?, local_path=?, byte_size=? WHERE file_id='connectivity_report'",
            (connectivity_sha, str(connectivity_path), connectivity_path.stat().st_size),
        )
        for result_id, calculation_id, energy, source_file in (
            ("is_energy", "calc_is", -10.0, "is_outcar"),
            ("ts_energy", "calc_ts_static", -9.0, "ts_outcar"),
            ("fs_energy", "calc_fs", -10.5, "fs_outcar"),
        ):
            connection.execute(
                """
                INSERT INTO results
                (result_id, calculation_id, result_name, numeric_value, unit, reference_convention,
                 source_file_id, extraction_method, validation_status, created_at)
                VALUES (?, ?, 'matched_static_toten', ?, 'eV', 'fe110_final_static_v1', ?, 'OUTCAR_TOTEN',
                        'accepted_matched_static', '2026-01-01')
                """,
                (result_id, calculation_id, energy, source_file),
            )
        for calculation_id, source_file in (
            ("calc_is", "is_outcar"),
            ("calc_ts_static", "ts_outcar"),
            ("calc_fs", "fs_outcar"),
        ):
            connection.execute(
                "UPDATE files SET job_record_id=? WHERE file_id=?",
                (f"job_{calculation_id}", source_file),
            )
    chemistry = contract()["compatibility"]
    for calculation_id in ("calc_is", "calc_ts_static", "calc_fs"):
        register_calculation_compatibility(path, calculation_id, chemistry, "reviewer", "2026-01-01")
    validation_payload = {
        "validation_calculation_id": "calc_vfa",
        "source_saddle_calculation_id": "calc_ts",
        "source_job_record_id": "job_ts_source",
        "source_method": "ci_neb",
        "frequency_output_file_id": "vfa_outcar",
        "positive_displacement_file_id": "mode_plus",
        "negative_displacement_file_id": "mode_minus",
        "connectivity_report_file_id": "connectivity_report",
        "positive_connectivity_job_record_id": "job_connectivity_plus",
        "negative_connectivity_job_record_id": "job_connectivity_minus",
        "connectivity_report": str(connectivity_path),
        "connectivity_report_sha256": connectivity_sha,
        "vfa_handoff": str(vfa_handoff_path),
        "vfa_handoff_sha256": hashlib.sha256(vfa_handoff_path.read_bytes()).hexdigest(),
        "source_saddle_sha256": hashlib.sha256(saddle_path.read_bytes()).hexdigest(),
        "frequency_poscar_sha256": hashlib.sha256(frequency_poscar.read_bytes()).hexdigest(),
        "connectivity_status": "PASS",
        "contract_sha256": contract()["contract_sha256"],
        "atom_map_sha256": contract()["atom_map_sha256"],
        "compatibility_sha256": contract()["compatibility_sha256"],
        "imaginary_frequency_count": 1,
        "imaginary_frequencies_cm1": [-500.0],
        "principal_mode_assignment": "accepted",
        "geometry_status": "pass",
        "connects_to_is": True,
        "connects_to_fs": True,
        "grade": "A",
        "kinetic_eligible": True,
        "reviewer": "reviewer",
        "reviewed_at": "2026-01-01",
        "frequency_grade": "A",
        "frequency_structure_hash_valid": True,
        "bidirectional_connectivity_valid": True,
        "compatible_final_energy_barrier_valid": True,
        "barrier_claim": {
            "barrier_set_id": "barrier_a",
            "reaction_id": "co_split",
            "source_calculation_id": "calc_ts",
            "ts_validation_id": "validation_a",
            "initial_result_id": "is_energy",
            "ts_result_id": "ts_energy",
            "final_result_id": "fs_energy",
        },
    }
    gate_path, gate_state = authoritative_gate(path, validation_payload)
    record_ts_validation(
        path,
        "validation_a",
        validation_payload,
        gate_decision=gate_path,
        gate_state_sha256=gate_state,
    )
    record_matched_static_barrier(
        path,
        gate_decision=gate_path,
        gate_state_sha256=gate_state,
        barrier_set_id="barrier_a",
        reaction_id="co_split",
        source_calculation_id="calc_ts",
        ts_validation_id="validation_a",
        initial_result_id="is_energy",
        ts_result_id="ts_energy",
        final_result_id="fs_energy",
        learning_record=successful_record(),
    )
    return path


def successful_record(**updates: object) -> dict:
    record = {
        "template_id": "fe110_co_split_grade_a",
        "reaction_family": "co_dissociation",
        "fingerprint": fingerprint(),
        "waypoint_strategy": ["molecular", "bent", "dissociated"],
        "interpolation_strategy": "segmented_idpp",
        "neb_settings": {
            "sequence": ["ordinary_neb", "ci_neb"],
            "image_count_policy": "adaptive_recompute",
        },
        "dimer_usage": {"policy": "conditional_refinement"},
        "ts_structure_file_id": "ts_file",
        "ts_validation_id": "validation_a",
        "barrier_set_id": "barrier_a",
        "convergence_history": [{"method": "ci_neb", "status": "converged"}],
        "failure_cases": [],
        "correction_strategy": None,
        "outcome": "success",
        "validation_grade": "A",
        "source_calculation_id": "calc_ts",
    }
    record.update(updates)
    return record


def test_matched_static_barrier_rejects_missing_completed_vasp_job_evidence(tmp_path: Path) -> None:
    path = database(tmp_path / "registry.sqlite3")
    gate_path, gate_state = authoritative_gate(
        path,
        barrier_validation(
            barrier_set_id="barrier_without_vasp_evidence",
            reaction_id="co_split_without_evidence",
        ),
    )
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM job_status_history WHERE job_record_id='job_calc_ts_static'")
    with pytest.raises(ValueError, match="latest status event"):
        record_matched_static_barrier(
            path,
            gate_decision=gate_path,
            gate_state_sha256=gate_state,
            barrier_set_id="barrier_without_vasp_evidence",
            reaction_id="co_split_without_evidence",
            source_calculation_id="calc_ts",
            ts_validation_id="validation_a",
            initial_result_id="is_energy",
            ts_result_id="ts_energy",
            final_result_id="fs_energy",
            learning_record=successful_record(
                template_id="template_without_vasp_evidence",
                barrier_set_id="barrier_without_vasp_evidence",
            ),
        )


def test_barrier_and_learning_record_roll_back_together(tmp_path: Path) -> None:
    db = database(tmp_path / "registry.sqlite3")
    barrier_id = "barrier_invalid_learning_record"
    gate_path, gate_state = authoritative_gate(
        db,
        barrier_validation(
            barrier_set_id=barrier_id,
            reaction_id="co_split_invalid_learning_record",
        ),
    )
    record = successful_record(
        template_id="template_invalid_learning_record",
        barrier_set_id=barrier_id,
    )
    record["dimer_usage"] = {
        "policy": "local_refinement",
        "source_image": "image03",
    }

    with pytest.raises(ValueError, match="non-transferable system-specific keys"):
        record_matched_static_barrier(
            db,
            gate_decision=gate_path,
            gate_state_sha256=gate_state,
            barrier_set_id=barrier_id,
            reaction_id="co_split_invalid_learning_record",
            source_calculation_id="calc_ts",
            ts_validation_id="validation_a",
            initial_result_id="is_energy",
            ts_result_id="ts_energy",
            final_result_id="fs_energy",
            learning_record=record,
        )
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT 1 FROM ts_barriers WHERE barrier_set_id=?", (barrier_id,)
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM ts_strategy_templates WHERE template_id=?",
            (record["template_id"],),
        ).fetchone() is None


def test_grade_a_template_is_evidence_bound_and_transferred(tmp_path: Path) -> None:
    db = database(tmp_path / "registry.sqlite3")
    assert validate_endpoint_evidence(db, contract())["status"] == "PASS"
    assert record_template(db, successful_record()) == "fe110_co_split_grade_a"
    ranked = rank_templates(fingerprint(), load_templates(db))
    config = yaml.safe_load((ROOT / "configs" / "ts_strategy_engine" / "families.yaml").read_text(encoding="utf-8"))
    strategy = compose_strategy(fingerprint(), ranked, config)
    assert ranked[0]["score"] == 1.0
    assert ranked[0]["evidence_valid"] is True
    assert ranked[0]["strategy_transferable"] is True
    assert ranked[0]["result_transferable"] is True
    assert strategy["strategy_source"] == "template_transfer"
    assert strategy["reuse_scope"] == "method_strategy_only"
    assert strategy["result_reuse_policy"] == "reference_existing_registered_result_only"
    assert strategy["automatic_submission"] is False
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE files SET sha256=NULL WHERE file_id='mode_plus'")
    assert load_templates(db)[0]["evidence_valid"] is False


def test_grade_a_dimer_template_does_not_require_optional_connectivity_files(
    tmp_path: Path,
) -> None:
    db = database(tmp_path / "registry.sqlite3")
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE ts_validations SET source_method='dimer', "
            "positive_displacement_file_id=NULL, negative_displacement_file_id=NULL, "
            "connects_to_is=NULL, connects_to_fs=NULL WHERE ts_validation_id='validation_a'"
        )

    assert record_template(db, successful_record()) == "fe110_co_split_grade_a"
    template = load_templates(db)[0]
    assert template["validation_source_method"] == "dimer"
    assert template["evidence_valid"] is True


def test_barrier_gate_rejects_a_revoked_latest_matched_static_status(tmp_path: Path) -> None:
    db = database(tmp_path / "registry.sqlite3")
    gate_path, gate_state = authoritative_gate(
        db,
        barrier_validation(barrier_set_id="barrier_after_revocation"),
    )
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO job_status_history
            (job_record_id, scheduler_status, scientific_status, checked_at, notes)
            VALUES ('job_calc_ts_static', 'DONE', 'review_revoked', '2026-02-01', 'corrected review')
            """
        )
    with pytest.raises(ValueError, match="latest status event"):
        record_matched_static_barrier(
            db,
            gate_decision=gate_path,
            gate_state_sha256=gate_state,
            barrier_set_id="barrier_after_revocation",
            reaction_id="co_split",
            source_calculation_id="calc_ts",
            ts_validation_id="validation_a",
            initial_result_id="is_energy",
            ts_result_id="ts_energy",
            final_result_id="fs_energy",
            learning_record=successful_record(
                template_id="template_after_revocation",
                barrier_set_id="barrier_after_revocation",
            ),
        )


def test_compatible_converged_sigma0p20_toten_chain_is_accepted(tmp_path: Path) -> None:
    db = database(tmp_path / "registry.sqlite3")
    compatibility = dict(contract()["compatibility"])
    compatibility["sigma_ev"] = 0.2
    compatibility["final_energy_convention"] = "fe110_converged_toten_sigma0p20_v1"
    for calculation_id in ("calc_is", "calc_ts_static", "calc_fs"):
        register_calculation_compatibility(
            db, calculation_id, compatibility, "reviewer", "2026-02-01"
        )
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "UPDATE calculations SET workflow_status='energy_accepted' "
            "WHERE calculation_id IN ('calc_is', 'calc_ts_static', 'calc_fs')"
        )
        connection.execute(
            "UPDATE results SET result_name='final_toten', "
            "reference_convention='fe110_converged_toten_sigma0p20_v1', "
            "validation_status='accepted_compatible_final_energy' "
            "WHERE result_id IN ('is_energy', 'ts_energy', 'fs_energy')"
        )
        for calculation_id in ("calc_is", "calc_ts_static", "calc_fs"):
            connection.execute(
                "INSERT INTO job_status_history "
                "(job_record_id, scheduler_status, scientific_status, checked_at) "
                "VALUES (?, 'DONE', 'accepted_compatible_final_energy', '2026-02-01')",
                (f"job_{calculation_id}",),
            )
        rows = matched_static_rows(connection, ("is_energy", "ts_energy", "fs_energy"))
        convention, fingerprint = matched_static_convention(rows)

    assert convention == "fe110_converged_toten_sigma0p20_v1"
    assert fingerprint


def test_final_energy_chain_accepts_reviewed_expired_scheduler_record(
    tmp_path: Path,
) -> None:
    db = database(tmp_path / "registry.sqlite3")
    compatibility = dict(contract()["compatibility"])
    compatibility["sigma_ev"] = 0.2
    compatibility["final_energy_convention"] = "fe110_converged_toten_sigma0p20_v1"
    for calculation_id in ("calc_is", "calc_ts_static", "calc_fs"):
        register_calculation_compatibility(
            db, calculation_id, compatibility, "reviewer", "2026-02-01"
        )
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE calculations SET workflow_status='energy_accepted' "
            "WHERE calculation_id IN ('calc_is', 'calc_ts_static', 'calc_fs')"
        )
        connection.execute(
            "UPDATE results SET reference_convention='fe110_converged_toten_sigma0p20_v1', "
            "validation_status='accepted_compatible_final_energy' "
            "WHERE result_id IN ('is_energy', 'ts_energy', 'fs_energy')"
        )
        for calculation_id in ("calc_is", "calc_ts_static", "calc_fs"):
            connection.execute(
                "INSERT INTO job_status_history "
                "(job_record_id, scheduler_status, scientific_status, checked_at) "
                "VALUES (?, 'DONE', 'accepted_compatible_final_energy', '2026-02-01')",
                (f"job_{calculation_id}",),
            )
        connection.execute(
            "UPDATE jobs SET finished_at=NULL WHERE job_record_id='job_calc_is'"
        )
        connection.execute(
            "INSERT INTO job_status_history "
            "(job_record_id, scheduler_status, scientific_status, checked_at) "
            "VALUES ('job_calc_is', 'UNKNOWN', 'accepted_compatible_final_energy', '2026-03-01')"
        )
        connection.execute(
            "INSERT INTO reviews "
            "(review_id, calculation_id, review_type, decision, reviewer, reviewed_at, evidence, reason) "
            "VALUES ('expired_scheduler_calc_is', 'calc_is', "
            "'historical_scheduler_retention_exception', 'accepted', 'reviewer', "
            "'2026-03-01', '{\"outcar_sha256\":\"bound\"}', "
            "'Scheduler record expired; hash-bound VASP completion evidence retained.')"
        )
        connection.row_factory = sqlite3.Row
        rows = matched_static_rows(connection, ("is_energy", "ts_energy", "fs_energy"))
        convention, fingerprint = matched_static_convention(rows)

    assert convention == "fe110_converged_toten_sigma0p20_v1"
    assert fingerprint


def test_final_energy_chain_uses_append_only_done_review_not_stale_summary_fields(
    tmp_path: Path,
) -> None:
    db = database(tmp_path / "registry.sqlite3")
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE calculations SET workflow_status='submitted' "
            "WHERE calculation_id IN ('calc_is', 'calc_ts_static', 'calc_fs')"
        )
        connection.execute(
            "UPDATE jobs SET finished_at=NULL "
            "WHERE calculation_id IN ('calc_is', 'calc_ts_static', 'calc_fs')"
        )
        connection.row_factory = sqlite3.Row
        rows = matched_static_rows(connection, ("is_energy", "ts_energy", "fs_energy"))
        convention, fingerprint = matched_static_convention(rows)

    assert convention == "fe110_final_static_v1"
    assert fingerprint


def test_final_energy_chain_rejects_mixed_static_and_relaxation_statuses(
    tmp_path: Path,
) -> None:
    db = database(tmp_path / "registry.sqlite3")
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "UPDATE results SET validation_status='accepted_compatible_final_energy' "
            "WHERE result_id='ts_energy'"
        )
        rows = matched_static_rows(connection, ("is_energy", "ts_energy", "fs_energy"))
        with pytest.raises(ValueError, match="one accepted validation status"):
            matched_static_convention(rows)


def test_final_compatibility_fingerprint_changes_with_smearing_and_rejects_partial_blocks() -> None:
    baseline = contract()
    changed_payload = copy.deepcopy(baseline)
    changed_payload.pop("version")
    changed_payload.pop("contract_sha256")
    changed_payload.pop("compatibility_sha256")
    changed_payload.pop("atom_map_sha256")
    changed_payload["compatibility"]["sigma_ev"] = 0.2
    changed = normalize_contract(changed_payload)
    assert changed["compatibility_sha256"] != baseline["compatibility_sha256"]

    partial = copy.deepcopy(changed_payload)
    partial["compatibility"].pop("ldipol")
    with pytest.raises(ValueError, match="partial final-energy compatibility block"):
        normalize_contract(partial)


def test_successful_template_without_validation_and_barrier_is_rejected() -> None:
    record = successful_record()
    record.pop("ts_validation_id")
    record.pop("barrier_set_id")
    with pytest.raises(ValueError, match="matched-static barrier IDs"):
        validate_record(record)


def test_strategy_fields_reject_system_specific_transfer_artifacts() -> None:
    record = successful_record()
    record["dimer_usage"] = {"policy": "local_refinement", "source_image": "image03"}
    with pytest.raises(ValueError, match="non-transferable system-specific keys"):
        validate_record(record)


def test_similar_reaction_on_incompatible_surface_transfers_strategy_not_result() -> None:
    template = successful_record()
    template["evidence_valid"] = True
    different = copy.deepcopy(contract())
    different["reactant_id"] = "co*/pt36"
    different["product_id"] = "c*+o*/pt36"
    different["compatibility"]["material"] = "pt"
    different["compatibility"]["surface"] = "pt111"
    different["compatibility_sha256"] = "different"
    match = rank_templates(build_fingerprint(different), [template])[0]
    assert match["score"] >= 0.60
    assert match["strategy_transferable"] is True
    assert match["result_transferable"] is False
    assert match["transferable"] is False
    assert match["match_level"] == "incompatible_method_branch"
    assert match["strategy_match_level"] == "reaction_event"


def test_reactant_product_identity_prevents_isomer_collision() -> None:
    cho = successful_record()
    cho["evidence_valid"] = True
    different = copy.deepcopy(contract())
    different["reactant_id"] = "c2o*/fe45"
    match = rank_templates(build_fingerprint(different), [cho])[0]
    assert match["chemical_match"] is False
    assert match["strategy_transferable"] is True
    assert match["result_transferable"] is False
    assert match["transferable"] is False


def test_similar_reaction_uses_template_strategy_without_reusing_result() -> None:
    template = successful_record()
    template["evidence_valid"] = True
    different = copy.deepcopy(contract())
    different["reactant_id"] = "co*/fe54"
    different["product_id"] = "c*+o*/fe54"
    query = build_fingerprint(different)
    ranked = rank_templates(query, [template])
    config = yaml.safe_load(
        (ROOT / "configs" / "ts_strategy_engine" / "families.yaml").read_text(
            encoding="utf-8"
        )
    )
    strategy = compose_strategy(query, ranked, config)

    assert strategy["strategy_source"] == "template_transfer"
    assert strategy["template_match"]["strategy_transferable"] is True
    assert strategy["template_match"]["result_transferable"] is False
    assert strategy["result_reuse_policy"] == "forbidden"
    assert "barrier" in strategy["nontransferable_artifacts"]


def test_family_name_without_reaction_event_does_not_transfer_template() -> None:
    template = successful_record()
    template["evidence_valid"] = True
    different = copy.deepcopy(contract())
    different["reactant_id"] = "unrelated_reactant"
    different["product_id"] = "unrelated_product"
    different["broken_bonds"] = [[0, 2]]
    different["site_changes"] = ["different_site_event"]
    query = build_fingerprint(different)
    ranked = rank_templates(query, [template])
    assert ranked[0]["score"] < 0.60
    assert ranked[0]["strategy_transferable"] is False


def test_no_template_uses_family_rule() -> None:
    config = yaml.safe_load((ROOT / "configs" / "ts_strategy_engine" / "families.yaml").read_text(encoding="utf-8"))
    strategy = compose_strategy(fingerprint(), [], config)
    assert strategy["strategy_source"] == "rule_based"
    assert strategy["interpolation_strategy"] == "segmented_idpp"
    assert strategy["neb_settings"]["initial_images"] == 3
    assert "gpu_ml_neb_vasp_validated_triad" in strategy["neb_settings"]["candidate_methods"]
    assert strategy["neb_settings"]["selection_policy"] == "choose_from_reviewed_path_evidence_not_a_fixed_sequence"
    assert strategy["path_initialization"]["waypoint_policy"].startswith("conditional")


def test_reaction_identifier_does_not_change_chemical_fingerprint() -> None:
    same_chemistry = copy.deepcopy(contract())
    same_chemistry["reaction_id"] = "another_local_label"
    assert build_fingerprint(same_chemistry)["fingerprint_id"] == fingerprint()["fingerprint_id"]


def test_failed_experience_requires_correction() -> None:
    record = successful_record()
    record.update(
        outcome="failure",
        validation_grade="C",
        ts_structure_file_id=None,
        ts_validation_id=None,
        barrier_set_id=None,
        failure_cases=["path collapse"],
    )
    with pytest.raises(ValueError, match="correction_strategy"):
        validate_record(record)


def test_healthy_decreasing_neb_continues_without_replanning() -> None:
    analysis = {
        "status": "ANALYZED",
        "path_binding_valid": True,
        "image_sequence_complete": True,
        "scf_failure": False,
        "internal_minimum_warning": False,
        "technically_converged": False,
        "internal_maximum": True,
        "barrierless_candidate": False,
        "images": [
            {"image": "00", "neb_force_trend": "insufficient_data", "ionic_steps": 0, "final_neb_force_eVA": None},
            {"image": "01", "neb_force_trend": "decreasing", "ionic_steps": 5, "final_neb_force_eVA": 0.5},
            {"image": "02", "neb_force_trend": "insufficient_data", "ionic_steps": 0, "final_neb_force_eVA": None},
        ],
    }
    thresholds = {
        "min_ionic_steps_for_force_warning": 3,
        "high_force_warning_threshold_eVA": 1.5,
    }
    decision = decide_search(
        {"status": "PASS"}, analysis, thresholds, False, True,
        scheduler={"job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "CONTINUE_NO_CLIMB_NEB"
    assert decision["ALLOWED_ACTIONS"] == ["CONTINUE_JOB"]


def test_unbound_path_is_never_advanced() -> None:
    analysis = {
        "status": "ANALYZED",
        "path_binding_valid": False,
        "path_binding": {"errors": ["contract_sha256_mismatch"]},
    }
    decision = decide_search({"status": "PASS"}, analysis, {}, True, True)
    assert decision["DECISION"] == "STOP_DATA_INTEGRITY"
    assert decision["ALLOWED_ACTIONS"] == []


def test_bond_changing_template_rejects_plain_idpp() -> None:
    record = successful_record()
    record["interpolation_strategy"] = "idpp"
    with pytest.raises(ValueError, match="bond-changing templates"):
        validate_record(record)


def test_path_and_review_are_checksum_bound_to_contract(tmp_path: Path) -> None:
    active_contract = contract()
    report = tmp_path / "path_generation_report.json"
    report.write_text(
        json.dumps(
            {
                "contract_sha256": active_contract["contract_sha256"],
                "atom_map_sha256": active_contract["atom_map_sha256"],
                "compatibility_sha256": active_contract["compatibility_sha256"],
                "fingerprint_id": fingerprint()["fingerprint_id"],
            }
        ),
        encoding="utf-8",
    )
    dist = tmp_path / "dist.dat"
    movie = tmp_path / "movie.xyz"
    dist.write_text("dist", encoding="ascii")
    movie.write_text("movie", encoding="ascii")
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    review = tmp_path / "path_review.json"
    review.write_text(
        json.dumps(
            {
                "status": "accepted",
                "reviewer": "reviewer",
                "reviewed_at": "2026-01-01",
                "dist_file": dist.name,
                "nebmovie_file": movie.name,
                "dist_sha256": digest(dist),
                "nebmovie_sha256": digest(movie),
                "path_generation_sha256": digest(report),
            }
        ),
        encoding="utf-8",
    )
    assert validate_path_binding(tmp_path, active_contract)["valid"] is True
    assert validate_path_review(review, report)[0] is True
    movie.write_text("changed", encoding="ascii")
    assert validate_path_review(review, report)[0] is False


def test_plan_cli_runs_the_evidence_and_mapping_chain(tmp_path: Path) -> None:
    db = database(tmp_path / "registry.sqlite3")
    structure = Poscar(
        comment="Fe C O",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C", "O"],
        counts=[1, 1, 1],
        frac=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.2], [0.4, 0.0, 0.2]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )
    initial = tmp_path / "IS.POSCAR"
    final = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure)
    write_poscar(final, structure)
    contract_path = tmp_path / "reaction.yaml"
    contract_path.write_text(yaml.safe_dump(contract(), sort_keys=False), encoding="utf-8")
    workdir = tmp_path / "plan"
    plan(
        PlanRequest(
            initial=initial,
            final=final,
            contract=contract_path,
            workdir=workdir,
            database=db,
            families=ROOT / "configs" / "ts_strategy_engine" / "families.yaml",
            thresholds=ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
            initialize_path=False,
            constraints=None,
            waypoint=(),
            output_dir=None,
            images=None,
        )
    )
    strategy = yaml.safe_load((workdir / "ts_strategy.json").read_text(encoding="utf-8"))
    assert strategy["status"] == "NEEDS_GPU_PATH_OR_VASP_PATH_REVIEW"
    assert yaml.safe_load((workdir / "endpoint_evidence.json").read_text(encoding="utf-8"))["status"] == "PASS"


def test_retrieval_decision_record_is_not_treated_as_constraint_path(tmp_path: Path) -> None:
    request = PlanRequest(
        initial=tmp_path / "IS",
        final=tmp_path / "FS",
        contract=tmp_path / "reaction.yaml",
        workdir=tmp_path / "plan",
        database=tmp_path / "registry.sqlite3",
        families=tmp_path / "families.yaml",
        thresholds=tmp_path / "thresholds.yaml",
    )
    assert _resolve_constraints(request, {"retrieval_constraints": {"decision": "NO_TRANSFERABLE_PATH"}}) is None
