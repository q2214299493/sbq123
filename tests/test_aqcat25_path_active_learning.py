from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import FixAtoms
from ase.io import write

from scripts.aqcat25_handoff import atom_order_sha256
from scripts.aqcat25_ml_path_committee import (
    assess_path_committee,
    prepare_committee_request,
)
from scripts.artifact_io import sha256_file
from scripts.ts_strategy_engine.active_learning_path import (
    assess_path_force_predictions,
    ingest_path_vasp_force_labels,
    initialize_path_workflow,
    prepare_path_force_predictions,
    prepare_path_vasp_force_labels,
)
from scripts.ts_strategy_engine.active_learning_common import load_state
from scripts.ts_strategy_engine.active_learning_training import (
    prepare_finetuning_package,
    register_finetuning_result,
)
from scripts.ts_strategy_engine.contract import normalize_contract


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "configs" / "aqcat25_ts_active_learning.yaml"


class OffsetCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, offset: float):
        super().__init__()
        self.offset = offset

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        forces = np.zeros((len(atoms), 3), dtype=float)
        forces[-1, 0] = self.offset
        self.results = {"energy": self.offset, "forces": forces}


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _structure_ref(path: Path, atoms: Atoms, root: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "format": "vasp_poscar",
        "atom_count": len(atoms),
        "atom_order_sha256": atom_order_sha256(atoms.get_chemical_symbols()),
    }


def _path_fixture(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    initial = Atoms(
        ["Fe", "C", "H"],
        positions=[[1.0, 1.0, 1.0], [4.0, 1.0, 2.0], [6.0, 1.0, 2.0]],
        cell=[10.0, 10.0, 12.0],
        pbc=True,
    )
    initial.set_constraint(FixAtoms(indices=[0]))
    final = initial.copy()
    final.positions[-1, 0] = 5.0
    initial_path = source_root / "IS.vasp"
    final_path = source_root / "FS.vasp"
    write(initial_path, initial, format="vasp", direct=True, vasp5=True)
    write(final_path, final, format="vasp", direct=True, vasp5=True)
    checkpoints = []
    for index in range(3):
        checkpoint = tmp_path / f"member_{index}.pt"
        checkpoint.write_bytes(f"checkpoint-{index}".encode())
        checkpoints.append(checkpoint)
    contract = normalize_contract(
        {
            "reaction_id": "fixture_c_h_to_ch",
            "reaction_family": "hydrogen_transfer",
            "reactant_id": "fixture_c_h",
            "product_id": "fixture_ch",
            "index_base": 0,
            "atom_map": [{"is": index, "fs": index} for index in range(3)],
            "reaction_atoms": [1, 2],
            "broken_bonds": [],
            "formed_bonds": [[1, 2]],
            "site_changes": ["H:bridge->CH"],
            "compatibility": {
                "material": "fe",
                "surface": "fe110",
                "branch": "fixture_fe110",
                "slab_model": "fixture_fixed_fe",
                "xc": "pbe",
                "potcar_family": "paw_pbe",
                "encut_ev": 400.0,
                "kmesh": [5, 5, 1],
                "magnetic_state": "ispin2_ferromagnetic_fe",
                "coverage": "fixture",
            },
            "endpoints": {
                "initial": {
                    "calculation_id": "fixture-is",
                    "structure_file_id": "fixture-is-poscar",
                    "static_result_id": "fixture-is-energy",
                },
                "final": {
                    "calculation_id": "fixture-fs",
                    "structure_file_id": "fixture-fs-poscar",
                    "static_result_id": "fixture-fs-energy",
                },
            },
        }
    )
    contract_path = _write_json(tmp_path / "contract.json", contract)
    initial_ref = _structure_ref(initial_path, initial, source_root)
    final_ref = _structure_ref(final_path, final, source_root)
    transition = {
        "normalized_reaction_contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "initial_structure": initial_ref,
        "waypoint_structures": [],
        "final_structure": final_ref,
        "indexed_bond_changes": [{"atoms_1based": [2, 3], "change": "form"}],
    }
    restrictions = {
        "predicted_candidate_only": True,
        "submit_vasp": False,
        "scientific_acceptance": False,
        "direct_gpu_to_vasp_handoff": False,
    }
    handoff = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": "fixture-path",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": "0" * 64,
        "candidate_structure": initial_ref,
        "compatibility": {
            "branch": "fixture_fe110",
            "sha256": contract["compatibility_sha256"],
            "slab_model": "fixture_fixed_fe",
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": "AQCat25 fixture",
            "checkpoint_sha256": sha256_file(checkpoints[0]),
            "fmax_eV_per_A": 0.10,
            "max_steps": 50,
        },
        "selective_dynamics": {"fixed_atom_indices_1based": [1], "free_atom_count": 2},
        "transition_state": transition,
        "restrictions": restrictions,
    }
    handoff_path = _write_json(source_root / "handoff.json", handoff)
    path_root = tmp_path / "path"
    energies = [0.0, 0.3, 0.7, 1.2, 0.8, 0.4, 0.1]
    rows = []
    for index, energy in enumerate(energies):
        atoms = initial.copy()
        atoms.positions[-1, 0] = 6.0 - index / (len(energies) - 1)
        image_path = path_root / "images" / f"{index:02d}" / "POSCAR"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        write(image_path, atoms, format="vasp", direct=True, vasp5=True)
        rows.append(
            {
                "image": f"{index:02d}",
                "structure_path": image_path.relative_to(path_root).as_posix(),
                "structure_sha256": sha256_file(image_path),
                "predicted_energy_eV": energy,
                "predicted_physical_force_max_eVA": 0.2,
                "projected_neb_force_max_eVA": 0.1,
                "spring_force_max_eVA": 0.1,
                "reaction_coordinate_value": index / (len(energies) - 1),
                "key_bond_distances_A": {"2-3:form": 2.0 - index / 6},
                "minimum_pair_distance_A": 1.0,
                "model_disagreement": None,
                "model_disagreement_reason": "single_checkpoint_has_no_committee_disagreement",
                "uncertainty_status": "single_checkpoint_no_per_image_uncertainty",
            }
        )
    exit_record = _write_json(
        path_root / "producer_exit_record.json",
        {"gpu_job_id": "fixture-1", "status": "success", "exit_code": 0},
    )
    manifest = {
        "schema_version": 1,
        "document_kind": "gpu_ml_neb_path_manifest",
        "status": "needs_work_review",
        "result_class": "predicted_path_candidate_only",
        "source_handoff": {
            "path": Path(os.path.relpath(handoff_path, path_root)).as_posix(),
            "sha256": sha256_file(handoff_path),
        },
        "checkpoint_sha256": sha256_file(checkpoints[0]),
        "model_identifier": "AQCat25 fixture",
        "runner_sha256": "1" * 64,
        "contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility_sha256": contract["compatibility_sha256"],
        "run_settings": {"images_per_segment": 7, "ml_ci": "auto"},
        "producer": {"backend": "aqcat_gpu", "gpu_job_id": "fixture-1"},
        "producer_exit_record": {
            "path": exit_record.name,
            "sha256": sha256_file(exit_record),
            "status": "success",
            "exit_code": 0,
        },
        "images": rows,
        "adjacent_rmsd_A": [0.2] * (len(rows) - 1),
        "path_review": {
            "geometry_continuity": "needs_review",
            "periodic_mapping": "needs_review",
            "reaction_coordinate_resolution": "needs_review",
            "elementary_step_assignment": "needs_review",
            "numeric_screen": {
                "adjacent_rmsd_passed": True,
                "periodic_branch_numeric_passed": True,
                "minimum_pair_distance_passed": True,
                "single_strict_internal_peak": True,
                "strict_internal_peak_images": ["03"],
            },
        },
        "vasp_label_candidates": [
            {"image": "02", "reasons": ["peak_left_neighbor"]},
            {"image": "03", "reasons": ["highest_predicted_energy"]},
            {"image": "04", "reasons": ["peak_right_neighbor"]},
            {"image": "05", "reasons": ["largest_adjacent_rmsd_link"]},
        ],
        "restrictions": {
            "predicted_candidate_only": True,
            "reportable_dft": False,
            "automatic_vasp_submission": False,
            "dimer_parent_accepted": False,
        },
    }
    manifest_path = _write_json(path_root / "gpu_ml_neb_path_manifest.candidate.json", manifest)
    return manifest_path, contract_path, checkpoints


def _write_completed_label(label_dir: Path) -> None:
    count = sum(int(value) for value in (label_dir / "POSCAR").read_text().splitlines()[6].split())
    rows = [f" {index:4d} 0 0 0.001 0.00000000 0.00000000" for index in range(count)]
    (label_dir / "OUTCAR").write_text(
        " free  energy   TOTEN  =       -10.5000 eV\n"
        " TOTAL-FORCE (eV/Angst)\n"
        " -------------------------------------------------------------------\n"
        + "\n".join(rows)
        + "\n\nGeneral timing and accounting informations for this job:\n",
        encoding="ascii",
    )
    (label_dir / "OSZICAR").write_text(
        " RMM:   5   -0.105E+02   -0.1E-07   -0.1E-08  100  0.1E-04\n"
        "   1 F= -.105E+02 E0= -.105E+02 d E =-.1E-07\n",
        encoding="ascii",
    )


def _scheduler(job_id: str) -> dict:
    stdout = f"JOBID USER STAT\n{job_id} user DONE\n"
    return {
        "schema_version": 1,
        "document_kind": "scheduler_job_evidence",
        "stage": "vasp_force_label",
        "scheduler": "LSF",
        "server_alias": "sunboquan-codex",
        "job_id": job_id,
        "status": "DONE",
        "checked_at": "2026-08-19T00:00:00Z",
        "source_command": f"ssh sunboquan-codex bjobs -a {job_id}",
        "query": {
            "argv": ["ssh", "sunboquan-codex", "bjobs", "-a", job_id],
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        },
    }


def _live(job_id: str, *, stage: str) -> dict:
    return _scheduler(job_id)


def test_path_controller_prepares_and_ingests_one_hash_bound_vasp_batch(tmp_path: Path) -> None:
    path_manifest, contract, _ = _path_fixture(tmp_path)
    root = tmp_path / "active_learning"
    state = initialize_path_workflow(path_manifest, contract, POLICY, root)
    selected = state["rounds"][0]["path_selection"]["selected_images"]
    assert {"02", "03", "04"}.issubset({row["image"] for row in selected})
    batch = prepare_path_vasp_force_labels(root / "active_learning_state.json", tmp_path / "labels")
    assert batch["submission_policy"]["automatic_submission"] is False
    evidence_rows = []
    for row in batch["labels"]:
        label_dir = tmp_path / "labels" / row["directory"]
        _write_completed_label(label_dir)
        evidence_path = _write_json(tmp_path / f"scheduler_{row['image']}.json", _scheduler(row["image"]))
        evidence_rows.append(
            {
                "image": row["image"],
                "scheduler_evidence": evidence_path.name,
                "scheduler_evidence_sha256": sha256_file(evidence_path),
            }
        )
    evidence = _write_json(
        tmp_path / "batch_evidence.json",
        {
            "document_kind": "vasp_ts_force_label_batch_evidence",
            "source_batch_request_sha256": sha256_file(
                tmp_path / "labels" / "path_label_batch_request.json"
            ),
            "labels": evidence_rows,
        },
    )
    result = ingest_path_vasp_force_labels(
        root / "active_learning_state.json", evidence, live_query=_live
    )
    assert len(result["reports"]) == len(selected)
    assert load_state(root / "active_learning_state.json")["status"] == (
        "awaiting_path_ml_prediction_preparation"
    )


def test_path_force_comparison_aggregates_all_selected_images(tmp_path: Path) -> None:
    path_manifest, contract, _ = _path_fixture(tmp_path)
    root = tmp_path / "active_learning"
    initialize_path_workflow(path_manifest, contract, POLICY, root)
    batch = prepare_path_vasp_force_labels(root / "active_learning_state.json", tmp_path / "labels")
    evidence_rows = []
    for row in batch["labels"]:
        _write_completed_label(tmp_path / "labels" / row["directory"])
        evidence_path = _write_json(tmp_path / f"scheduler_{row['image']}.json", _scheduler(row["image"]))
        evidence_rows.append(
            {
                "image": row["image"],
                "scheduler_evidence": evidence_path.name,
                "scheduler_evidence_sha256": sha256_file(evidence_path),
            }
        )
    evidence = _write_json(
        tmp_path / "batch_evidence.json",
        {
            "document_kind": "vasp_ts_force_label_batch_evidence",
            "source_batch_request_sha256": sha256_file(tmp_path / "labels" / "path_label_batch_request.json"),
            "labels": evidence_rows,
        },
    )
    ingest_path_vasp_force_labels(root / "active_learning_state.json", evidence, live_query=_live)
    prediction_batch = prepare_path_force_predictions(
        root / "active_learning_state.json", tmp_path / "predictions"
    )
    assert all("\\" not in row["request"] for row in prediction_batch["predictions"])
    state = load_state(root / "active_learning_state.json")
    labels = {row["image"]: row for row in state["rounds"][-1]["path_vasp_force_labels"]}
    prediction_rows = []
    for row in prediction_batch["predictions"]:
        label = json.loads(Path(labels[row["image"]]["report_path"]).read_text())
        prediction = {
            "schema_version": 1,
            "document_kind": "aqcat25_ts_force_prediction",
            "request_sha256": row["request_sha256"],
            "structure_sha256": row["structure_sha256"],
            "checkpoint_sha256": prediction_batch["checkpoint"]["sha256"],
            "predicted_energy_eV": 0.0,
            "forces_eV_per_A": label["forces_eV_per_A"],
            "result_class": "predicted_transition_state_candidate_only",
            "reportable_dft": False,
            "scientifically_validated_ts": False,
        }
        path = _write_json(tmp_path / f"prediction_{row['image']}.json", prediction)
        prediction_rows.append(
            {"image": row["image"], "prediction": path.name, "prediction_sha256": sha256_file(path)}
        )
    set_path = _write_json(
        tmp_path / "prediction_set.json",
        {
            "document_kind": "aqcat25_ts_path_force_prediction_set",
            "source_request_sha256": sha256_file(
                tmp_path / "predictions" / "path_prediction_batch_request.json"
            ),
            "checkpoint_sha256": prediction_batch["checkpoint"]["sha256"],
            "predictions": prediction_rows,
        },
    )
    assessment = assess_path_force_predictions(root / "active_learning_state.json", set_path)
    assert assessment["status"] == "passed"
    assert assessment["aggregate_metrics"]["sample_count"] == len(prediction_rows)
    assert load_state(root / "active_learning_state.json")["status"] == (
        "awaiting_independent_ts_domain_validation"
    )


def test_failed_path_round_trains_all_batch_labels_and_routes_to_full_path_rerun(
    tmp_path: Path,
) -> None:
    path_manifest, contract, _ = _path_fixture(tmp_path)
    root = tmp_path / "active_learning"
    initialize_path_workflow(path_manifest, contract, POLICY, root)
    batch = prepare_path_vasp_force_labels(root / "active_learning_state.json", tmp_path / "labels")
    evidence_rows = []
    for row in batch["labels"]:
        _write_completed_label(tmp_path / "labels" / row["directory"])
        evidence_path = _write_json(tmp_path / f"scheduler_{row['image']}.json", _scheduler(row["image"]))
        evidence_rows.append(
            {
                "image": row["image"],
                "scheduler_evidence": evidence_path.name,
                "scheduler_evidence_sha256": sha256_file(evidence_path),
            }
        )
    evidence = _write_json(
        tmp_path / "batch_evidence.json",
        {
            "document_kind": "vasp_ts_force_label_batch_evidence",
            "source_batch_request_sha256": sha256_file(tmp_path / "labels" / "path_label_batch_request.json"),
            "labels": evidence_rows,
        },
    )
    state_path = root / "active_learning_state.json"
    ingest_path_vasp_force_labels(state_path, evidence, live_query=_live)
    state = load_state(state_path)
    state["rounds"][-1]["status"] = "fine_tuning_required"
    state["status"] = "fine_tuning_required"
    _write_json(state_path, state)
    package = prepare_finetuning_package(state_path, tmp_path / "training")
    assert len(package["labels"]) == len(batch["labels"])
    state = load_state(state_path)
    new_sha = "c" * 64
    checkpoint_validation = _write_json(
        tmp_path / "checkpoint_validation.json",
        {
            "schema_version": 1,
            "document_kind": "aqcat25_finetuned_checkpoint_validation",
            "status": "passed",
            "checkpoint_sha256": new_sha,
            "metrics": {"sample_count": 4},
        },
    )
    result = _write_json(
        tmp_path / "finetune_result.json",
        {
            "schema_version": 1,
            "document_kind": "aqcat25_ts_force_only_finetune_result",
            "status": "success",
            "result_class": "force_only_finetuned_checkpoint_candidate",
            "hostname": "MZ73",
            "gpu_job_id": "fixture-finetune",
            "training_manifest_sha256": state["rounds"][-1]["fine_tuning"]["manifest_sha256"],
            "base_checkpoint_sha256": state["rounds"][-1]["candidate"]["checkpoint_sha256"],
            "checkpoint": {
                "path": "/home/sbq/sbq/aqcat25_ts_pilot/fixture/model.pt",
                "sha256": new_sha,
            },
            "checkpoint_validation": {
                "path": checkpoint_validation.name,
                "sha256": sha256_file(checkpoint_validation),
                "status": "passed",
                "checkpoint_sha256": new_sha,
                "metrics": {"sample_count": 4},
                "scope": "held_out_adsorption_regression_not_ts_domain",
            },
            "producer_exit_record": {"path": "producer_exit_record.json", "sha256": "d" * 64},
            "reportable_final_energy": False,
            "scientific_acceptance": False,
        },
    )
    register_finetuning_result(state_path, result)
    assert load_state(state_path)["status"] == "awaiting_ml_neb_path_rerun"


def test_real_three_checkpoint_committee_is_rankable_but_not_called_calibrated_uncertainty(
    tmp_path: Path,
) -> None:
    path_manifest, contract, checkpoints = _path_fixture(tmp_path)
    request_path = tmp_path / "committee_request.json"
    prepare_committee_request(
        path_manifest,
        [(f"member-{index}", path) for index, path in enumerate(checkpoints)],
        request_path,
    )
    offsets = {str(path.resolve()): float(index) * 0.1 for index, path in enumerate(checkpoints)}
    assessment_path = tmp_path / "committee_assessment.json"
    assessment = assess_path_committee(
        path_manifest,
        request_path,
        assessment_path,
        calculator_factory=lambda checkpoint, _member_id: OffsetCalculator(
            offsets[str(checkpoint.resolve())]
        ),
    )
    assert assessment["interpretation"]["calibrated_uncertainty"] is False
    assert assessment["images"][3]["force_vector_std_max_eV_per_A"] > 0
    state = initialize_path_workflow(
        path_manifest,
        contract,
        POLICY,
        tmp_path / "committee_active_learning",
        committee_assessment_path=assessment_path,
    )
    assert state["rounds"][0]["path_selection"]["committee_status"] == "available"
