from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

import pytest
import numpy as np
from ase.db import connect

from scripts.aqcat25_ts_training_data import build_database
from scripts.aqcat25_handoff import atom_order_sha256, sha256_file
from scripts.aqcat25_ts_schema import validate_document
from scripts.neb_agent.utils_structure import Poscar, read_poscar, write_poscar
from scripts.ts_strategy_engine.contract import normalize_contract
from scripts.ts_strategy_engine.active_learning import (
    assess_independent_ts_domain,
    assess_force_prediction,
    decide_ts_domain_reuse,
    ingest_vasp_force_label,
    initialize_workflow,
    load_state,
    prepare_finetuning_package,
    prepare_ba_sella_rerun,
    prepare_force_prediction_request,
    prepare_vasp_force_label,
    register_finetuning_result,
    register_ts_domain_calibration,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "configs" / "aqcat25_ts_active_learning.yaml"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _active_learning_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build an immutable, self-contained AQCat25 handoff fixture."""

    handoff_root = tmp_path / "aqcat25_fixture"
    structure_path = handoff_root / "candidate" / "POSCAR"
    structure_path.parent.mkdir(parents=True)
    fe_coordinates = [
        [(index % 5) / 5, ((index // 5) % 3) / 3, 0.15 + 0.10 * (index // 15)]
        for index in range(45)
    ]
    write_poscar(
        structure_path,
        Poscar(
            comment="Fe45 CO active-learning fixture",
            cell=np.diag([10.0, 10.0, 20.0]),
            symbols=["Fe", "C", "O"],
            counts=[45, 1, 1],
            frac=np.array([*fe_coordinates, [0.40, 0.40, 0.70], [0.50, 0.40, 0.70]]),
            selective=True,
            flags=[*(('F', 'F', 'F') for _ in range(18)), *(('T', 'T', 'T') for _ in range(29))],
        ),
    )
    symbols = [*("Fe" for _ in range(45)), "C", "O"]
    structure_ref = {
        "path": "candidate/POSCAR",
        "sha256": sha256_file(structure_path),
        "format": "vasp_poscar",
        "atom_count": 47,
        "atom_order_sha256": atom_order_sha256(symbols),
    }

    contract = normalize_contract(
        {
            "reaction_id": "fixture_fe110_co_dissociation",
            "reaction_family": "co_dissociation",
            "reactant_id": "fixture_co",
            "product_id": "fixture_c_o",
            "index_base": 0,
            "atom_map": [{"is": index, "fs": index} for index in range(47)],
            "reaction_atoms": [45, 46],
            "broken_bonds": [[45, 46]],
            "formed_bonds": [],
            "site_changes": ["c:top->bridge", "o:molecular->hollow"],
            "compatibility": {
                "material": "fe",
                "surface": "fe110",
                "branch": "fixture_fe110",
                "slab_model": "fe45_bottom18_fixed",
                "xc": "pbe",
                "potcar_family": "paw_pbe",
                "encut_ev": 400.0,
                "kmesh": [5, 5, 1],
                "magnetic_state": "ispin2_ferromagnetic_fe",
                "coverage": "fixture_single_co",
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
    contract_path = handoff_root / "reaction_contract.normalized.json"
    _write_json(contract_path, contract)

    transition_state = {
        "normalized_reaction_contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "initial_structure": structure_ref,
        "waypoint_structures": [structure_ref],
        "final_structure": structure_ref,
        "indexed_bond_changes": [{"atoms_1based": [46, 47], "change": "break"}],
    }
    restrictions = {
        "predicted_candidate_only": True,
        "submit_vasp": False,
        "scientific_acceptance": False,
        "direct_gpu_to_vasp_handoff": False,
    }
    source_workflow_sha256 = "a" * 64
    source_handoff = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": "fixture-aqcat25-job-737",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": source_workflow_sha256,
        "candidate_structure": structure_ref,
        "compatibility": {
            "branch": "fixture_fe110",
            "sha256": "b" * 64,
            "slab_model": "fe45_bottom18_fixed",
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": "fixture-aqcat25",
            "checkpoint_sha256": "f" * 64,
            "fmax_eV_per_A": 0.05,
            "max_steps": 100,
        },
        "selective_dynamics": {
            "fixed_atom_indices_1based": list(range(1, 19)),
            "free_atom_count": 29,
        },
        "transition_state": transition_state,
        "restrictions": restrictions,
    }
    source_path = handoff_root / "source_handoff.json"
    _write_json(source_path, source_handoff)

    exit_path = handoff_root / "producer_exit_record.json"
    _write_json(exit_path, {"gpu_job_id": "fixture-737", "exit_code": 0})
    manifest = {
        "schema_version": 2,
        "direction": "gpu_to_work",
        "handoff_id": "fixture-aqcat25-job-737",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": source_workflow_sha256,
        "source_handoff": {"path": source_path.name, "sha256": sha256_file(source_path)},
        "candidate_structure": structure_ref,
        "transition_state": transition_state,
        "producer": {
            "backend": "aqcat_gpu",
            "hostname": "fixture-host",
            "gpu_job_id": "fixture-737",
            "model_identifier": "fixture-aqcat25",
            "checkpoint_sha256": "f" * 64,
        },
        "result": {
            "result_class": "predicted_transition_state_candidate_only",
            "optimizer_status": "converged",
            "optimizer_steps": 10,
            "predicted_energy": {"value": 0.0, "unit": "eV", "reportable_dft": False},
            "predicted_force": {"fmax": 0.01, "unit": "eV/A", "reportable_dft": False},
            "geometry_before": {},
            "geometry_after": {},
            "connectivity_status": "not_applicable",
            "structure_invariants": {
                "atom_order_preserved": True,
                "cell_preserved": True,
                "fixed_atoms_preserved": True,
            },
        },
        "domain_assessment": {
            "calibration_id": None,
            "status": "uncalibrated",
            "method": "test fixture",
            "reasons": ["fixture has no production calibration"],
        },
        "producer_exit_record": {
            "path": exit_path.name,
            "sha256": sha256_file(exit_path),
            "status": "success",
            "exit_code": 0,
            "evidence_class": "producer_process_only_not_scheduler_accounting",
        },
        "restrictions": restrictions,
    }
    manifest_path = handoff_root / "gpu_result_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path, handoff_root, contract_path


def _initialized(tmp_path: Path) -> Path:
    manifest, handoff_root, contract = _active_learning_fixture(tmp_path)
    destination = tmp_path / "active_learning"
    state = initialize_workflow(manifest, handoff_root, contract, POLICY, destination)
    assert state["data_policy"]["ml_values_reportable"] is False
    return destination / "active_learning_state.json"


def _write_completed_label(label_dir: Path, *, normal: bool = True) -> None:
    atom_count = sum(int(value) for value in (label_dir / "POSCAR").read_text(encoding="utf-8").splitlines()[6].split())
    rows = [f" {index:4d} 0.0 0.0 {0.001 * index:.8f} 0.00000000 0.00000000" for index in range(atom_count)]
    ending = "General timing and accounting informations for this job:\n" if normal else ""
    (label_dir / "OUTCAR").write_text(
        " free  energy   TOTEN  =       -10.5000 eV\n"
        " TOTAL-FORCE (eV/Angst)\n"
        " -------------------------------------------------------------------\n"
        + "\n".join(rows)
        + "\n\n"
        + ending,
        encoding="ascii",
    )
    (label_dir / "OSZICAR").write_text(
        " RMM:   5   -0.105000000000E+02   -0.10000E-07   -0.10000E-08  100  0.1E-04\n"
        "   1 F= -.10500000E+02 E0= -.10500000E+02  d E =-.100000E-07\n",
        encoding="ascii",
    )


def _scheduler_payload(
    job_id: str = "test-label-1", stage: str = "vasp_force_label", status: str = "DONE"
) -> dict:
    stdout = (
        "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
        f"{job_id} user {status} queue host exec label Jul 20 00:00\n"
    )
    return {
        "schema_version": 1,
        "document_kind": "scheduler_job_evidence",
        "stage": stage,
        "scheduler": "LSF",
        "server_alias": "sunboquan-codex",
        "job_id": job_id,
        "status": status,
        "checked_at": "2026-07-20T00:00:00Z",
        "source_command": f"ssh sunboquan-codex bjobs -a {job_id}",
        "query": {
            "argv": ["ssh", "sunboquan-codex", "bjobs", "-a", job_id],
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        },
    }


def _live_scheduler(job_id: str, *, stage: str) -> dict:
    return _scheduler_payload(job_id, stage)


def test_scheduler_schema_accepts_diagnostic_static() -> None:
    validate_document(
        _scheduler_payload(stage="diagnostic_static"),
        expected_kind="scheduler_job_evidence",
    )


def _scheduler(path: Path) -> Path:
    path.write_text(json.dumps(_scheduler_payload()), encoding="utf-8")
    return path


def _accepted_label(tmp_path: Path) -> tuple[Path, Path, dict]:
    state_path = _initialized(tmp_path)
    label_dir = tmp_path / "label"
    request = prepare_vasp_force_label(state_path, label_dir)
    assert request["reportable_final_energy"] is False
    _write_completed_label(label_dir)
    report = ingest_vasp_force_label(
        state_path, _scheduler(tmp_path / "scheduler.json"), live_query=_live_scheduler
    )
    prepare_force_prediction_request(state_path, tmp_path / "prediction_request")
    return state_path, label_dir, report


def _awaiting_domain_validation(tmp_path: Path) -> tuple[Path, dict, dict, dict]:
    state_path, _, report = _accepted_label(tmp_path)
    state = load_state(state_path)
    candidate = state["rounds"][-1]["candidate"]
    prediction = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_prediction",
        "request_sha256": state["rounds"][-1]["force_prediction"]["request_sha256"],
        "structure_sha256": candidate["structure_sha256"],
        "checkpoint_sha256": candidate["checkpoint_sha256"],
        "predicted_energy_eV": 0.0,
        "forces_eV_per_A": report["forces_eV_per_A"],
        "result_class": "predicted_transition_state_candidate_only",
        "reportable_dft": False,
        "scientifically_validated_ts": False,
    }
    prediction_path = tmp_path / "candidate_prediction.json"
    prediction_path.write_text(json.dumps(prediction), encoding="utf-8")
    assess_force_prediction(state_path, prediction_path)
    return state_path, report, prediction, candidate


def _heldout_sample(
    tmp_path: Path,
    *,
    index: int,
    role: str,
    report: dict,
    prediction: dict,
    geometry_offset: float = 0.0,
    structure_source: Path | None = None,
) -> dict:
    sample_dir = tmp_path / f"heldout_{index}"
    sample_dir.mkdir()
    source_structure = structure_source or Path(report["structure"]["path"])
    structure_path = sample_dir / "POSCAR"
    shutil.copy2(source_structure, structure_path)
    if geometry_offset:
        structure = read_poscar(structure_path)
        structure.frac[-1, 0] = (structure.frac[-1, 0] + geometry_offset) % 1.0
        write_poscar(structure_path, structure)
    references = {}
    for name, filename in (
        ("label_request", "label_request.json"),
        ("outcar", "OUTCAR"),
        ("oszicar", "OSZICAR"),
    ):
        target = sample_dir / filename
        shutil.copy2(Path(report[name]["path"]), target)
        references[name] = {**report[name], "path": str(target), "sha256": sha256_file(target)}
    structure_sha = sha256_file(structure_path)
    label_path = tmp_path / f"heldout_label_{index}.json"
    label_path.write_text(
        json.dumps(
            {
                **report,
                **references,
                "structure": {
                    **report["structure"],
                    "path": str(structure_path),
                    "sha256": structure_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    prediction_path = tmp_path / f"heldout_prediction_{index}.json"
    prediction_path.write_text(
        json.dumps(
            {
                **prediction,
                "request_sha256": f"{index + 20:064x}",
                "structure_sha256": structure_sha,
            }
        ),
        encoding="utf-8",
    )
    return {
        "sample_id": f"heldout-{index}",
        "role": role,
        "label": label_path.name,
        "label_sha256": sha256_file(label_path),
        "prediction": prediction_path.name,
        "prediction_sha256": sha256_file(prediction_path),
    }


def test_job737_fixture_initializes_prediction_only_workflow_without_writing_in_dry_run(tmp_path: Path) -> None:
    manifest, handoff_root, contract = _active_learning_fixture(tmp_path)
    destination = tmp_path / "dry"
    state = initialize_workflow(manifest, handoff_root, contract, POLICY, destination, dry_run=True)
    assert state["rounds"][0]["candidate"]["result_class"] == "predicted_transition_state_candidate_only"
    assert state["rounds"][0]["candidate"]["reportable_final"] is False
    assert not destination.exists()


def test_only_normally_completed_electronic_converged_vasp_label_is_ingested(tmp_path: Path) -> None:
    state_path = _initialized(tmp_path)
    label_dir = tmp_path / "label"
    prepare_vasp_force_label(state_path, label_dir)
    _write_completed_label(label_dir, normal=False)
    with pytest.raises(ValueError, match="did not finish normally"):
        ingest_vasp_force_label(
            state_path, _scheduler(tmp_path / "scheduler.json"), live_query=_live_scheduler
        )

    _write_completed_label(label_dir, normal=True)
    report = ingest_vasp_force_label(
        state_path, tmp_path / "scheduler.json", live_query=_live_scheduler
    )
    assert report["result_class"] == "vasp_completed_electronic_converged_force_label_only"
    assert report["reportable_final_energy"] is False
    assert report["eligible_for_force_only_training"] is True


def test_vasp_label_rechecks_live_lsf_state_instead_of_trusting_stored_done(tmp_path: Path) -> None:
    state_path = _initialized(tmp_path)
    label_dir = tmp_path / "label"
    prepare_vasp_force_label(state_path, label_dir)
    _write_completed_label(label_dir)

    def live_running(job_id: str, *, stage: str) -> dict:
        return _scheduler_payload(job_id, stage, "RUN")

    with pytest.raises(ValueError, match="live LSF state"):
        ingest_vasp_force_label(
            state_path,
            _scheduler(tmp_path / "scheduler.json"),
            live_query=live_running,
        )


def test_electronically_unconverged_vasp_label_is_rejected(tmp_path: Path) -> None:
    state_path = _initialized(tmp_path)
    label_dir = tmp_path / "label"
    prepare_vasp_force_label(state_path, label_dir)
    _write_completed_label(label_dir)
    (label_dir / "OSZICAR").write_text(
        " RMM: 200 -0.105000000000E+02 -0.10000E-02 -0.10000E-02 100 0.1E-02\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="not electronically converged"):
        ingest_vasp_force_label(
            state_path, _scheduler(tmp_path / "scheduler.json"), live_query=_live_scheduler
        )


def test_force_agreement_passes_but_never_claims_a_validated_ts(tmp_path: Path) -> None:
    state_path, _, report = _accepted_label(tmp_path)
    state = load_state(state_path)
    candidate = state["rounds"][-1]["candidate"]
    prediction = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_prediction",
        "request_sha256": state["rounds"][-1]["force_prediction"]["request_sha256"],
        "structure_sha256": candidate["structure_sha256"],
        "checkpoint_sha256": candidate["checkpoint_sha256"],
        "predicted_energy_eV": 0.0,
        "forces_eV_per_A": report["forces_eV_per_A"],
        "result_class": "predicted_transition_state_candidate_only",
        "reportable_dft": False,
        "scientifically_validated_ts": False,
    }
    prediction_path = tmp_path / "prediction.json"
    prediction_path.write_text(json.dumps(prediction), encoding="utf-8")
    assessment = assess_force_prediction(state_path, prediction_path)
    assert assessment["local_force_screen_passed"] is True
    assert assessment["active_learning_converged"] is False
    assert assessment["scientifically_validated_ts"] is False
    assert load_state(state_path)["status"] == "awaiting_independent_ts_domain_validation"


def test_force_label_report_tampering_is_rejected(tmp_path: Path) -> None:
    state_path, _, report = _accepted_label(tmp_path)
    state = load_state(state_path)
    label_ref = state["rounds"][-1]["vasp_force_label"]
    label_path = Path(label_ref["report_path"])
    tampered = json.loads(label_path.read_text(encoding="utf-8"))
    tampered["forces_eV_per_A"][0][0] += 1.0
    label_path.write_text(json.dumps(tampered), encoding="utf-8")
    candidate = state["rounds"][-1]["candidate"]
    prediction_path = tmp_path / "tampered_prediction.json"
    prediction_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_force_prediction",
                "request_sha256": state["rounds"][-1]["force_prediction"]["request_sha256"],
                "structure_sha256": candidate["structure_sha256"],
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "predicted_energy_eV": 0.0,
                "forces_eV_per_A": report["forces_eV_per_A"],
                "result_class": "predicted_transition_state_candidate_only",
                "reportable_dft": False,
                "scientifically_validated_ts": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="report hash changed"):
        assess_force_prediction(state_path, prediction_path)


def test_state_rejects_policy_drift(tmp_path: Path) -> None:
    policy_path = tmp_path / "configs" / "aqcat25_ts_active_learning.yaml"
    policy_path.parent.mkdir()
    shutil.copy2(POLICY, policy_path)
    destination = tmp_path / "policy_state"
    manifest, handoff_root, contract = _active_learning_fixture(tmp_path)
    initialize_workflow(manifest, handoff_root, contract, policy_path, destination)
    policy_path.write_text(
        policy_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="policy changed"):
        load_state(destination / "active_learning_state.json")


def test_uncalibrated_gate_requires_review_before_registering_bootstrap_calibration(
    tmp_path: Path,
) -> None:
    state_path, _, report = _accepted_label(tmp_path)
    state = load_state(state_path)
    candidate = state["rounds"][-1]["candidate"]
    prediction = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_prediction",
        "request_sha256": state["rounds"][-1]["force_prediction"]["request_sha256"],
        "structure_sha256": candidate["structure_sha256"],
        "checkpoint_sha256": candidate["checkpoint_sha256"],
        "predicted_energy_eV": 0.0,
        "forces_eV_per_A": report["forces_eV_per_A"],
        "result_class": "predicted_transition_state_candidate_only",
        "reportable_dft": False,
        "scientifically_validated_ts": False,
    }
    prediction_path = tmp_path / "candidate_prediction.json"
    prediction_path.write_text(json.dumps(prediction), encoding="utf-8")
    assess_force_prediction(state_path, prediction_path)
    roles = ["rising_path", "near_saddle", "falling_path", "rising_path", "falling_path"]
    samples = [
        _heldout_sample(
            tmp_path,
            index=index,
            role=role,
            report=report,
            prediction=prediction,
            geometry_offset=0.001 * (index + 1),
        )
        for index, role in enumerate(roles)
    ]
    manifest_path = tmp_path / "domain_validation.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_independent_validation_set",
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "compatibility_sha256": state["compatibility_sha256"],
                "samples": samples,
            }
        ),
        encoding="utf-8",
    )
    assessment = assess_independent_ts_domain(state_path, manifest_path)
    assert assessment["status"] == "bootstrap_passed"
    assert assessment["active_learning_converged"] is False
    assert load_state(state_path)["status"] == "awaiting_ts_domain_calibration_review"
    review_path = tmp_path / "calibration_review.json"
    review_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_domain_calibration_review",
                "assessment_sha256": sha256_file(
                    state_path.parent / "ts_domain_assessment.json"
                ),
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "compatibility_sha256": state["compatibility_sha256"],
                "reaction_domain": "true_fe110_co_dissociation",
                "force_acceptance": {
                    "component_mae_eV_per_A_max": 0.05,
                    "vector_rmse_eV_per_A_max": 0.10,
                    "vector_p95_eV_per_A_max": 0.20,
                    "vector_max_eV_per_A_max": 0.30,
                },
                "reviewer": "reviewer",
                "reviewed_at": "2026-07-22T00:00:00Z",
                "status": "accepted",
            }
        ),
        encoding="utf-8",
    )
    calibration = register_ts_domain_calibration(state_path, review_path)
    assert calibration["checkpoint_sha256"] == candidate["checkpoint_sha256"]
    assert load_state(state_path)["status"] == "ml_acceleration_ready_for_vasp_refinement"
    reusable_state = load_state(state_path)
    reusable_state["status"] = "awaiting_ts_domain_reuse_decision"
    reusable_state["rounds"][-1]["status"] = "awaiting_ts_domain_reuse_decision"
    state_path.write_text(json.dumps(reusable_state), encoding="utf-8")
    context_path = tmp_path / "reuse_context.json"
    context_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_domain_reuse_context",
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "compatibility_sha256": state["compatibility_sha256"],
                "reaction_domain": "true_fe110_co_dissociation",
                "reaction_domain_in_scope": True,
                "novelty_or_uncertainty_gate_passed": True,
                "periodic_audit_due": False,
                "reviewer": "reviewer",
                "reviewed_at": "2026-07-22T00:10:00Z",
            }
        ),
        encoding="utf-8",
    )
    reuse = decide_ts_domain_reuse(state_path, context_path)
    assert reuse["reused"] is True
    assert load_state(state_path)["status"] == "ml_acceleration_ready_for_vasp_refinement"


def test_independent_ts_domain_rejects_duplicate_structure_hashes(tmp_path: Path) -> None:
    state_path, report, prediction, candidate = _awaiting_domain_validation(tmp_path)
    roles = ["rising_path", "near_saddle", "falling_path", "rising_path", "falling_path"]
    samples = [
        _heldout_sample(
            tmp_path,
            index=index,
            role=role,
            report=report,
            prediction=prediction,
            geometry_offset=0.01,
        )
        for index, role in enumerate(roles)
    ]
    manifest_path = tmp_path / "duplicate_validation.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_independent_validation_set",
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "compatibility_sha256": load_state(state_path)["compatibility_sha256"],
                "samples": samples,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate structure hash"):
        assess_independent_ts_domain(state_path, manifest_path)


def test_independent_ts_domain_rejects_adsorption_replay_overlap(tmp_path: Path) -> None:
    state_path, report, prediction, candidate = _awaiting_domain_validation(tmp_path)
    replay = json.loads((ROOT / "outputs/aqcat25_fe45_calibration_v1/labels.json").read_text(encoding="utf-8"))
    replay_sample = replay["samples"][0]
    replay_structure = (
        ROOT
        / "outputs/aqcat25_fe45_calibration_v1/structures"
        / f"{replay_sample['sample_id']}.vasp"
    )
    roles = ["near_saddle", "rising_path", "falling_path", "rising_path", "falling_path"]
    samples = [
        _heldout_sample(
            tmp_path,
            index=index,
            role=role,
            report=report,
            prediction=prediction,
            structure_source=replay_structure if index == 0 else None,
            geometry_offset=0.0 if index == 0 else 0.001 * (index + 1),
        )
        for index, role in enumerate(roles)
    ]
    manifest_path = tmp_path / "replay_overlap_validation.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_independent_validation_set",
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "compatibility_sha256": load_state(state_path)["compatibility_sha256"],
                "samples": samples,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="overlaps active-learning training structures"):
        assess_independent_ts_domain(state_path, manifest_path)


def test_failed_force_agreement_builds_force_only_ase_database(tmp_path: Path) -> None:
    state_path, _, report = _accepted_label(tmp_path)
    state = load_state(state_path)
    candidate = state["rounds"][-1]["candidate"]
    prediction = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_prediction",
        "request_sha256": state["rounds"][-1]["force_prediction"]["request_sha256"],
        "structure_sha256": candidate["structure_sha256"],
        "checkpoint_sha256": candidate["checkpoint_sha256"],
        "predicted_energy_eV": 0.0,
        "forces_eV_per_A": [[value + 1.0 for value in vector] for vector in report["forces_eV_per_A"]],
        "result_class": "predicted_transition_state_candidate_only",
        "reportable_dft": False,
        "scientifically_validated_ts": False,
    }
    prediction_path = tmp_path / "prediction.json"
    prediction_path.write_text(json.dumps(prediction), encoding="utf-8")
    assessment = assess_force_prediction(state_path, prediction_path)
    assert assessment["active_learning_converged"] is False

    package = tmp_path / "finetune"
    manifest = prepare_finetuning_package(state_path, package)
    assert manifest["training_target"] == "forces_only"
    assert manifest["energy_loss_coefficient"] == 0.0
    database = package / "training.db"
    assert build_database(package / "training_manifest.json", database) >= 9
    validation_database = package / "validation.db"
    assert build_database(package / "training_manifest.json", validation_database, "validation") == 4
    row = connect(database).get(1)
    assert row.data["reportable_final_energy"] is False
    assert row.toatoms().get_forces().shape == (47, 3)


def test_validated_finetune_result_builds_hash_bound_ba_sella_rerun_handoff(tmp_path: Path) -> None:
    state_path, _, report = _accepted_label(tmp_path)
    state = load_state(state_path)
    candidate = state["rounds"][-1]["candidate"]
    prediction_path = tmp_path / "failed_prediction.json"
    prediction_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_force_prediction",
                "request_sha256": state["rounds"][-1]["force_prediction"]["request_sha256"],
                "structure_sha256": candidate["structure_sha256"],
                "checkpoint_sha256": candidate["checkpoint_sha256"],
                "predicted_energy_eV": 0.0,
                "forces_eV_per_A": [[value + 1.0 for value in vector] for vector in report["forces_eV_per_A"]],
                "result_class": "predicted_transition_state_candidate_only",
                "reportable_dft": False,
                "scientifically_validated_ts": False,
            }
        ),
        encoding="utf-8",
    )
    assess_force_prediction(state_path, prediction_path)
    package = tmp_path / "training_package"
    prepare_finetuning_package(state_path, package)
    state = load_state(state_path)
    new_sha = "c" * 64
    checkpoint_validation = tmp_path / "checkpoint_validation.json"
    checkpoint_validation.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_finetuned_checkpoint_validation",
                "status": "passed",
                "checkpoint_sha256": new_sha,
                "metrics": {"sample_count": 4},
            }
        ),
        encoding="utf-8",
    )
    result_path = tmp_path / "finetune_result_manifest.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "aqcat25_ts_force_only_finetune_result",
                "status": "success",
                "result_class": "force_only_finetuned_checkpoint_candidate",
                "hostname": "MZ73",
                "gpu_job_id": "123",
                "training_manifest_sha256": state["rounds"][-1]["fine_tuning"]["manifest_sha256"],
                "base_checkpoint_sha256": candidate["checkpoint_sha256"],
                "checkpoint": {"path": "/home/sbq/sbq/aqcat25_ts_pilot/test/model.pt", "sha256": new_sha},
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
            }
        ),
        encoding="utf-8",
    )
    register_finetuning_result(state_path, result_path)
    request = prepare_ba_sella_rerun(state_path, tmp_path / "rerun")
    assert request["checkpoint"]["sha256"] == new_sha
    assert (tmp_path / "rerun" / "handoff.json").is_file()
    assert load_state(state_path)["status"] == "awaiting_ba_sella_rerun_result"
