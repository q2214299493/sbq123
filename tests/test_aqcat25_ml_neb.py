from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import FixAtoms
from ase.io import write

from scripts.aqcat25_handoff import atom_order_sha256
from scripts.aqcat25_ml_neb import RunSettings, run_from_handoff, seal_successful_run
from scripts.artifact_io import sha256_file
from scripts.ts_strategy_engine.ml_neb_path import (
    finalize_gpu_ml_neb_path_manifest,
    validate_gpu_ml_neb_path_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
ZERO = "0" * 64


class DoubleWellCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        coordinate = (float(atoms.positions[2, 0]) - 5.5) / 0.5
        energy = (coordinate**2 - 1.0) ** 2
        forces = np.zeros((len(atoms), 3), dtype=float)
        forces[2, 0] = -4.0 * coordinate * (coordinate**2 - 1.0) / 0.5
        self.results = {"energy": energy, "forces": forces}


def _structure_ref(path: Path, atoms: Atoms) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "format": "vasp_poscar",
        "atom_count": len(atoms),
        "atom_order_sha256": atom_order_sha256(atoms.get_chemical_symbols()),
    }


def _handoff(tmp_path: Path) -> tuple[Path, Path]:
    initial = Atoms(
        ["Fe", "C", "H"],
        positions=[[1.0, 1.0, 1.0], [4.0, 1.0, 2.0], [6.0, 1.0, 2.0]],
        cell=[10.0, 10.0, 12.0],
        pbc=True,
    )
    initial.set_constraint(FixAtoms(indices=[0]))
    final = initial.copy()
    final.positions[2, 0] = 5.0
    initial_path, final_path = tmp_path / "IS.vasp", tmp_path / "FS.vasp"
    write(initial_path, initial, format="vasp", direct=True, vasp5=True)
    write(final_path, final, format="vasp", direct=True, vasp5=True)
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"test checkpoint")
    handoff = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": "ml-neb-test",
        "workflow_kind": "transition_state",
        "source_workflow_sha256": ZERO,
        "candidate_structure": _structure_ref(initial_path, initial),
        "compatibility": {
            "branch": "test",
            "sha256": "1" * 64,
            "slab_model": "Fe-test",
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": "AQCat25 test",
            "checkpoint_sha256": sha256_file(checkpoint),
            "fmax_eV_per_A": 0.10,
            "max_steps": 5,
        },
        "selective_dynamics": {"fixed_atom_indices_1based": [1], "free_atom_count": 2},
        "transition_state": {
            "normalized_reaction_contract_sha256": "2" * 64,
            "atom_map_sha256": "3" * 64,
            "initial_structure": _structure_ref(initial_path, initial),
            "waypoint_structures": [],
            "final_structure": _structure_ref(final_path, final),
            "indexed_bond_changes": [{"atoms_1based": [2, 3], "change": "form"}],
        },
        "restrictions": {
            "predicted_candidate_only": True,
            "submit_vasp": False,
            "scientific_acceptance": False,
            "direct_gpu_to_vasp_handoff": False,
        },
    }
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    return handoff_path, checkpoint


def test_ml_neb_runs_every_image_and_finalizes_reviewed_manifest(tmp_path: Path) -> None:
    handoff, checkpoint = _handoff(tmp_path)
    output = tmp_path / "output" / "run"
    candidate = run_from_handoff(
        handoff,
        checkpoint,
        output,
        schema_path=ROOT / "configs" / "aqcat25_handoff.schema.json",
        settings=RunSettings(
            images_per_segment=5,
            ordinary_fmax_eV_per_A=50.0,
            ordinary_max_steps=2,
            ml_ci="auto",
            ci_fmax_eV_per_A=50.0,
            ci_max_steps=2,
            checkpoint_interval=1,
        ),
        calculator_factory=DoubleWellCalculator,
    )
    sealed = seal_successful_run(output, candidate)
    candidate_path = output / "gpu_ml_neb_path_manifest.candidate.json"
    validate_gpu_ml_neb_path_manifest(candidate_path)
    first_image = output / sealed["images"][0]["structure_path"]
    original_image = first_image.read_bytes()
    first_image.write_bytes(original_image + b"\n")
    with pytest.raises(ValueError, match="structure_hash"):
        validate_gpu_ml_neb_path_manifest(candidate_path)
    first_image.write_bytes(original_image)

    assert len(sealed["images"]) == 5
    assert sealed["optimizer"]["ml_ci_neb"]["ran"] is True
    assert sealed["optimizer"]["final_stage"] == "ml_ci_neb"
    assert (output / "gpu_ml_neb_path_review.draft.json").is_file()
    assert all((output / row["structure_path"]).is_file() for row in sealed["images"])
    assert all(row["key_bond_distances_A"] for row in sealed["images"])
    assert sealed["vasp_label_candidates"]

    def must_not_recalculate():
        raise AssertionError("completed --resume must reuse the sealed path")

    resumed = run_from_handoff(
        handoff,
        checkpoint,
        output,
        schema_path=ROOT / "configs" / "aqcat25_handoff.schema.json",
        settings=RunSettings(
            images_per_segment=5,
            ordinary_fmax_eV_per_A=50.0,
            ordinary_max_steps=2,
            ml_ci="auto",
            ci_fmax_eV_per_A=50.0,
            ci_max_steps=2,
            checkpoint_interval=1,
        ),
        calculator_factory=must_not_recalculate,
        resume=True,
    )
    assert resumed["producer_exit_record"]["status"] == "success"

    review = {
        "document_kind": "gpu_ml_neb_path_review",
        "status": "accepted",
        "candidate_manifest_sha256": sha256_file(candidate_path),
        "geometry_continuity": "accepted",
        "periodic_mapping": "accepted",
        "reaction_coordinate_resolution": "accepted",
        "elementary_step_assignment": "accepted",
        "candidate_peak_image": "02",
        "reviewer": "test-reviewer",
        "reviewed_at": "2026-08-19T00:00:00Z",
    }
    review_path = output / "gpu_ml_neb_path_review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    accepted_path = output / "gpu_ml_neb_path_manifest.json"
    accepted = finalize_gpu_ml_neb_path_manifest(candidate_path, review_path, accepted_path)
    assert accepted["status"] == "accepted_for_vasp_validated_dimer_parent"
    assert accepted["restrictions"]["reportable_dft"] is False
