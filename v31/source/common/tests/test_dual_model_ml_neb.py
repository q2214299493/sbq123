from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import FixAtoms
from ase.io import write

from scripts.artifact_io import sha256_file
from scripts.dual_model_ml_neb import (
    HarmonicPositionRestraint,
    _assert_geometry_guards,
    _backtrack_assessment,
    _geometry_guard_evidence,
    _load_images,
    _load_request,
    _normalize_periodic_branches,
    _redistribute_by_monitored_bond,
    run_dual_model_request,
    seal_successful_run,
)


class PathCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, offset: float) -> None:
        super().__init__()
        self.offset = offset

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        forming_distance = float(atoms.get_distance(3, 5, mic=True))
        self.results = {
            "energy": self.offset - (forming_distance - 1.5) ** 2,
            "forces": np.zeros((len(atoms), 3), dtype=float),
        }


class ConstantTransverseForceCalculator(PathCalculator):
    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        forces = np.zeros((len(atoms), 3), dtype=float)
        forces[4, 1] = 0.4
        self.results["forces"] = forces


def _fixture(tmp_path: Path, *, broken_cc: bool = False) -> tuple[Path, Path, Path]:
    structures = tmp_path / "structures"
    structures.mkdir()
    images = []
    for index in range(5):
        atoms = Atoms(
            ["Fe", "C", "C", "O", "H", "H"],
            positions=[
                [1.0, 1.0, 1.0],
                [4.0, 4.0, 4.0],
                [5.4 if not broken_cc else 6.0, 4.0, 4.0],
                [6.6, 4.0, 4.0],
                [3.0, 4.0, 4.0],
                [8.6 - 0.25 * index, 4.0, 4.0],
            ],
            cell=[12.0, 12.0, 14.0],
            pbc=True,
        )
        atoms.set_constraint(FixAtoms(indices=[0]))
        path = structures / f"{index:02d}.vasp"
        write(path, atoms, format="vasp", direct=True, vasp5=True)
        images.append(
            {
                "image": f"{index:02d}",
                "path": path.relative_to(tmp_path).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    primary = tmp_path / "matris.pth.tar"
    secondary = tmp_path / "aqcat.pt"
    primary.write_bytes(b"matris-test")
    secondary.write_bytes(b"aqcat-test")
    request = {
        "schema_version": 1,
        "document_kind": "dual_model_ml_neb_request",
        "request_id": "dual-model-test",
        "run_kind": "smoke_test",
        "result_class": "predicted_path_candidate_only",
        "automatic_vasp_submission": False,
        "models": {
            "primary": {
                "backend": "matris",
                "identifier": "MatRIS test",
                "checkpoint_sha256": sha256_file(primary),
            },
            "secondary": {
                "backend": "aqcat25",
                "identifier": "AQCat25 test",
                "checkpoint_sha256": sha256_file(secondary),
            },
        },
        "reaction": {
            "contract_sha256": "1" * 64,
            "atom_map_sha256": "2" * 64,
            "compatibility_sha256": "3" * 64,
            "indexed_bond_changes": [{"atoms_1based": [4, 6], "change": "form"}],
        },
        "fixed_atom_indices_zero_based": [0],
        "images": images,
        "preconditioning": {
            "fmax_eV_per_A": 50.0,
            "max_steps": 1,
            "restraint_spring_constant_eV_per_A2": 10.0,
            "position_restraint_spring_constant_eV_per_A2": 10.0,
            "require_convergence_before_release": True,
            "enforce_monitored_bond_monotonicity": True,
            "maximum_monitored_bond_backtrack_A": 0.05,
            "require_monitored_bond_interval_coverage": True,
            "temporary_bond_constraints": [
                {
                    "name": "preserve_C_C",
                    "atoms_zero_based": [1, 2],
                    "images": "internal",
                },
                {
                    "name": "anchor_forming_O_H",
                    "atoms_zero_based": [3, 5],
                    "images": ["02"],
                },
            ],
            "temporary_position_constraints": [
                {
                    "name": "anchor_transfer_H_position",
                    "atom_zero_based": 5,
                    "images": "internal",
                }
            ],
        },
        "restraint_release": {
            "purpose": "test gradual release without changing the hard geometry limits",
            "require_each_stage_convergence": True,
            "stages": [
                {
                    "name": "half_strength",
                    "bond_spring_constant_eV_per_A2": 5.0,
                    "position_spring_constant_eV_per_A2": 5.0,
                    "fmax_eV_per_A": 50.0,
                    "max_steps": 1,
                    "enforce_monitored_bond_monotonicity": True,
                    "maximum_monitored_bond_backtrack_A": 0.05,
                    "require_monitored_bond_interval_coverage": True,
                },
                {
                    "name": "low_strength",
                    "bond_spring_constant_eV_per_A2": 2.0,
                    "position_spring_constant_eV_per_A2": 2.0,
                    "fmax_eV_per_A": 50.0,
                    "max_steps": 1,
                    "enforce_monitored_bond_monotonicity": True,
                    "maximum_monitored_bond_backtrack_A": 0.05,
                    "require_monitored_bond_interval_coverage": True,
                },
            ],
        },
        "ordinary_ml_neb": {
            "spring_constant_eV_per_A2": 0.10,
            "fmax_eV_per_A": 50.0,
            "max_steps": 1,
            "ml_ci": "off",
            "ci_fmax_eV_per_A": 50.0,
            "ci_max_steps": 1,
            "monitored_geometry_guard": {
                "enforce_monitored_bond_monotonicity": True,
                "maximum_monitored_bond_backtrack_A": 0.05,
                "require_monitored_bond_interval_coverage": True,
            },
        },
        "geometry_guards": {
            "preserved_bonds": [
                {
                    "name": "C1_C2",
                    "atoms_zero_based": [1, 2],
                    "minimum_A": 1.25,
                    "maximum_A": 1.60,
                }
            ],
            "monitored_bonds": [
                {
                    "name": "forming_O_H",
                    "atoms_zero_based": [3, 5],
                    "important_interval_A": [1.1, 1.8],
                    "minimum_internal_images": 3,
                }
            ],
            "minimum_pair_distance_A": 0.65,
            "maximum_adjacent_rmsd_A": 0.75,
            "maximum_single_movable_atom_step_A": 1.0,
        },
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return request_path, primary, secondary


def test_dual_model_executor_releases_constraints_and_compares_exact_path(tmp_path: Path) -> None:
    request, primary, secondary = _fixture(tmp_path)

    def loader(backend: str, _checkpoint: Path, _device: str) -> Calculator:
        return PathCalculator(0.0 if backend == "matris" else 0.2)

    output = tmp_path / "output"
    candidate = run_dual_model_request(
        request,
        primary,
        secondary,
        output,
        device="cpu",
        calculator_loader=loader,
    )
    sealed = seal_successful_run(output, candidate)

    release = sealed["optimizer"]["constraint_release"]
    assert release["released_before_ordinary_ml_neb"] is True
    assert release["post_release_internal_coordinate_constraint_count"] == [0, 0, 0, 0, 0]
    assert release["post_release_position_restraint_count"] == [0, 0, 0, 0, 0]
    assert len(release["staged_release"]) == 2
    assert len(release["stage_snapshots"]) == 3
    for snapshot in release["stage_snapshots"]:
        manifest = output / snapshot["manifest_path"]
        assert manifest.is_file()
        assert sha256_file(manifest) == snapshot["manifest_sha256"]
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload["image_count"] == 5
        assert all(
            sha256_file(manifest.parent / row["path"]) == row["sha256"]
            for row in payload["images"]
        )
    assert sealed["geometry_guards"]["passed"] is True
    assert sealed["fixed_path_model_comparison"]["interpretation"].endswith(
        "not_calibrated_uncertainty"
    )
    assert all(
        row["structure_sha256"] == sealed["images"][index]["structure_sha256"]
        for index, row in enumerate(sealed["fixed_path_model_comparison"]["images"])
    )
    assert all(row["model_disagreement"] is not None for row in sealed["images"])
    assert sealed["restrictions"]["automatic_vasp_submission"] is False


def test_release_stage_can_warn_and_continue_when_only_fmax_target_is_missed(
    tmp_path: Path,
) -> None:
    request, primary, secondary = _fixture(tmp_path)
    request_data = json.loads(request.read_text(encoding="utf-8"))
    release = request_data["restraint_release"]
    release["require_each_stage_convergence"] = False
    release["nonconverged_stage_action"] = "warning_continue"
    for stage in release["stages"]:
        stage["fmax_eV_per_A"] = 1.0e-6
        stage["max_steps"] = 1
    request.write_text(json.dumps(request_data), encoding="utf-8")

    def loader(backend: str, _checkpoint: Path, _device: str) -> Calculator:
        if backend == "matris":
            return ConstantTransverseForceCalculator(0.0)
        return PathCalculator(0.2)

    candidate = run_dual_model_request(
        request,
        primary,
        secondary,
        tmp_path / "output",
        device="cpu",
        calculator_loader=loader,
    )

    release_result = candidate["optimizer"]["constraint_release"]
    assert release_result["nonconverged_stage_action"] == "warning_continue"
    assert all(not row["converged"] for row in release_result["staged_release"])
    assert all(
        row["warning_codes"] == ["RESTRAINT_RELEASE_FMAX_TARGET_NOT_REACHED"]
        for row in release_result["staged_release"]
    )
    for row in release_result["staged_release"]:
        diagnostic = tmp_path / "output" / row["stage_diagnostic"]["path"]
        payload = json.loads(diagnostic.read_text(encoding="utf-8"))
        assert sha256_file(diagnostic) == row["stage_diagnostic"]["sha256"]
        assert payload["continuation_status"] == "warning_continue"
        assert payload["geometry_guards"]["passed"] is True
        assert payload["force_decomposition"]["maximum_physical_force_eVA"] > 0.0
        assert payload["force_decomposition"]["maximum_projected_neb_force_eVA"] > 0.0


def test_release_stage_strict_mode_still_fails_when_fmax_target_is_missed(
    tmp_path: Path,
) -> None:
    request, primary, secondary = _fixture(tmp_path)
    request_data = json.loads(request.read_text(encoding="utf-8"))
    request_data["restraint_release"]["nonconverged_stage_action"] = "fail"
    request_data["restraint_release"]["stages"][0]["fmax_eV_per_A"] = 1.0e-6
    request.write_text(json.dumps(request_data), encoding="utf-8")

    def loader(backend: str, _checkpoint: Path, _device: str) -> Calculator:
        if backend == "matris":
            return ConstantTransverseForceCalculator(0.0)
        return PathCalculator(0.2)

    with pytest.raises(RuntimeError, match="did not converge before the next release"):
        run_dual_model_request(
            request,
            primary,
            secondary,
            tmp_path / "output",
            device="cpu",
            calculator_loader=loader,
        )


def test_dual_model_executor_aborts_outside_preserved_cc_window(tmp_path: Path) -> None:
    request, primary, secondary = _fixture(tmp_path, broken_cc=True)

    def loader(backend: str, _checkpoint: Path, _device: str) -> Calculator:
        return PathCalculator(0.0 if backend == "matris" else 0.2)

    with pytest.raises(RuntimeError, match="geometry guard failed"):
        run_dual_model_request(
            request,
            primary,
            secondary,
            tmp_path / "output",
            device="cpu",
            calculator_loader=loader,
        )


def test_preserved_cc_graded_warning_only_aborts_outside_hard_window(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    preserved = request_data["geometry_guards"]["preserved_bonds"][0]
    preserved.update(
        {
            "assessment_mode": "graded_warning",
            "hard_minimum_A": 1.10,
            "hard_maximum_A": 1.90,
        }
    )
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)

    images[2].positions[2, 0] = images[2].positions[1, 0] + 1.70
    warning = _geometry_guard_evidence(images, request)["preserved_bonds"][0]
    assert warning["accepted_window_passed"] is False
    assert warning["hard_passed"] is True
    assert warning["level"] == "warning"
    _assert_geometry_guards(images, request, "ordinary_ml_neb")

    images[2].positions[2, 0] = images[2].positions[1, 0] + 1.95
    failure = _geometry_guard_evidence(images, request)["preserved_bonds"][0]
    assert failure["hard_passed"] is False
    assert failure["level"] == "hard_failure"
    with pytest.raises(RuntimeError, match="geometry guard failed"):
        _assert_geometry_guards(images, request, "ordinary_ml_neb")


def test_monitored_forming_bond_rejects_backtracking(tmp_path: Path) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)

    passed = _geometry_guard_evidence(images, request)["monitored_bonds"][0]
    assert passed["coverage_passed"] is True
    assert passed["monotonic_passed"] is True
    assert passed["passed"] is True

    images[3].positions[5, 0] = images[3].positions[3, 0] + 1.70
    failed = _geometry_guard_evidence(images, request)["monitored_bonds"][0]
    assert failed["coverage_passed"] is True
    assert failed["maximum_observed_backtrack_A"] == pytest.approx(0.20)
    assert failed["monotonic_passed"] is False
    assert failed["passed"] is False


def test_monitored_bond_interval_uses_configured_numeric_tolerance(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["important_interval_tolerance_A"] = 0.02
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    images[3].positions[5, 0] = images[3].positions[3, 0] + 1.0995

    evidence = _geometry_guard_evidence(images, request)["monitored_bonds"][0]

    assert evidence["important_interval_tolerance_A"] == pytest.approx(0.02)
    assert evidence["effective_important_interval_A"] == pytest.approx([1.08, 1.82])
    assert "03" not in evidence["covered_internal_images"]
    assert "03" in evidence["borderline_internal_images"]


def test_preconditioning_hard_gate_rejects_monitored_bond_backtracking(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    images[3].positions[5, 0] = images[3].positions[3, 0] + 1.70

    with pytest.raises(RuntimeError, match="geometry guard failed"):
        _assert_geometry_guards(images, request, "restrained_preconditioning")
    _assert_geometry_guards(images, request, "ordinary_ml_neb")


def test_preconditioning_allows_only_configured_small_transient_backtrack(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    images[3].positions[5, 0] = images[3].positions[3, 0] + 1.52

    evidence = _geometry_guard_evidence(images, request)["monitored_bonds"][0]

    assert evidence["maximum_observed_backtrack_A"] == pytest.approx(0.02)
    assert evidence["monotonic_passed"] is False
    _assert_geometry_guards(images, request, "restrained_preconditioning")


def test_periodic_position_restraint_uses_minimum_image() -> None:
    atoms = Atoms("H", positions=[[11.2, 1.0, 1.0]], cell=[10.0, 10.0, 10.0], pbc=True)
    restraint = HarmonicPositionRestraint(0, np.asarray([1.0, 1.0, 1.0]), 10.0)
    forces = np.zeros((1, 3), dtype=float)

    restraint.adjust_forces(atoms, forces)

    assert forces[0] == pytest.approx([-2.0, 0.0, 0.0])


def test_periodic_branch_normalization_preserves_physical_geometry(tmp_path: Path) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    reference_distance = images[2].get_distance(3, 5, mic=True)
    images[2].positions[5] += images[2].cell[0]
    assert _geometry_guard_evidence(images, request)["periodic_branch_numeric_passed"] is False

    normalizations = _normalize_periodic_branches(images)

    assert normalizations
    assert _geometry_guard_evidence(images, request)["periodic_branch_numeric_passed"] is True
    assert images[2].get_distance(3, 5, mic=True) == pytest.approx(reference_distance)


def test_single_atom_step_guard_is_not_hidden_by_average_rmsd(tmp_path: Path) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    images[2].positions[5, 1] += 1.2

    evidence = _geometry_guard_evidence(images, request)

    assert evidence["adjacent_rmsd_passed"] is True
    assert evidence["maximum_single_movable_atom_step_A"] > 1.0
    assert evidence["maximum_single_movable_atom_step_passed"] is False


def test_graded_backtrack_treats_small_far_field_rollback_as_warning_only(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    images[1].positions[5, 0] = images[1].positions[3, 0] + 2.05133
    row = _geometry_guard_evidence(images, request)["monitored_bonds"][0]
    policy = {
        "monitored_bond_backtrack_mode": "graded_warning",
        "monitored_bond_monotonicity_scope": "all_path",
        "maximum_monitored_bond_backtrack_A": 0.05,
        "borderline_monitored_bond_backtrack_A": 0.07,
    }

    assessment = _backtrack_assessment(row, policy)

    assert assessment["maximum_observed_backtrack_A"] == pytest.approx(0.05133)
    assert assessment["level"] == "borderline_warning"
    assert assessment["automatic_failure_from_backtrack_only"] is False

    policy["monitored_bond_monotonicity_scope"] = "important_interval"
    scoped = _backtrack_assessment(row, policy)
    assert scoped["maximum_observed_backtrack_A"] == pytest.approx(0.0)
    assert scoped["level"] == "pass"


def test_reaction_coordinate_redistribution_restores_frozen_interval_grid(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_data["reaction_coordinate_redistribution"] = {
        "enabled": True,
        "monitored_bond_name": "forming_O_H",
        "target_distances_A": {"01": 1.75, "02": 1.5, "03": 1.25},
        "maximum_exact_bond_correction_A": 0.20,
        "apply_after_preconditioning": True,
        "apply_after_each_release_stage": True,
        "apply_before_ordinary_ml_neb": True,
    }
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    for image, distance in zip(images[1:4], [1.95, 1.05, 1.01], strict=True):
        image.positions[5, 0] = image.positions[3, 0] + distance

    evidence = _redistribute_by_monitored_bond(images, request)

    assert evidence["before_distances_A"] == pytest.approx(
        [2.0, 1.95, 1.05, 1.01, 1.0]
    )
    assert evidence["after_distances_A"] == pytest.approx(
        [2.0, 1.75, 1.5, 1.25, 1.0]
    )
    assert evidence["geometry_guards"]["passed"] is True


def test_product_side_redistribution_can_use_configuration_arc_length(
    tmp_path: Path,
) -> None:
    request_path, _, _ = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_data["reaction_coordinate_redistribution"] = {
        "enabled": True,
        "monitored_bond_name": "forming_O_H",
        "target_distances_A": {"01": 1.75, "02": 1.5, "03": 1.25},
        "maximum_exact_bond_correction_A": 0.20,
        "apply_after_preconditioning": True,
        "apply_after_each_release_stage": True,
        "apply_before_ordinary_ml_neb": True,
        "product_side_arc_length": {
            "start_image": "03",
            "method": "movable_atom_configuration_arc_length",
        },
    }
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    request = _load_request(request_path)
    images = _load_images(request, request_path.parent)
    images[3].positions[4, 1] += 0.8

    evidence = _redistribute_by_monitored_bond(images, request)

    product_side = evidence["product_side_arc_length"]
    assert product_side["start_image"] == "03"
    assert product_side["end_image"] == "04"
    assert product_side["configuration_arc_length_A"] > 0.0
    assert product_side["source_path_parameters"][0] == pytest.approx(
        evidence["source_path_parameters"][3]
    )
    assert product_side["source_path_parameters"][-1] == pytest.approx(4.0)
    assert evidence["geometry_guards"]["passed"] is True


def test_prevalidated_unrestrained_seed_skips_constraint_preparation(
    tmp_path: Path,
) -> None:
    request_path, primary, secondary = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    request_data["preconditioning"] = {"enabled": False}
    request_data["restraint_release"] = {
        "require_each_stage_convergence": False,
        "nonconverged_stage_action": "fail",
        "stages": [],
    }
    request_path.write_text(json.dumps(request_data), encoding="utf-8")

    def loader(backend: str, _checkpoint: Path, _device: str) -> Calculator:
        return PathCalculator(0.0 if backend == "matris" else 0.2)

    candidate = run_dual_model_request(
        request_path,
        primary,
        secondary,
        tmp_path / "output",
        device="cpu",
        calculator_loader=loader,
    )

    release = candidate["optimizer"]["constraint_release"]
    assert candidate["optimizer"]["restrained_preconditioning"]["steps"] == 0
    assert release["constraint_target_reference"] == "prevalidated_unrestrained_seed"
    assert release["staged_release"] == []
    assert release["reaction_coordinate_redistributions"] == []


def test_executor_records_frozen_targets_and_staged_redistributions(
    tmp_path: Path,
) -> None:
    request_path, primary, secondary = _fixture(tmp_path)
    request_data = json.loads(request_path.read_text(encoding="utf-8"))
    monitored = request_data["geometry_guards"]["monitored_bonds"][0]
    monitored["monotonic_direction"] = "decreasing"
    monitored["maximum_backtrack_A"] = 0.01
    request_data["preconditioning"]["constraint_target_reference"] = (
        "initial_request_seed"
    )
    request_data["reaction_coordinate_redistribution"] = {
        "enabled": True,
        "monitored_bond_name": "forming_O_H",
        "target_distances_A": {"01": 1.75, "02": 1.5, "03": 1.25},
        "maximum_exact_bond_correction_A": 0.20,
        "apply_after_preconditioning": True,
        "apply_after_each_release_stage": True,
        "apply_before_ordinary_ml_neb": True,
    }
    request_path.write_text(json.dumps(request_data), encoding="utf-8")

    def loader(backend: str, _checkpoint: Path, _device: str) -> Calculator:
        return PathCalculator(0.0 if backend == "matris" else 0.2)

    candidate = run_dual_model_request(
        request_path,
        primary,
        secondary,
        tmp_path / "output",
        device="cpu",
        calculator_loader=loader,
    )
    release = candidate["optimizer"]["constraint_release"]

    assert release["constraint_target_reference"] == "initial_request_seed"
    assert len(release["reaction_coordinate_redistributions"]) == 4
    assert all(
        row["evidence"]["geometry_guards"]["passed"]
        for row in release["reaction_coordinate_redistributions"]
    )
