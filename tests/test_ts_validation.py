from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from scripts.aqcat25_handoff import sha256_file
from scripts.neb_agent.utils_structure import Poscar, write_poscar
from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
from scripts.ts_strategy_engine.evidence import _validate_ts_payload
from scripts.ts_strategy_engine.execution_evidence import validated_ts
from scripts.ts_validation.analyze_vfa import analyze_vfa
from scripts.ts_validation.connectivity import (
    _aggregate_endpoint_match,
    _classify_structure,
    _evaluate_reaction_connectivity,
    analyze_bidirectional_connectivity,
)
from scripts.ts_validation.prepare_vfa_from_ts_image import prepare_vfa_handoff


def test_dimer_analysis_requires_negative_curvature_and_force(tmp_path: Path) -> None:
    source = _connectivity_structure(2.0)
    write_poscar(tmp_path / "POSCAR", source)
    write_poscar(tmp_path / "CONTCAR", source)
    (tmp_path / "INCAR").write_text(
        "EDIFFG = -0.02\nEDIFF = 1E-5\nNELM = 60\nICHAIN = 2\nDFNMin = 0.01\n",
        encoding="ascii",
    )
    (tmp_path / "DIMCAR").write_text(
        "Step Force Torque Energy Curvature Angle\n1 0.10 0.02 -10.0 -0.4 0.2\n2 0.01 0.01 -10.1 -0.5 0.1\n",
        encoding="ascii",
    )
    (tmp_path / "OUTCAR").write_text(
        "FORCES: max atom, RMS     0.010000 0.001000\n"
        "FORCES: max atom, RMS     9.999999\n"
        "General timing and accounting informations for this job\n",
        encoding="ascii",
    )
    (tmp_path / "OSZICAR").write_text(
        " RMM:   5 -0.10E+02 -0.10E-06 -0.10E-06 100 0.1E-04\n"
        "   1 F= -.10000000E+02 E0= -.10000000E+02 d E=-.100000E-06\n",
        encoding="ascii",
    )
    (tmp_path / "MODECAR").write_text("1 0 0\n", encoding="ascii")
    (tmp_path / "dimer_handoff.json").write_text(
        json.dumps(
            {
                    "source_sha256": sha256_file(tmp_path / "POSCAR"),
                    "contract_sha256": "1" * 64,
                    "atom_map_sha256": "2" * 64,
                    "compatibility_sha256": "3" * 64,
                    "path_generation_sha256": "4" * 64,
            }
        ),
        encoding="utf-8",
    )
    scheduler_stdout = "dimer-job user DONE queue host exec dimer Jul 22 00:00\n"
    (tmp_path / "scheduler_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "scheduler_job_evidence",
                "stage": "dimer",
                "scheduler": "LSF",
                "server_alias": "sunboquan-codex",
                "job_id": "dimer-job",
                "status": "DONE",
                "checked_at": "2026-07-22T00:00:00Z",
                "source_command": "bjobs -a dimer-job",
                "query": {
                    "argv": ["ssh", "sunboquan-codex", "bjobs", "-a", "dimer-job"],
                    "returncode": 0,
                    "stdout": scheduler_stdout,
                    "stderr": "",
                    "stdout_sha256": hashlib.sha256(scheduler_stdout.encode()).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "mode_review.json").write_text(
        json.dumps(
            {
                "status": "accepted",
                "reviewer": "reviewer",
                "reviewed_at": "2026-01-01",
                "modecar_sha256": hashlib.sha256((tmp_path / "MODECAR").read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "final_mode_review.json").write_text(
        json.dumps(
            {
                "status": "accepted",
                "reviewer": "reviewer",
                "reviewed_at": "2026-01-01",
                "modecar_sha256": hashlib.sha256((tmp_path / "MODECAR").read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    payload = analyze_dimer(tmp_path)
    assert payload["status"] == "TECHNICALLY_CONVERGED_NEEDS_FREQUENCY"
    assert payload["technically_converged"] is True
    assert payload["vasp_force_converged"] is True
    assert payload["final_atomic_force_max_eVA"] == 0.01
    assert payload["final_atomic_force_rms_eVA"] == 0.001
    assert payload["vasp_force_convergence_source"] == "OUTCAR:last_complete_FORCES_max_atom"
    assert payload["torque_converged"] is True
    assert payload["scientifically_valid"] is False
    (tmp_path / "DIMCAR").write_text(
        "Step Force Torque Energy Curvature Angle\n1 0.01 0.02 -10.1 -0.5 0.1\n",
        encoding="ascii",
    )
    high_torque = analyze_dimer(tmp_path)
    assert high_torque["torque_converged"] is False
    assert high_torque["technically_converged"] is True
    assert high_torque["status"] == "TECHNICALLY_CONVERGED_SOFT_REVIEW_REQUIRED"
    assert high_torque["dimer_soft_warnings"] == ["DIMER_TORQUE_ABOVE_DFNMIN"]
    (tmp_path / "DIMCAR").write_text(
        "Step Force Torque Energy Curvature Angle\n"
        "1 0.01 0.01 -10.1 -0.5 0.1\n"
        "2 0.02\n",
        encoding="ascii",
    )
    incomplete = analyze_dimer(tmp_path)
    assert incomplete["final_curvature_eVA2"] == -0.5
    assert incomplete["complete_dimcar_rows"] == 1
    (tmp_path / "DIMCAR").write_text(
        "Step Force Torque Energy Curvature Angle\n1 0.01 0.01 -10.1 -0.5 0.1\n",
        encoding="ascii",
    )
    (tmp_path / "MODECAR").write_text("0 1 0\n", encoding="ascii")
    changed = analyze_dimer(tmp_path)
    assert changed["mode_reviewed"] is False
    assert changed["technically_converged"] is False

    (tmp_path / "MODECAR").write_text("1 0 0\n", encoding="ascii")
    (tmp_path / "OUTCAR").write_text(
        "FORCES: max atom, RMS     0.030000 0.001000\n"
        "General timing and accounting informations for this job\n",
        encoding="ascii",
    )
    unconverged_force = analyze_dimer(tmp_path)
    assert unconverged_force["vasp_force_converged"] is False
    assert unconverged_force["technically_converged"] is False


def test_dimer_analysis_rejects_placeholder_files(tmp_path: Path) -> None:
    (tmp_path / "INCAR").write_text("EDIFFG=-0.02\n", encoding="ascii")
    (tmp_path / "DIMCAR").write_text("1 0.01 0.01 -10.0 -0.5 0.1\n", encoding="ascii")
    (tmp_path / "OUTCAR").write_text(
        "General timing and accounting informations for this job\n", encoding="ascii"
    )
    (tmp_path / "CONTCAR").write_text("structure", encoding="ascii")
    payload = analyze_dimer(tmp_path)
    assert payload["technically_converged"] is False
    assert payload["evidence_gate"]["passed"] is False


def test_neb_vfa_rejects_manual_connectivity_booleans_without_vasp_report(tmp_path: Path) -> None:
    contract = {
        "reaction_atoms": [1, 2],
        "contract_sha256": "contract",
        "atom_map_sha256": "mapping",
        "compatibility_sha256": "compatibility",
    }
    (tmp_path / "OUTCAR").write_text(
        """
  1 f/i=   15.0 THz   500.0 cm-1
 X Y Z dx dy dz
 1 0 0 0 0.00 0.00 0.00
 2 0 0 0 0.70 0.00 0.00
 3 0 0 0 -0.70 0.00 0.00
  2 f  =   3.0 THz   100.0 cm-1
 X Y Z dx dy dz
 1 0 0 0 0.00 0.00 0.01
General timing and accounting informations for this job
""",
        encoding="ascii",
    )
    plus = tmp_path / "plus.POSCAR"
    minus = tmp_path / "minus.POSCAR"
    plus.write_text("plus", encoding="ascii")
    minus.write_text("minus", encoding="ascii")
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "status": "accepted",
                "source_method": "neb",
                "validation_calculation_id": "calc_vfa",
                "source_saddle_calculation_id": "calc_ts",
                "source_job_record_id": "job_ts",
                "frequency_output_file_id": "vfa_outcar",
                "positive_displacement_file_id": "mode_plus",
                "negative_displacement_file_id": "mode_minus",
                "contract_sha256": contract["contract_sha256"],
                "atom_map_sha256": contract["atom_map_sha256"],
                "compatibility_sha256": contract["compatibility_sha256"],
                "mode_assignment": "accepted",
                "geometry_status": "pass",
                "connects_to_is": True,
                "connects_to_fs": True,
                "positive_displacement_file": plus.name,
                "negative_displacement_file": minus.name,
                "reviewer": "reviewer",
                "reviewed_at": "2026-01-01",
            }
        ),
        encoding="utf-8",
    )
    payload = analyze_vfa(tmp_path, contract, review)
    assert payload["imaginary_frequency_count"] == 1
    assert payload["principal_mode_reaction_atom_overlap"] == [1, 2]
    assert payload["grade"] == "Ungraded"
    assert payload["connectivity_status"] == "Needs confirmation"
    assert payload["kinetic_eligible"] is False


def test_incomplete_frequency_output_is_ungraded_not_grade_c(tmp_path: Path) -> None:
    contract = {
        "reaction_atoms": [1, 2],
        "contract_sha256": "contract",
        "atom_map_sha256": "mapping",
        "compatibility_sha256": "compatibility",
    }
    (tmp_path / "OUTCAR").write_text(
        "  1 f = 3.0 THz 100.0 cm-1\n 1 0 0 0 0 0 0.01\n",
        encoding="ascii",
    )
    payload = analyze_vfa(
        tmp_path,
        contract,
        None,
        {
            "meaningful_imaginary_frequency_min_cm1": 50.0,
            "additional_soft_mode_abs_max_cm1": 30.0,
        },
    )
    assert payload["normal_completion"] is False
    assert payload["grade"] == "Ungraded"
    assert payload["status"] == "NEEDS_REVIEW"


def test_dimer_grade_a_payload_does_not_require_connectivity() -> None:
    payload = {
        "validation_calculation_id": "calc_vfa",
        "source_saddle_calculation_id": "calc_ts",
        "source_job_record_id": "job_ts",
        "source_method": "dimer",
        "frequency_output_file_id": "vfa_outcar",
        "vfa_handoff": "vfa_handoff.json",
        "vfa_handoff_sha256": "a" * 64,
        "source_saddle_sha256": "b" * 64,
        "frequency_poscar_sha256": "b" * 64,
        "contract_sha256": "c" * 64,
        "atom_map_sha256": "d" * 64,
        "compatibility_sha256": "e" * 64,
        "imaginary_frequency_count": 1,
        "principal_mode_assignment": "accepted",
        "geometry_status": "pass",
        "dimer_technical_acceptance": True,
        "grade": "A",
        "kinetic_eligible": True,
        "reviewer": "reviewer",
        "reviewed_at": "2026-08-06",
    }
    _validate_ts_payload(payload)
    assert validated_ts(
        {
            "source_method": "dimer",
            "grade": "A",
            "source_saddle_sha256": "b" * 64,
            "frequency_poscar_sha256": "b" * 64,
            "dimer_technical_acceptance": True,
        }
    )


def test_non_dimer_grade_a_payload_still_requires_connectivity() -> None:
    payload = {
        "validation_calculation_id": "calc_vfa",
        "source_saddle_calculation_id": "calc_ts",
        "source_job_record_id": "job_ts",
        "source_method": "neb",
        "frequency_output_file_id": "vfa_outcar",
        "vfa_handoff": "vfa_handoff.json",
        "vfa_handoff_sha256": "a" * 64,
        "source_saddle_sha256": "b" * 64,
        "frequency_poscar_sha256": "b" * 64,
        "contract_sha256": "c" * 64,
        "atom_map_sha256": "d" * 64,
        "compatibility_sha256": "e" * 64,
        "grade": "A",
        "kinetic_eligible": True,
    }
    with pytest.raises(ValueError, match="connectivity_report"):
        _validate_ts_payload(payload)


def test_vfa_parser_uses_real_vasp_frequency_row_order(tmp_path: Path) -> None:
    contract = {
        "reaction_atoms": [1, 2],
        "contract_sha256": "contract",
        "atom_map_sha256": "mapping",
        "compatibility_sha256": "compatibility",
    }
    (tmp_path / "OUTCAR").write_text(
        "  1 f/i= 15.0 THz 500.0 cm-1\n"
        " X Y Z dx dy dz\n"
        " 0 0 0 0 0 0\n"
        " 1 0 0 0.7 0 0\n"
        " 2 0 0 -0.7 0 0\n"
        "General timing and accounting informations for this job\n",
        encoding="ascii",
    )
    payload = analyze_vfa(tmp_path, contract, None)
    assert [
        row["atom_index_zero_based"] for row in payload["modes"][0]["dominant_atoms"][:2]
    ] == [1, 2]


def _connectivity_structure(co_distance: float) -> Poscar:
    return Poscar(
        comment="Fe C O",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C", "O"],
        counts=[1, 1, 1],
        frac=np.array([[0.0, 0.0, 0.0], [0.20, 0.20, 0.20], [0.20 + co_distance / 10.0, 0.20, 0.20]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )


def test_large_rmsd_requires_endpoint_review_but_keeps_reaction_connectivity(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.vasp"
    final = tmp_path / "FS.vasp"
    wrong = tmp_path / "wrong.vasp"
    write_poscar(initial, _connectivity_structure(1.2))
    product = _connectivity_structure(3.5)
    write_poscar(final, product)
    shifted = _connectivity_structure(3.5)
    shifted.frac[1:, 1] = (shifted.frac[1:, 1] + 0.4) % 1.0
    shifted.frac[1:, 2] = (shifted.frac[1:, 2] + 0.3) % 1.0
    write_poscar(wrong, shifted)
    result = _classify_structure(
        wrong,
        initial,
        final,
        {"reaction_atoms": [1, 2], "broken_bonds": [[1, 2]], "formed_bonds": []},
    )
    assert result["assigned_endpoint"] == "FS"
    assert result["classification_passed"] is True
    assert result["endpoint_match"] in {"UNRESOLVED", "DIFFERENT_LOCAL_MINIMUM"}
    assert result["geometry_checks"]["reaction_atom_rmsd"] is False

    initial_result = _classify_structure(
        initial,
        initial,
        final,
        {"reaction_atoms": [1, 2], "broken_bonds": [[1, 2]], "formed_bonds": []},
    )
    branches = [
        _state_branch("positive", initial_result),
        _state_branch("negative", result),
    ]
    connectivity = _evaluate_reaction_connectivity(branches)
    endpoint_match, _ = _aggregate_endpoint_match(
        branches, connectivity["reaction_connectivity"]
    )
    assert connectivity["reaction_connectivity"] == "PASS"
    assert endpoint_match in {"UNRESOLVED", "DIFFERENT_LOCAL_MINIMUM"}


def _state_branch(
    direction: str,
    classification: dict | None = None,
    *,
    state: str = "IS",
    state_status: str = "MATCHED",
    converged: bool = True,
) -> dict:
    resolved = classification or {
        "state_classification": {"status": state_status, "state_class": state},
        "endpoint_match": "EXACT",
    }
    return {
        "direction": direction,
        "result_gate": {
            "electronically_converged": converged,
            "ionic_converged": converged,
        },
        "classification": resolved,
    }


def test_reaction_connectivity_accepts_direct_direction() -> None:
    result = _evaluate_reaction_connectivity(
        [_state_branch("positive", state="IS"), _state_branch("negative", state="FS")]
    )
    assert result["reaction_connectivity"] == "PASS"
    assert result["direct_match"] is True


def test_reaction_connectivity_accepts_reversed_direction() -> None:
    result = _evaluate_reaction_connectivity(
        [_state_branch("positive", state="FS"), _state_branch("negative", state="IS")]
    )
    assert result["reaction_connectivity"] == "PASS"
    assert result["reverse_match"] is True


def test_reaction_connectivity_rejects_same_state_on_both_sides() -> None:
    result = _evaluate_reaction_connectivity(
        [_state_branch("positive", state="IS"), _state_branch("negative", state="IS")]
    )
    assert result["reaction_connectivity"] == "FAIL"
    assert result["reason_codes"] == ["BOTH_BRANCHES_REACHED_SAME_STATE"]


def test_reaction_connectivity_is_unresolved_without_convergence_or_state() -> None:
    unconverged = _evaluate_reaction_connectivity(
        [
            _state_branch("positive", state="IS", converged=False),
            _state_branch("negative", state="FS"),
        ]
    )
    assert unconverged["reaction_connectivity"] == "UNRESOLVED"

    unclassified = _evaluate_reaction_connectivity(
        [
            _state_branch(
                "positive", state="UNRESOLVED", state_status="UNRESOLVED"
            ),
            _state_branch("negative", state="FS"),
        ]
    )
    assert unclassified["reaction_connectivity"] == "UNRESOLVED"


def _completed_relaxation(directory: Path, displacement: Path, final: Poscar, job_id: str) -> Path:
    directory.mkdir()
    write_poscar(directory / "POSCAR", _connectivity_structure(2.0))
    displacement.write_bytes((directory / "POSCAR").read_bytes())
    write_poscar(directory / "CONTCAR", final)
    (directory / "INCAR").write_text("EDIFF = 1E-5\nNELM = 60\n", encoding="ascii")
    (directory / "OSZICAR").write_text(
        " RMM:   5 -0.10E+02 -0.10E-06 -0.10E-06 100 0.1E-04\n"
        "   1 F= -.10000000E+02 E0= -.10000000E+02 d E=-.100000E-06\n",
        encoding="ascii",
    )
    (directory / "OUTCAR").write_text(
        "reached required accuracy\nGeneral timing and accounting informations for this job\n",
        encoding="ascii",
    )
    scheduler = directory.parent / f"scheduler_{job_id}.json"
    scheduler.write_text(
        json.dumps(
            {
                "scheduler": "LSF",
                "server_alias": "sunboquan-codex",
                "job_id": job_id,
                "status": "DONE",
                "source_command": f"bjobs -d {job_id}",
            }
        ),
        encoding="utf-8",
    )
    return scheduler


def test_dimer_vfa_grade_a_does_not_require_bidirectional_connectivity(tmp_path: Path) -> None:
    initial = tmp_path / "IS.vasp"
    final = tmp_path / "FS.vasp"
    saddle = tmp_path / "TS.vasp"
    write_poscar(initial, _connectivity_structure(1.2))
    write_poscar(final, _connectivity_structure(3.5))
    write_poscar(saddle, _connectivity_structure(2.0))
    contract_path = tmp_path / "reaction.yaml"
    contract_path.write_text(
        yaml.safe_dump(
            {
                "reaction_id": "co_break",
                "reaction_family": "dissociation",
                "reactant_id": "co",
                "product_id": "c_o",
                "index_base": 1,
                "atom_map": [[1, 1], [2, 2], [3, 3]],
                "reaction_atoms": [2, 3],
                "broken_bonds": [[2, 3]],
                "formed_bonds": [],
                "site_changes": ["co_to_c_o"],
                "compatibility": {
                    "material": "fe",
                    "surface": "110",
                    "branch": "test",
                    "slab_model": "test",
                    "xc": "pbe",
                    "potcar_family": "paw_pbe",
                    "encut_ev": 400,
                    "kmesh": [1, 1, 1],
                    "magnetic_state": "spin",
                    "coverage": "test",
                },
                "endpoints": {
                    "initial": {"calculation_id": "is", "structure_file_id": "isf", "static_result_id": "isr"},
                    "final": {"calculation_id": "fs", "structure_file_id": "fsf", "static_result_id": "fsr"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    frequency = tmp_path / "OUTCAR"
    write_poscar(tmp_path / "POSCAR", _connectivity_structure(2.0))
    frequency.write_text(
        "  1 f/i= 15.0 THz 500.0 cm-1\n"
        " 1 0 0 0 0 0 0\n 2 0 0 0 0.7 0 0\n 3 0 0 0 -0.7 0 0\n"
        "  2 f = 3.0 THz 100.0 cm-1\n 1 0 0 0 0 0 0.01\n"
        "General timing and accounting informations for this job\n",
        encoding="ascii",
    )
    plus_displacement = tmp_path / "plus.POSCAR"
    minus_displacement = tmp_path / "minus.POSCAR"
    plus_run = tmp_path / "plus_run"
    minus_run = tmp_path / "minus_run"
    plus_scheduler = _completed_relaxation(plus_run, plus_displacement, _connectivity_structure(1.25), "plus-job")
    minus_scheduler = _completed_relaxation(minus_run, minus_displacement, _connectivity_structure(3.45), "minus-job")
    report_path = tmp_path / "connectivity.json"
    report = analyze_bidirectional_connectivity(
        contract_path=contract_path,
        initial_path=initial,
        final_path=final,
        saddle_path=saddle,
        frequency_outcar=frequency,
        positive_run=plus_run,
        positive_displacement=plus_displacement,
        positive_scheduler=plus_scheduler,
        negative_run=minus_run,
        negative_displacement=minus_displacement,
        negative_scheduler=minus_scheduler,
        output=report_path,
    )
    assert report["status"] == "PASS"
    contract = {
        "reaction_atoms": [1, 2],
        "contract_sha256": report["contract_sha256"],
        "atom_map_sha256": report["atom_map_sha256"],
        "compatibility_sha256": report["compatibility_sha256"],
    }
    vfa_handoff = tmp_path / "vfa_handoff.json"
    saddle_analysis = tmp_path / "dimer_analysis.json"
    saddle_analysis.write_text(
        json.dumps(
            {
                "technically_converged": True,
                "negative_curvature": True,
                "vasp_force_converged": True,
                "force_converged": True,
                "torque_converged": True,
                "dimer_soft_gate_passed": True,
                "contract_bound": True,
                "mode_reviewed": True,
                "final_mode_reviewed": True,
                "normal_completion": True,
                "fatal_keywords": [],
            }
        ),
        encoding="utf-8",
    )
    vfa_handoff.write_text(
        json.dumps(
            {
                "source_sha256": sha256_file(saddle),
                "source_ts_candidate": str(saddle),
                "frequency_poscar_sha256": sha256_file(tmp_path / "POSCAR"),
                "contract_sha256": report["contract_sha256"],
                "atom_map_sha256": report["atom_map_sha256"],
                "compatibility_sha256": report["compatibility_sha256"],
                "source_method": "dimer",
                "saddle_analysis_source": str(saddle_analysis),
                "saddle_analysis_sha256": sha256_file(saddle_analysis),
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "status": "accepted",
                "source_method": "dimer",
                "validation_calculation_id": "calc_vfa",
                "source_saddle_calculation_id": "calc_ts",
                "source_job_record_id": "job_ts",
                "frequency_output_file_id": "vfa_outcar",
                "contract_sha256": report["contract_sha256"],
                "atom_map_sha256": report["atom_map_sha256"],
                "compatibility_sha256": report["compatibility_sha256"],
                "mode_assignment": "accepted",
                "geometry_status": "pass",
                "vfa_handoff": vfa_handoff.name,
                "vfa_handoff_sha256": sha256_file(vfa_handoff),
                "reviewer": "reviewer",
                "reviewed_at": "2026-01-01",
            }
        ),
        encoding="utf-8",
    )
    frequency_policy = {
        "meaningful_imaginary_frequency_min_cm1": 50.0,
        "additional_soft_mode_abs_max_cm1": 30.0,
    }
    assert analyze_vfa(tmp_path, contract, review)["grade"] == "Ungraded"
    analysis = analyze_vfa(tmp_path, contract, review, frequency_policy)
    assert analysis["grade"] == "A"
    assert analysis["connectivity_required"] is False
    assert analysis["connectivity_job_ids"] == []

    original_poscar = (tmp_path / "POSCAR").read_bytes()
    (tmp_path / "POSCAR").write_bytes(original_poscar + b"\n")
    assert analyze_vfa(tmp_path, contract, review, frequency_policy)["grade"] == "Ungraded"
    (tmp_path / "POSCAR").write_bytes(original_poscar)
    original_saddle = saddle.read_bytes()
    saddle.write_bytes(original_saddle + b"\n")
    assert analyze_vfa(tmp_path, contract, review, frequency_policy)["grade"] == "Ungraded"
    saddle.write_bytes(original_saddle)

    frequency.write_text(
        "  1 f/i= 15.0 THz 500.0 cm-1\n"
        " 1 0 0 0 0 0 0\n 2 0 0 0 0.7 0 0\n 3 0 0 0 -0.7 0 0\n"
        "  2 f/i= 0.3 THz 10.0 cm-1\n"
        " 1 0 0 0 0.01 0 0\n 2 0 0 0 0.01 0 0\n"
        "General timing and accounting informations for this job\n",
        encoding="ascii",
    )
    report["frequency_outcar"]["sha256"] = sha256_file(frequency)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    review_payload = json.loads(review.read_text(encoding="utf-8"))
    review_payload.update(
        {
            "status": "manual_review",
            "principal_mode_index": 1,
            "soft_mode_assessment": "one_additional_small_soft_mode_repeat_required",
            "repeat_required": True,
            "connectivity_report_sha256": sha256_file(report_path),
        }
    )
    review.write_text(json.dumps(review_payload, indent=2), encoding="utf-8")
    grade_b = analyze_vfa(tmp_path, contract, review, frequency_policy)
    assert grade_b["grade"] == "B"
    assert grade_b["kinetic_eligible"] is False
    assert grade_b["repeat_required"] is True

    shifted = _connectivity_structure(1.25)
    shifted.frac[1:, 1] = (shifted.frac[1:, 1] + 0.4) % 1.0
    shifted.frac[1:, 2] = (shifted.frac[1:, 2] + 0.3) % 1.0
    write_poscar(plus_run / "CONTCAR", shifted)
    unresolved = analyze_bidirectional_connectivity(
        contract_path=contract_path,
        initial_path=initial,
        final_path=final,
        saddle_path=saddle,
        frequency_outcar=frequency,
        positive_run=plus_run,
        positive_displacement=plus_displacement,
        positive_scheduler=plus_scheduler,
        negative_run=minus_run,
        negative_displacement=minus_displacement,
        negative_scheduler=minus_scheduler,
        output=tmp_path / "connectivity_review.json",
    )
    assert unresolved["status"] == "PASS"
    assert unresolved["reaction_connectivity"] == "PASS"
    assert unresolved["endpoint_match"] in {
        "UNRESOLVED",
        "DIFFERENT_LOCAL_MINIMUM",
    }
    assert unresolved["overall_status"] in {
        "NEEDS_REVIEW",
        "VALIDATED_DIFFERENT_ENDPOINT",
    }
    if unresolved["endpoint_match"] == "UNRESOLVED":
        assert unresolved["summary"] == (
            "TS 两侧分别连接预期的 IS 和 FS 状态类别，因此反应连通性通过。"
            "实际端点与参考端点是否属于同一个局部极小值尚未确认，"
            "需要进一步检查周期等价性、局部配位或结构对称性。"
        )
    assert unresolved["grade_a_connectivity_eligible"] is False


def test_vfa_handoff_requires_contract_bound_saddle_analysis(tmp_path: Path) -> None:
    contract = {
        "reaction_atoms": [1, 2],
        "contract_sha256": "contract",
        "atom_map_sha256": "mapping",
        "compatibility_sha256": "compatibility",
    }
    source = tmp_path / "dimer"
    write_poscar(
        source / "CONTCAR",
        Poscar(
            comment="Fe C O",
            cell=np.eye(3) * 10.0,
            symbols=["Fe", "C", "O"],
            counts=[1, 1, 1],
            frac=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.2], [0.4, 0.0, 0.2]]),
            selective=True,
            flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
        ),
    )
    analysis = source / "dimer_analysis.json"
    analysis.write_text(
        json.dumps(
            {
                "status": "TECHNICALLY_CONVERGED_SOFT_REVIEW_REQUIRED",
                "technically_converged": True,
                "negative_curvature": True,
                "vasp_force_converged": True,
                "force_converged": False,
                "dimer_force_converged": False,
                "torque_converged": False,
                "dimer_soft_gate_passed": False,
                "dimer_soft_warnings": [
                    "DIMER_FORCE_ABOVE_TARGET",
                    "DIMER_TORQUE_ABOVE_DFNMIN",
                ],
                "contract_bound": True,
                "mode_reviewed": True,
                "final_mode_reviewed": True,
                "normal_completion": True,
                "fatal_keywords": [],
                **{key: contract[key] for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")},
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "vfa"
    with pytest.raises(SystemExit, match="VFA requires"):
        prepare_vfa_handoff(source, destination, [1, 2], contract, analysis, False)
    soft_review = source / "dimer_soft_gate_review.json"
    soft_review.write_text(
        json.dumps(
            {
                "status": "accepted",
                "decision": "allow_frequency_handoff",
                "reviewer": "user",
                "reviewed_at": "2026-08-05T00:00:00Z",
                "saddle_analysis_sha256": sha256_file(analysis),
                "source_structure_sha256": sha256_file(source / "CONTCAR"),
                "acknowledged_warning_codes": [
                    "DIMER_FORCE_ABOVE_TARGET",
                    "DIMER_TORQUE_ABOVE_DFNMIN",
                ],
            }
        ),
        encoding="utf-8",
    )
    prepare_vfa_handoff(
        source,
        destination,
        [1, 2],
        contract,
        analysis,
        False,
        soft_review,
    )
    manifest = json.loads((destination / "vfa_handoff.json").read_text(encoding="utf-8"))
    assert manifest["contract_sha256"] == contract["contract_sha256"]
    assert manifest["submitted"] is False
    assert manifest["dimer_frequency_gate"]["manual_review_decision"] == "allow_frequency_handoff"
    assert manifest["dimer_frequency_gate"]["ts_validation_eligible"] is False

    bad = dict(contract)
    bad["contract_sha256"] = "other"
    with pytest.raises(SystemExit, match="does not match"):
        prepare_vfa_handoff(source, tmp_path / "bad", [1, 2], bad, analysis, False)
