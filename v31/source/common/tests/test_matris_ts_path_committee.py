from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import write

from scripts.matris_ts_path_committee import run_committee


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _MemberCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, value: float) -> None:
        super().__init__()
        self.value = value

    def calculate(self, atoms=None, properties=None, system_changes=all_changes) -> None:
        super().calculate(atoms, properties, system_changes)
        coordinate = float(atoms.positions[-1, 2])
        self.results = {
            "energy": self.value * coordinate,
            "forces": np.full((len(atoms), 3), self.value, dtype=float),
        }


def test_three_member_committee_reports_exact_path_disagreement(tmp_path: Path) -> None:
    structures = []
    for index in range(3):
        atoms = Atoms("FeOH", positions=[[0, 0, 0], [0, 0, 2], [0, 0, 3-index*0.2]])
        atoms.set_cell([8, 8, 12])
        atoms.set_pbc(True)
        path = tmp_path / f"{index:02d}.vasp"
        write(path, atoms, format="vasp", direct=True, vasp5=True)
        structures.append(
            {
                "sample_id": f"pre_{index:02d}",
                "image": f"{index:02d}",
                "source_stage": "preconditioning",
                "selection_role": "path_member",
                "path": path.name,
                "sha256": _sha(path),
            }
        )
    base_checkpoint = tmp_path / "base.pt"
    audit_checkpoint = tmp_path / "audit.pt"
    base_checkpoint.write_bytes(b"base")
    audit_checkpoint.write_bytes(b"audit")
    prediction_request = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_path_force_prediction_batch_request",
        "automatic_vasp_submission": False,
        "models": {
            "primary": {"backend": "matris", "checkpoint_sha256": _sha(base_checkpoint)},
            "secondary": {"backend": "aqcat25", "checkpoint_sha256": _sha(audit_checkpoint)},
        },
        "indexed_bond_changes": [{"atoms_1based": [2, 3], "change": "form"}],
        "fixed_atom_indices_zero_based": [0],
        "structures": structures,
    }
    prediction_path = tmp_path / "prediction_request.json"
    prediction_path.write_text(json.dumps(prediction_request), encoding="utf-8")
    members = []
    values = {}
    for index, value in enumerate((0.1, 0.2, 0.4), start=1):
        checkpoint = tmp_path / f"member_{index}.pt"
        checkpoint.write_bytes(f"member-{index}".encode())
        values[checkpoint.resolve()] = value
        members.append(
            {
                "member_id": f"seed_{index}",
                "backend": "matris",
                "checkpoint_path": str(checkpoint),
                "checkpoint_sha256": _sha(checkpoint),
                "architecture_identifier": "MatRIS-4M-FeCOH",
                "training_run_sha256": f"{index:064x}",
                "production_acceptance_passed": True,
            }
        )
    committee_request = {
        "schema_version": 1,
        "document_kind": "matris_ts_path_committee_request",
        "source_prediction_request_sha256": _sha(prediction_path),
        "relative_energy_reference_sample": "pre_00",
        "members": members,
        "automatic_submission": False,
    }
    committee_path = tmp_path / "committee.json"
    committee_path.write_text(json.dumps(committee_request), encoding="utf-8")

    def loader(backend: str, checkpoint: Path, device: str):
        assert backend == "matris"
        assert device == "cpu"
        return _MemberCalculator(values[checkpoint.resolve()])

    result = run_committee(
        committee_path,
        prediction_path,
        tmp_path / "result.json",
        device="cpu",
        calculator_loader=loader,
    )
    assert len(result["members"]) == 3
    assert result["predictions"][1]["force_disagreement_eV_per_A"] > 0
    assert result["predictions"][1]["relative_energy_disagreement_eV"] > 0
    assert result["interpretation"].endswith("heldout_calibration")


def test_committee_rejects_fewer_than_three_members(tmp_path: Path) -> None:
    committee = {
        "schema_version": 1,
        "document_kind": "matris_ts_path_committee_request",
        "source_prediction_request_sha256": "0" * 64,
        "members": [],
        "automatic_submission": False,
    }
    path = tmp_path / "committee.json"
    path.write_text(json.dumps(committee), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        run_committee(path, tmp_path / "missing.json", tmp_path / "out.json", device="cpu")
