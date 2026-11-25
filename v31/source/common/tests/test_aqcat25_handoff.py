from __future__ import annotations

import json
from pathlib import Path

import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write
from jsonschema import Draft202012Validator

from scripts.aqcat25_handoff import DEFAULT_SCHEMA, HandoffValidationError, atom_order_sha256, sha256_file, validate_handoff


ZERO_SHA = "0" * 64
RESTRICTIONS = {
    "predicted_candidate_only": True,
    "submit_vasp": False,
    "scientific_acceptance": False,
    "direct_gpu_to_vasp_handoff": False,
}


def test_aqcat25_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8")))


def _write_h2_candidate(root: Path) -> tuple[Path, list[str]]:
    atoms = Atoms(
        ["Fe", "Fe", "H", "H"],
        positions=[[0, 0, 0], [2.4, 0, 0], [1.2, 0, 1.8], [1.2, 0, 2.55]],
        cell=[8, 8, 12],
        pbc=[True, True, False],
    )
    atoms.set_constraint(FixAtoms(indices=[0]))
    path = root / "POSCAR"
    write(path, atoms, format="vasp", direct=True, vasp5=True)
    return path, atoms.get_chemical_symbols()


def _adsorption_contract() -> dict[str, object]:
    return {
        "evidence_gated_plan_sha256": ZERO_SHA,
        "clean_slab_sha256": ZERO_SHA,
        "identity_and_connectivity": "molecular H2",
        "intended_motif": "H2 molecular top",
        "surface_elements": ["Fe"],
        "adsorbate_atoms": [
            {"index_1based": 3, "symbol": "H", "role": "anchor"},
            {"index_1based": 4, "symbol": "H", "role": "non_anchor"},
        ],
        "connectivity_constraints": [
            {"label": "H-H", "atoms_1based": [3, 4], "max_distance_A": 1.0}
        ],
        "monitored_pairs": [{"label": "H-H", "atoms_1based": [3, 4]}],
    }


def _structure_ref(path: Path, symbols: list[str]) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "format": "vasp_poscar",
        "atom_count": len(symbols),
        "atom_order_sha256": atom_order_sha256(symbols),
    }


def _work_manifest(root: Path) -> dict[str, object]:
    path, symbols = _write_h2_candidate(root)
    return {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": "h2-test",
        "workflow_kind": "adsorption",
        "source_workflow_sha256": ZERO_SHA,
        "candidate_structure": _structure_ref(path, symbols),
        "compatibility": {
            "branch": "true_fe110_5layer_5x5x1",
            "sha256": ZERO_SHA,
            "slab_model": "test",
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": "AQCat25 test",
            "checkpoint_sha256": ZERO_SHA,
            "fmax_eV_per_A": 0.05,
            "max_steps": 80,
        },
        "selective_dynamics": {"fixed_atom_indices_1based": [1], "free_atom_count": 3},
        "adsorption": _adsorption_contract(),
        "restrictions": RESTRICTIONS,
    }


def test_work_to_gpu_h2_contract_and_bound_files_validate(tmp_path: Path) -> None:
    manifest = _work_manifest(tmp_path)
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    validated = validate_handoff(path)
    assert validated["adsorption"]["adsorbate_atoms"][1]["symbol"] == "H"


def test_validator_rejects_structure_hash_mismatch(tmp_path: Path) -> None:
    manifest = _work_manifest(tmp_path)
    manifest["candidate_structure"]["sha256"] = "f" * 64
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(HandoffValidationError, match="SHA256 mismatch"):
        validate_handoff(path)


def test_work_to_gpu_ts_contract_binds_waypoints_and_atom_order(tmp_path: Path) -> None:
    atoms = Atoms(
        ["Fe", "Fe", "C", "O"],
        positions=[[0, 0, 0], [2.4, 0, 0], [1.2, 0, 1.8], [1.2, 0, 2.98]],
        cell=[8, 8, 12],
        pbc=True,
    )
    atoms.set_constraint(FixAtoms(indices=[0]))
    refs = []
    for name, shift in (("IS", 0.0), ("WP", 0.5), ("FS", 1.5)):
        state = atoms.copy()
        state.positions[3, 0] += shift
        path = tmp_path / f"{name}.vasp"
        write(path, state, format="vasp", direct=True, vasp5=True)
        refs.append(_structure_ref(path, state.get_chemical_symbols()))
    manifest = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": "ts-test",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": ZERO_SHA,
        "candidate_structure": refs[1],
        "compatibility": {
            "branch": "true_fe110_5layer_5x5x1",
            "sha256": ZERO_SHA,
            "slab_model": "test",
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": "AQCat25 test",
            "checkpoint_sha256": ZERO_SHA,
            "fmax_eV_per_A": 0.05,
            "max_steps": 80,
        },
        "selective_dynamics": {"fixed_atom_indices_1based": [1], "free_atom_count": 3},
        "transition_state": {
            "normalized_reaction_contract_sha256": ZERO_SHA,
            "atom_map_sha256": ZERO_SHA,
            "initial_structure": refs[0],
            "waypoint_structures": [refs[1]],
            "final_structure": refs[2],
            "indexed_bond_changes": [{"atoms_1based": [3, 4], "change": "break"}],
        },
        "restrictions": RESTRICTIONS,
    }
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    validate_handoff(path)

    manifest["transition_state"]["waypoint_structures"][0]["sha256"] = "f" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(HandoffValidationError, match="SHA256 mismatch"):
        validate_handoff(path)


def test_work_to_gpu_ts_contract_allows_reviewed_direct_path_without_waypoint(tmp_path: Path) -> None:
    atoms = Atoms(["Fe", "H"], positions=[[0, 0, 0], [0, 0, 1]], cell=[8, 8, 12], pbc=True)
    atoms.set_constraint(FixAtoms(indices=[0]))
    refs = []
    for name, height in (("IS", 1.0), ("FS", 2.0)):
        state = atoms.copy()
        state.positions[1, 2] = height
        path = tmp_path / f"{name}.vasp"
        write(path, state, format="vasp", direct=True, vasp5=True)
        refs.append(_structure_ref(path, state.get_chemical_symbols()))
    manifest = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": "ts-direct-test",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": ZERO_SHA,
        "candidate_structure": refs[0],
        "compatibility": {"branch": "test", "sha256": ZERO_SHA, "slab_model": "test", "facet": "Fe(110)"},
        "model": {"identifier": "AQCat25 test", "checkpoint_sha256": ZERO_SHA, "fmax_eV_per_A": 0.05, "max_steps": 20},
        "selective_dynamics": {"fixed_atom_indices_1based": [1], "free_atom_count": 1},
        "transition_state": {
            "normalized_reaction_contract_sha256": ZERO_SHA,
            "atom_map_sha256": ZERO_SHA,
            "initial_structure": refs[0],
            "waypoint_structures": [],
            "final_structure": refs[1],
            "indexed_bond_changes": [{"atoms_1based": [1, 2], "change": "break"}],
        },
        "restrictions": RESTRICTIONS,
    }
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    validate_handoff(path)


def test_gpu_to_work_contract_binds_exit_record_and_forbids_dft_claim(tmp_path: Path) -> None:
    source_manifest = _work_manifest(tmp_path)
    source_path = tmp_path / "handoff.json"
    source_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    structure_path, symbols = _write_h2_candidate(tmp_path)
    exit_path = tmp_path / "producer_exit_record.json"
    exit_path.write_text(json.dumps({"gpu_job_id": "12", "exit_code": 0}), encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "direction": "gpu_to_work",
        "handoff_id": "h2-test",
        "workflow_kind": "adsorption",
        "source_workflow_sha256": ZERO_SHA,
        "source_handoff": {"path": source_path.name, "sha256": sha256_file(source_path)},
        "candidate_structure": _structure_ref(structure_path, symbols),
        "adsorption": _adsorption_contract(),
        "producer": {
            "backend": "aqcat_gpu",
            "hostname": "MZ73",
            "gpu_job_id": "12",
            "model_identifier": "AQCat25 test",
            "checkpoint_sha256": ZERO_SHA,
        },
        "result": {
            "result_class": "predicted_adsorption_candidate_only",
            "optimizer_status": "converged",
            "optimizer_steps": 2,
            "predicted_energy": {"value": -1.0, "unit": "eV", "reportable_dft": False},
            "predicted_force": {"fmax": 0.03, "unit": "eV/A", "reportable_dft": False},
            "geometry_before": {},
            "geometry_after": {},
            "connectivity_status": "pass",
            "structure_invariants": {
                "atom_order_preserved": True,
                "cell_preserved": True,
                "fixed_atoms_preserved": True,
            },
        },
        "domain_assessment": {
            "calibration_id": None,
            "status": "uncalibrated",
            "method": "no compatible labels",
            "reasons": ["test"],
        },
        "producer_exit_record": {
            "path": exit_path.name,
            "sha256": sha256_file(exit_path),
            "status": "success",
            "exit_code": 0,
            "evidence_class": "producer_process_only_not_scheduler_accounting",
        },
        "restrictions": RESTRICTIONS,
    }
    path = tmp_path / "gpu_result_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    validate_handoff(path)

    manifest["result"]["predicted_energy"]["reportable_dft"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(HandoffValidationError, match="False was expected"):
        validate_handoff(path)
