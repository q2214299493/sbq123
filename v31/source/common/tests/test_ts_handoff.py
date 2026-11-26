from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.neb_agent.utils_structure import Poscar, write_poscar
from scripts.artifact_io import sha256_file
from scripts.ts_strategy_engine.dimer_gate import evaluate_candidate_triad
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.handoff import prepare_dimer_handoff, prepare_ts_handoff, resolve_ts_candidate


def test_resolve_ts_candidate_prefers_contcar_and_falls_back_to_poscar(tmp_path: Path) -> None:
    image = tmp_path / "03"
    image.mkdir()
    poscar = image / "POSCAR"
    poscar.write_text("initial", encoding="ascii")
    assert resolve_ts_candidate(image) == poscar
    contcar = image / "CONTCAR"
    contcar.write_text("relaxed", encoding="ascii")
    assert resolve_ts_candidate(image) == contcar


def test_prepare_ts_handoff_writes_one_shared_contract(tmp_path: Path) -> None:
    source = tmp_path / "CONTCAR"
    source.write_text("candidate", encoding="ascii")
    destination = tmp_path / "handoff"
    prepare_ts_handoff(
        source,
        destination,
        handoff_name="TEST",
        manifest_name="handoff.json",
        manifest_fields={"submitted": False},
        dry_run=False,
    )
    assert (destination / "POSCAR").read_text(encoding="ascii") == "candidate"
    manifest = json.loads((destination / "handoff.json").read_text(encoding="utf-8"))
    assert manifest["source_ts_candidate"] == str(source)
    assert manifest["source_sha256"]
    assert manifest["submitted"] is False
    assert not (destination / "README.md").exists()


def test_prepare_ts_handoff_is_non_destructive_in_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "POSCAR"
    source.write_text("candidate", encoding="ascii")
    destination = tmp_path / "handoff"
    prepare_ts_handoff(
        source,
        destination,
        handoff_name="TEST",
        manifest_name="handoff.json",
        manifest_fields={},
        dry_run=True,
    )
    assert not destination.exists()
    destination.mkdir()
    with pytest.raises(SystemExit, match="never overwrites"):
        prepare_ts_handoff(
            source,
            destination,
            handoff_name="TEST",
            manifest_name="handoff.json",
            manifest_fields={},
            dry_run=True,
        )


def test_dimer_handoff_generates_reviewable_modecar(tmp_path: Path) -> None:
    def structure(c_x: float) -> Poscar:
        return Poscar(
            comment="Fe C O",
            cell=np.eye(3) * 10.0,
            symbols=["Fe", "C", "O"],
            counts=[1, 1, 1],
            frac=np.array([[0.0, 0.0, 0.0], [c_x, 0.0, 0.2], [0.4, 0.0, 0.2]]),
            selective=True,
            flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
        )

    images = tmp_path / "path"
    for name, value in (("00", structure(0.20)), ("01", structure(0.25)), ("02", structure(0.30))):
        write_poscar(images / name / "POSCAR", value)
    analysis = tmp_path / "neb_analysis.json"
    binding = {
        "contract_sha256": "contract",
        "atom_map_sha256": "mapping",
        "compatibility_sha256": "compatibility",
        "report_sha256": "path-report",
    }
    analysis.write_text(
        json.dumps(
            {
                "parent_neb_method": "ordinary_neb",
                "maximum_image": "01",
                "technically_converged": False,
                "geometry_validated": True,
                "path_reviewed": True,
                "path_binding_valid": True,
                "internal_maximum": True,
                "images": [
                    {
                        "image": "00",
                        "has_output": True,
                        "normal_completion": True,
                        "electronically_converged": True,
                        "final_energy_eV": -10.0,
                        "final_atomic_force_eVA": 0.20,
                        "atomic_force_history_last10_eVA": [0.6, 0.2],
                    },
                    {
                        "image": "01",
                        "has_output": True,
                        "normal_completion": True,
                        "electronically_converged": True,
                        "final_energy_eV": -9.0,
                        "final_atomic_force_eVA": 0.25,
                        "atomic_force_history_last10_eVA": [0.7, 0.25],
                    },
                    {
                        "image": "02",
                        "has_output": True,
                        "normal_completion": True,
                        "electronically_converged": True,
                        "final_energy_eV": -9.5,
                        "final_atomic_force_eVA": 0.20,
                        "atomic_force_history_last10_eVA": [0.5, 0.2],
                    },
                ],
                **{key: binding[key] for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")},
            }
        ),
        encoding="utf-8",
    )
    dist = tmp_path / "dist.dat"
    movie = tmp_path / "movie.xyz"
    dist.write_text("review", encoding="ascii")
    movie.write_text("review", encoding="ascii")
    review = tmp_path / "path_review.json"
    review.write_text(
        json.dumps(
            {
                "status": "accepted",
                "reviewer": "reviewer",
                "reviewed_at": "2026-01-01",
                "dist_file": str(dist),
                "nebmovie_file": str(movie),
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "dimer"
    gate = decide_execution(
        {"status": "PASS"},
        {
            "path_binding_valid": True,
            "image_sequence_complete": True,
            "technically_converged": False,
            "internal_maximum": True,
            "images": [{}, {}],
        },
        {
            "min_ionic_steps_for_force_warning": 3,
            "high_force_warning_threshold_eVA": 1.5,
        },
        climb=True,
        path_reviewed=True,
        path_quality={"PATH_QUALITY_STATUS": "UNDERRESOLVED_REACTION_COORDINATE"},
        authorization={"action": "PREPARE_DIMER_HANDOFF"},
    )
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    prepare_dimer_handoff(
        images / "01",
        images / "00",
        images / "02",
        destination,
        False,
        analysis_path=analysis,
        path_review_path=review,
        reaction_indices=[1, 2],
        contract_binding=binding,
        gate_decision=gate_path,
        gate_state_sha256=gate["state_sha256"],
    )
    rows = [[float(value) for value in line.split()] for line in (destination / "MODECAR").read_text().splitlines()]
    assert len(rows) == 3
    assert np.isclose(np.linalg.norm(np.array(rows)), 1.0)
    assert rows[0] == [0.0, 0.0, 0.0]
    manifest = json.loads((destination / "dimer_handoff.json").read_text(encoding="utf-8"))
    assert manifest["candidate_hard_gate"]["hard_gate_passed"] is True
    assert manifest["recommended_gate"]["parent_neb_technically_converged"] is False


def test_gpu_ml_neb_parent_requires_complete_path_and_exact_vasp_triad(tmp_path: Path) -> None:
    def structure(c_x: float) -> Poscar:
        return Poscar(
            comment="Fe C H",
            cell=np.eye(3) * 10.0,
            symbols=["Fe", "C", "H"],
            counts=[1, 1, 1],
            frac=np.array([[0.0, 0.0, 0.0], [c_x, 0.0, 0.2], [0.4, 0.0, 0.2]]),
            selective=True,
            flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
        )

    images_root = tmp_path / "gpu_path"
    image_paths: list[Path] = []
    for name, value in (("00", structure(0.20)), ("01", structure(0.25)), ("02", structure(0.30))):
        path = images_root / name / "POSCAR"
        write_poscar(path, value)
        image_paths.append(path)
    structure_hashes = [sha256_file(path) for path in image_paths]
    contract_hash, atom_map_hash, compatibility_hash = "a" * 64, "b" * 64, "c" * 64
    checkpoint_hash = "d" * 64
    source_handoff = tmp_path / "handoff.json"
    source_handoff.write_text("{}", encoding="utf-8")
    exit_record = tmp_path / "producer_exit_record.json"
    exit_record.write_text(
        json.dumps({"gpu_job_id": "12", "status": "success", "exit_code": 0}), encoding="utf-8"
    )
    candidate_manifest_source = tmp_path / "gpu_ml_neb_path_manifest.candidate.json"
    candidate_manifest_source.write_text("{}", encoding="utf-8")
    path_review_source = tmp_path / "gpu_ml_neb_path_review.json"
    path_review_source.write_text("{}", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "document_kind": "gpu_ml_neb_path_manifest",
        "status": "accepted_for_vasp_validated_dimer_parent",
        "result_class": "predicted_path_candidate_only",
        "source_handoff": {"path": source_handoff.name, "sha256": sha256_file(source_handoff)},
        "checkpoint_sha256": checkpoint_hash,
        "model_identifier": "AQCat25 test",
        "runner_sha256": "9" * 64,
        "run_settings": {"images_per_segment": 3},
        "contract_sha256": contract_hash,
        "atom_map_sha256": atom_map_hash,
        "compatibility_sha256": compatibility_hash,
        "adjacent_rmsd_A": [0.5, 0.5],
        "path_review": {
            "geometry_continuity": "accepted",
            "periodic_mapping": "accepted",
            "reaction_coordinate_resolution": "accepted",
            "elementary_step_assignment": "accepted",
            "numeric_screen": {
                "adjacent_rmsd_passed": True,
                "periodic_branch_numeric_passed": True,
                "minimum_pair_distance_passed": True,
                "single_strict_internal_peak": True,
            },
        },
        "source_candidate_manifest_file": candidate_manifest_source.name,
        "source_candidate_manifest_sha256": sha256_file(candidate_manifest_source),
        "path_review_file": path_review_source.name,
        "path_review_sha256": sha256_file(path_review_source),
        "producer": {"backend": "aqcat_gpu", "hostname": "MZ73", "gpu_job_id": "12"},
        "producer_exit_record": {
            "path": exit_record.name,
            "sha256": sha256_file(exit_record),
            "status": "success",
            "exit_code": 0,
            "evidence_class": "producer_process_only_not_scheduler_accounting",
        },
        "restrictions": {
            "predicted_candidate_only": True,
            "reportable_dft": False,
            "automatic_vasp_submission": False,
            "dimer_parent_accepted": True,
        },
        "images": [
            {
                "image": name,
                "structure_path": f"gpu_path/{name}/POSCAR",
                "structure_sha256": digest,
                "predicted_energy_eV": energy,
                "predicted_physical_force_max_eVA": 0.12,
                "projected_neb_force_max_eVA": 0.08,
                "spring_force_max_eVA": 0.03,
                "reaction_coordinate_value": coordinate,
                "minimum_pair_distance_A": 1.0,
                "key_bond_distances_A": {"form:2-3": coordinate},
            }
            for name, digest, energy, coordinate in zip(
                ("00", "01", "02"), structure_hashes, (-10.0, -9.0, -9.5), (2.0, 1.7, 1.4)
            )
        ],
    }
    manifest_path = tmp_path / "gpu_ml_neb_path_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dft_hash = "e" * 64
    rows = [
        {
            "image": name,
            "has_output": True,
            "normal_completion": True,
            "electronically_converged": True,
            "final_energy_eV": energy,
            "final_atomic_force_eVA": 0.15,
            "structure_sha256": digest,
            "force_source": "vasp_exact_structure_static",
            "scheduler_evidence_accepted": True,
            "dft_fingerprint_sha256": dft_hash,
        }
        for name, digest, energy in zip(("00", "01", "02"), structure_hashes, (-10.0, -9.0, -9.5))
    ]
    analysis = {
        "parent_neb_method": "gpu_ml_neb_vasp_validated_triad",
        "contract_sha256": contract_hash,
        "atom_map_sha256": atom_map_hash,
        "compatibility_sha256": compatibility_hash,
        "images": rows,
        "gpu_ml_neb_parent_evidence": {
            "path_manifest_file": manifest_path.name,
            "path_manifest_sha256": sha256_file(manifest_path),
            "reliability_route": "exact_vasp_triad_force_agreement",
            "force_agreement": {
                "comparison_sha256": "f" * 64,
                "checkpoint_sha256": checkpoint_hash,
                "structure_sha256": structure_hashes,
                "component_mae_eV_per_A": 0.05,
                "vector_rmse_eV_per_A": 0.10,
                "vector_max_eV_per_A": 0.30,
            },
        },
    }

    passed = evaluate_candidate_triad(
        image_paths[0], image_paths[1], image_paths[2], analysis, [1, 2], analysis_root=tmp_path
    )
    assert passed["hard_gate_passed"] is True
    assert passed["parent_method"] == "gpu_ml_neb_vasp_validated_triad"
    assert passed["gpu_ml_neb_parent_evidence"]["local_force_agreement_passed"] is True

    rows[1]["scheduler_evidence_accepted"] = False
    blocked = evaluate_candidate_triad(
        image_paths[0], image_paths[1], image_paths[2], analysis, [1, 2], analysis_root=tmp_path
    )
    assert blocked["hard_gate_passed"] is False
    assert "gpu_vasp_triad_exact_structure_force_labels" in blocked["hard_gate_errors"]
