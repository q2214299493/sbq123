from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from scripts.neb_agent.check_endpoints import check_endpoints
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.generate_path import _constraint_midpoint, generate_path
from scripts.neb_agent.utils_structure import Poscar, pbc_distance, preferred_image_structure, read_poscar, write_poscar


ROOT = Path(__file__).resolve().parents[1]


def structure(c_x: float = 0.20, o_x: float = 0.40) -> Poscar:
    return Poscar(
        comment="test Fe C O",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C", "O"],
        counts=[1, 1, 1],
        frac=np.array([[0.0, 0.0, 0.0], [c_x, 0.0, 0.0], [o_x, 0.0, 0.0]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )


def test_constraint_midpoint_enforces_requested_distance() -> None:
    midpoint, warnings = _constraint_midpoint(
        structure(),
        structure(0.25, 0.55),
        {"reaction_coordinate": {"breaking_bond": [1, 2], "target_distance_A": 2.05}},
    )
    assert midpoint is not None
    assert abs(pbc_distance(midpoint, 1, 2) - 2.05) < 1e-8
    assert warnings


def test_endpoint_gate_rejects_nonidentity_map_and_fixed_atom_drift(tmp_path: Path) -> None:
    initial = tmp_path / "IS.POSCAR"
    final = tmp_path / "FS.POSCAR"
    mapped = Poscar(
        comment="test Fe C C",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C"],
        counts=[1, 2],
        frac=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.0], [0.4, 0.0, 0.0]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )
    write_poscar(initial, mapped)
    moved = copy.deepcopy(mapped)
    moved.frac[0, 0] = 0.001
    write_poscar(final, moved)
    payload = check_endpoints(
        initial,
        final,
        {
            "atom_map": [{"is": 0, "fs": 0}, {"is": 1, "fs": 2}, {"is": 2, "fs": 1}],
            "atom_map_sha256": "mapping",
            "reaction_atoms": [1, 2],
            "broken_bonds": [[1, 2]],
            "formed_bonds": [],
        },
    )
    assert payload["status"] == "STOP"
    assert any(error.startswith("non_identity_atom_map_requires_endpoint_reorder") for error in payload["errors"])
    assert any(error.startswith("fixed_atom_coordinate_mismatch") for error in payload["errors"])


def test_large_endpoint_displacement_requires_review_but_does_not_block(tmp_path: Path) -> None:
    initial = tmp_path / "IS.POSCAR"
    final = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure(0.20, 0.40))
    write_poscar(final, structure(0.60, 0.40))
    payload = check_endpoints(
        initial,
        final,
        {
            "atom_map": [{"is": index, "fs": index} for index in range(3)],
            "atom_map_sha256": "mapping",
            "reaction_atoms": [1, 2],
            "broken_bonds": [[1, 2]],
            "formed_bonds": [],
        },
    )
    assert payload["status"] == "REVIEW"
    assert payload["errors"] == []
    assert payload["warnings"] == ["mapped_displacement_exceeds_3_A"]


def test_constraint_midpoint_keeps_boundary_crossing_center() -> None:
    start = structure(0.99, 0.01)
    end = structure(0.98, 0.02)
    midpoint, _ = _constraint_midpoint(
        start,
        end,
        {"reaction_coordinate": {"breaking_bond": [1, 2], "target_distance_A": 1.0}},
    )
    assert midpoint is not None
    assert abs(pbc_distance(midpoint, 1, 2) - 1.0) < 1e-8
    assert midpoint.frac[1, 0] > 0.8


def test_diagnose_blocks_nonconsecutive_image_names(tmp_path: Path) -> None:
    for name, value in (("00", structure()), ("02", structure(0.22, 0.43))):
        write_poscar(tmp_path / name / "POSCAR", value)
    payload = diagnose(
        tmp_path,
        ["1", "2"],
        [],
        ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
    )
    assert [row["image"] for row in payload["images"]] == ["00", "02"]
    assert payload["status"] == "STOP"
    assert "nonconsecutive_or_incomplete_image_directories" in payload["errors"]


def test_diagnose_accepts_complete_compatible_path(tmp_path: Path) -> None:
    for name, value in (("00", structure()), ("01", structure(0.21, 0.415)), ("02", structure(0.22, 0.43))):
        write_poscar(tmp_path / name / "POSCAR", value)
    payload = diagnose(
        tmp_path,
        ["1", "2"],
        [],
        ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
        reaction_pairs=[[1, 2]],
        expected_interior=1,
    )
    assert payload["status"] == "PASS"
    assert (tmp_path / "path_geometry_diagnosis.json").is_file()
    assert not (tmp_path / "path_geometry_diagnosis.md").exists()
    assert not (tmp_path / "geometry_review.xyz").exists()


def test_reaction_coordinate_backtrack_requires_review_not_stop(tmp_path: Path) -> None:
    for name, value in (
        ("00", structure(0.20, 0.32)),
        ("01", structure(0.20, 0.40)),
        ("02", structure(0.20, 0.37)),
        ("03", structure(0.20, 0.50)),
    ):
        write_poscar(tmp_path / name / "POSCAR", value)
    payload = diagnose(
        tmp_path,
        ["1", "2"],
        [],
        ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
        reaction_pairs=[[1, 2]],
        expected_interior=2,
    )
    assert payload["status"] == "REVIEW"
    assert payload["errors"] == []
    assert any("reaction_coordinate_backtrack" in item for item in payload["warnings"])


def test_normal_oh_bond_is_not_reported_as_collision(tmp_path: Path) -> None:
    oh = Poscar(
        comment="Fe O H",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "O", "H"],
        counts=[1, 1, 1],
        frac=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.2], [0.2, 0.0, 0.296]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )
    for name in ("00", "01", "02"):
        write_poscar(tmp_path / name / "POSCAR", oh)
    payload = diagnose(
        tmp_path,
        ["1", "2"],
        [],
        ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
        reaction_pairs=[[1, 2]],
        expected_interior=1,
    )
    assert payload["status"] == "PASS"


def test_segmented_idpp_preserves_fixed_atoms(tmp_path: Path) -> None:
    initial = tmp_path / "initial.POSCAR"
    midpoint = tmp_path / "midpoint.POSCAR"
    final = tmp_path / "final.POSCAR"
    write_poscar(initial, structure(0.20, 0.40))
    write_poscar(midpoint, structure(0.24, 0.46))
    write_poscar(final, structure(0.28, 0.52))
    output = tmp_path / "path"
    payload = generate_path(initial, final, output, 3, "segmented_idpp", None, [midpoint])
    assert payload["status"] == "READY_FOR_GEOMETRY_REVIEW"
    assert len(payload["image_directories"]) == 5
    assert (output / "path_generation_report.json").is_file()
    assert not (output / "path_generation_report.md").exists()
    fixed = [read_poscar(output / name / "POSCAR").frac[0].tolist() for name in payload["image_directories"]]
    assert all(np.allclose(value, fixed[0]) for value in fixed)


def test_segmented_idpp_uses_one_continuous_periodic_branch(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "initial.POSCAR"
    midpoint = tmp_path / "midpoint.POSCAR"
    final = tmp_path / "final.POSCAR"
    start = structure(0.95, 0.80)
    middle = structure(0.02, 0.90)
    end = structure(1.08, 1.05)
    middle.frac[0] = np.array([1.0, 1.0, 0.0])
    end.frac[0] = np.array([1.0, 1.0, 0.0])
    write_poscar(initial, start)
    write_poscar(midpoint, middle)
    write_poscar(final, end)

    output = tmp_path / "path"
    payload = generate_path(
        initial,
        final,
        output,
        3,
        "segmented_idpp",
        None,
        [midpoint],
    )

    images = [
        read_poscar(output / name / "POSCAR")
        for name in payload["image_directories"]
    ]
    assert payload["periodic_branch"]["fixed_atoms_exactly_preserved"] is True
    assert all(
        np.array_equal(image.frac[0], images[0].frac[0])
        for image in images
    )
    assert all(
        float(np.max(np.abs(right.frac - left.frac))) <= 0.5
        for left, right in zip(images, images[1:])
    )
    assert np.allclose(
        np.mod(images[-1].frac, 1.0),
        np.mod(end.frac, 1.0),
    )


def test_geometry_diagnosis_rejects_raw_periodic_branch_jump(
    tmp_path: Path,
) -> None:
    first = structure(0.20, 0.40)
    middle = structure(0.24, 0.46)
    final = structure(0.28, 0.52)
    middle.frac[0] = np.array([1.0, 0.0, 0.0])
    final.frac[0] = np.array([1.0, 0.0, 0.0])
    for name, value in zip(
        ("00", "01", "02"),
        (first, middle, final),
        strict=True,
    ):
        write_poscar(tmp_path / name / "POSCAR", value)

    payload = diagnose(
        tmp_path,
        ["1", "2"],
        ["0"],
        ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
        reaction_pairs=[[1, 2]],
        expected_interior=1,
    )

    assert payload["status"] == "STOP"
    assert any(
        "raw_periodic_branch_discontinuity" in error
        for error in payload["errors"]
    )
    assert any(
        "fixed_atom_raw_coordinate_mismatch" in error
        for error in payload["errors"]
    )


def test_segmented_idpp_accepts_exactly_one_image_per_waypoint(tmp_path: Path) -> None:
    initial = tmp_path / "initial.POSCAR"
    final = tmp_path / "final.POSCAR"
    waypoints = [tmp_path / f"waypoint_{index}.POSCAR" for index in range(3)]
    write_poscar(initial, structure(0.20, 0.40))
    for path, values in zip(
        waypoints,
        ((0.22, 0.43), (0.24, 0.46), (0.26, 0.49)),
        strict=True,
    ):
        write_poscar(path, structure(*values))
    write_poscar(final, structure(0.28, 0.52))
    output = tmp_path / "path"
    payload = generate_path(initial, final, output, 3, "segmented_idpp", None, waypoints)
    assert payload["status"] == "READY_FOR_GEOMETRY_REVIEW"
    assert payload["segment_additional_images"] == [0, 0, 0, 0]
    assert len(payload["image_directories"]) == 5


def test_rebuild_requires_authoritative_gate_decision(tmp_path: Path) -> None:
    initial = tmp_path / "initial.POSCAR"
    final = tmp_path / "final.POSCAR"
    write_poscar(initial, structure(0.20, 0.40))
    write_poscar(final, structure(0.28, 0.52))
    payload = generate_path(
        initial,
        final,
        tmp_path / "path",
        3,
        "idpp",
        None,
        [],
        rebuild=True,
    )
    assert payload["status"] == "STOP"
    assert "authoritative gate decision" in payload["errors"][0]


def test_preferred_image_structure_uses_nonempty_contcar(tmp_path: Path) -> None:
    image = tmp_path / "01"
    image.mkdir()
    poscar = image / "POSCAR"
    poscar.write_text("initial", encoding="ascii")
    assert preferred_image_structure(image) == poscar
    contcar = image / "CONTCAR"
    contcar.touch()
    assert preferred_image_structure(image) == poscar
    contcar.write_text("relaxed", encoding="ascii")
    assert preferred_image_structure(image) == contcar
