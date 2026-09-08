from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import write

from scripts.dual_model_ts_force_prediction_batch import run_batch, validate_request


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _FixedCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, energy: float, force: float) -> None:
        super().__init__()
        self.energy = energy
        self.force = force

    def calculate(self, atoms=None, properties=None, system_changes=all_changes) -> None:
        super().calculate(atoms, properties, system_changes)
        self.results = {
            "energy": self.energy,
            "forces": np.full((len(atoms), 3), self.force, dtype=float),
        }


def _request(tmp_path: Path) -> tuple[Path, Path, Path]:
    structures = []
    for index in range(3):
        atoms = Atoms("Fe2OH", positions=[[0, 0, 0], [2, 0, 0], [0, 0, 2], [0, 0, 3-index*0.1]])
        atoms.set_cell([8, 8, 12])
        atoms.set_pbc(True)
        path = tmp_path / f"{index:02d}.vasp"
        write(path, atoms, format="vasp", direct=True, vasp5=True)
        structures.append(
            {
                "sample_id": f"pre_{index:02d}",
                "image": f"{index:02d}",
                "source_stage": "preconditioning",
                "path": path.name,
                "sha256": _sha(path),
            }
        )
    primary = tmp_path / "primary.pt"
    secondary = tmp_path / "secondary.pt"
    primary.write_bytes(b"primary")
    secondary.write_bytes(b"secondary")
    request = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_path_force_prediction_batch_request",
        "automatic_vasp_submission": False,
        "models": {
            "primary": {"backend": "matris", "checkpoint_sha256": _sha(primary)},
            "secondary": {"backend": "aqcat25", "checkpoint_sha256": _sha(secondary)},
        },
        "indexed_bond_changes": [{"atoms_1based": [3, 4], "change": "form"}],
        "fixed_atom_indices_zero_based": [0, 1],
        "structures": structures,
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return request_path, primary, secondary


def test_exact_dual_model_batch_keeps_full_forces_and_hash_binding(tmp_path: Path) -> None:
    request, primary, secondary = _request(tmp_path)

    def loader(backend: str, checkpoint: Path, device: str):
        assert device == "cpu"
        return _FixedCalculator(1.0 if backend == "matris" else 1.5, 0.2 if backend == "matris" else 0.1)

    result = run_batch(
        request,
        primary,
        secondary,
        tmp_path / "predictions.json",
        device="cpu",
        calculator_loader=loader,
    )
    assert len(result["predictions"]) == 3
    row = result["predictions"][0]
    assert np.asarray(row["primary_forces_eV_per_A"]).shape == (4, 3)
    assert row["movable_force_difference"]["vector_max_eV_per_A"] == pytest.approx(
        np.sqrt(3) * 0.1
    )
    assert row["reaction_coordinate_value_A"] == pytest.approx(1.0)
    assert row["key_bond_distances_A"][0]["change"] == "form"
    assert result["interpretation"].endswith("not_calibrated_uncertainty")


def test_request_rejects_automatic_vasp_submission(tmp_path: Path) -> None:
    request, _, _ = _request(tmp_path)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["automatic_vasp_submission"] = True
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="automatic_vasp_submission"):
        validate_request(request)
