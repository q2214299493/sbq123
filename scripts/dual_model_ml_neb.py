#!/usr/bin/env python3
"""Run a hash-bound MatRIS-primary ML-NEB with AQCat25 fixed-path review.

This executor is prediction-only.  It may temporarily constrain selected bond
lengths during a preconditioning stage, but it always removes those temporary
constraints before ordinary ML-NEB.  The secondary model evaluates the exact
final primary-path structures without relaxation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms, FixConstraint
from ase.geometry import find_mic
from ase.io import read
from ase.mep import NEB

try:
    from scripts.aqcat25_ml_neb import (
        RunSettings,
        _adjacent_rmsd,
        _attach_model_context,
        _ci_readiness,
        _evaluate_path,
        _fixed_indices,
        _key_bond_distances,
        _minimum_pair_distance,
        _optimizer_stage,
        _periodic_branch_continuous,
        _strict_internal_peaks,
        _write_vasp_atomic,
        _write_restart,
    )
    from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
    from scripts.mlip_same_structure_benchmark import _load_calculator
    from scripts.ml_sella_candidate import refine_peak, require_sella, validate_settings as validate_sella_settings
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from aqcat25_ml_neb import (
        RunSettings,
        _adjacent_rmsd,
        _attach_model_context,
        _ci_readiness,
        _evaluate_path,
        _fixed_indices,
        _key_bond_distances,
        _minimum_pair_distance,
        _optimizer_stage,
        _periodic_branch_continuous,
        _strict_internal_peaks,
        _write_vasp_atomic,
        _write_restart,
    )
    from artifact_io import load_json_object, sha256_file, write_json_atomic
    from mlip_same_structure_benchmark import _load_calculator
    from ml_sella_candidate import refine_peak, require_sella, validate_settings as validate_sella_settings


CalculatorLoader = Callable[[str, Path, str], Any]


class HarmonicBondRestraint(FixConstraint):
    """Bilateral harmonic distance restraint used only during preconditioning."""

    def __init__(self, first: int, second: int, target_A: float, spring_eV_per_A2: float) -> None:
        self.first = int(first)
        self.second = int(second)
        self.target_A = float(target_A)
        self.spring_eV_per_A2 = float(spring_eV_per_A2)
        if self.first == self.second:
            raise ValueError("harmonic bond restraint requires two distinct atoms")
        if self.target_A <= 0.0 or self.spring_eV_per_A2 <= 0.0:
            raise ValueError("harmonic bond restraint target and spring must be positive")

    def get_removed_dof(self, atoms: Atoms) -> int:
        return 0

    def adjust_forces(self, atoms: Atoms, forces: np.ndarray) -> None:
        vector = np.asarray(
            atoms.get_distance(self.first, self.second, mic=True, vector=True), dtype=float
        )
        distance = float(np.linalg.norm(vector))
        if distance <= 1.0e-12:
            raise RuntimeError("harmonic bond restraint encountered zero distance")
        correction = self.spring_eV_per_A2 * (distance - self.target_A) * vector / distance
        forces[self.first] += correction
        forces[self.second] -= correction

    def index_shuffle(self, atoms: Atoms, ind: Any) -> None:
        reverse = {int(old): new for new, old in enumerate(ind)}
        if self.first not in reverse or self.second not in reverse:
            raise IndexError("harmonic bond restraint atom removed")
        self.first = reverse[self.first]
        self.second = reverse[self.second]

    def todict(self) -> dict[str, Any]:
        return {
            "name": type(self).__name__,
            "kwargs": {
                "first": self.first,
                "second": self.second,
                "target_A": self.target_A,
                "spring_eV_per_A2": self.spring_eV_per_A2,
            },
        }


class HarmonicPositionRestraint(FixConstraint):
    """Periodic harmonic position restraint used only during preconditioning."""

    def __init__(
        self, atom: int, target_position_A: np.ndarray, spring_eV_per_A2: float
    ) -> None:
        self.atom = int(atom)
        self.target_position_A = np.asarray(target_position_A, dtype=float).copy()
        self.spring_eV_per_A2 = float(spring_eV_per_A2)
        if self.target_position_A.shape != (3,) or not np.all(
            np.isfinite(self.target_position_A)
        ):
            raise ValueError("harmonic position restraint target must be one finite 3-vector")
        if self.spring_eV_per_A2 <= 0.0:
            raise ValueError("harmonic position restraint spring must be positive")

    def get_removed_dof(self, atoms: Atoms) -> int:
        return 0

    def adjust_forces(self, atoms: Atoms, forces: np.ndarray) -> None:
        displacement, _ = find_mic(
            atoms.positions[self.atom] - self.target_position_A,
            atoms.cell,
            atoms.pbc,
        )
        forces[self.atom] -= self.spring_eV_per_A2 * np.asarray(displacement, dtype=float)

    def index_shuffle(self, atoms: Atoms, ind: Any) -> None:
        reverse = {int(old): new for new, old in enumerate(ind)}
        if self.atom not in reverse:
            raise IndexError("harmonic position restraint atom removed")
        self.atom = reverse[self.atom]

    def todict(self) -> dict[str, Any]:
        return {
            "name": type(self).__name__,
            "kwargs": {
                "atom": self.atom,
                "target_position_A": self.target_position_A.tolist(),
                "spring_eV_per_A2": self.spring_eV_per_A2,
            },
        }


def _validate_sha256(value: Any, label: str) -> str:
    text = str(value).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} must be a lowercase SHA-256 value")
    return text


def _validate_release_stages(request: dict[str, Any]) -> None:
    release = request.get("restraint_release", {})
    stages = release.get("stages", []) if isinstance(release, dict) else None
    if not isinstance(stages, list):
        raise ValueError("restraint_release.stages must be a list")
    preconditioning = request.get("preconditioning", {})
    if preconditioning.get("enabled", True) is False:
        if stages:
            raise ValueError("disabled preconditioning requires an empty restraint-release schedule")
        if preconditioning.get("temporary_bond_constraints") or preconditioning.get(
            "temporary_position_constraints"
        ):
            raise ValueError("disabled preconditioning cannot define temporary constraints")
        if request.get("reaction_coordinate_redistribution") is not None:
            raise ValueError(
                "an unrestrained seed must be redistributed before request construction"
            )
        return
    nonconverged_action = release.get("nonconverged_stage_action")
    if nonconverged_action is not None and nonconverged_action not in {
        "fail",
        "warning_continue",
    }:
        raise ValueError(
            "restraint_release.nonconverged_stage_action must be fail or warning_continue"
        )
    if (
        release.get("require_each_stage_convergence", False)
        and nonconverged_action not in {None, "fail"}
    ):
        raise ValueError(
            "require_each_stage_convergence=true conflicts with warning_continue"
        )
    previous_bond_spring = float(
        preconditioning.get("restraint_spring_constant_eV_per_A2", float("inf"))
    )
    previous_position_spring = float(
        preconditioning.get(
            "position_restraint_spring_constant_eV_per_A2",
            previous_bond_spring,
        )
    )
    names: set[str] = set()
    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            raise ValueError(f"restraint release stage {index} must be an object")
        name = str(stage.get("name", ""))
        if (
            not name
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                for character in name
            )
            or name in names
        ):
            raise ValueError(f"invalid or repeated restraint release stage name: {name}")
        names.add(name)
        bond_spring = float(stage.get("bond_spring_constant_eV_per_A2", 0.0))
        position_spring = float(
            stage.get("position_spring_constant_eV_per_A2", 0.0)
        )
        if not 0.0 < bond_spring < previous_bond_spring:
            raise ValueError(
                "release-stage bond springs must be positive and strictly decreasing"
            )
        if not 0.0 < position_spring < previous_position_spring:
            raise ValueError(
                "release-stage position springs must be positive and strictly decreasing"
            )
        if float(stage.get("fmax_eV_per_A", 0.0)) <= 0.0 or int(
            stage.get("max_steps", 0)
        ) <= 0:
            raise ValueError("release-stage fmax and max_steps must be positive")
        previous_bond_spring = bond_spring
        previous_position_spring = position_spring


def _validate_product_side_arc_length(
    redistribution: dict[str, Any], labels: list[str], image_count: int
) -> None:
    product_side = redistribution.get("product_side_arc_length")
    if product_side is None:
        return
    if not isinstance(product_side, dict):
        raise ValueError("product-side arc-length settings must be an object")
    if product_side.get("method") != "movable_atom_configuration_arc_length":
        raise ValueError("unsupported product-side arc-length method")
    start_label = str(product_side.get("start_image", ""))
    if start_label != labels[-1]:
        raise ValueError(
            "product-side arc length must start at the final monitored-bond target"
        )
    if int(start_label) >= image_count - 1:
        raise ValueError("product-side arc length requires an internal start image")


def _validate_reaction_coordinate_redistribution(request: dict[str, Any]) -> None:
    redistribution = request.get("reaction_coordinate_redistribution")
    if redistribution is None:
        return
    if not isinstance(redistribution, dict) or redistribution.get("enabled") is not True:
        raise ValueError("reaction-coordinate redistribution must be an enabled object")
    monitored_name = str(redistribution.get("monitored_bond_name", ""))
    monitored = [
        row
        for row in request.get("geometry_guards", {}).get("monitored_bonds", [])
        if row.get("name") == monitored_name
    ]
    if len(monitored) != 1:
        raise ValueError("redistribution must name exactly one monitored bond")
    targets = redistribution.get("target_distances_A")
    image_count = len(request.get("images", []))
    if not isinstance(targets, dict) or not targets:
        raise ValueError("redistribution target distances must be a non-empty image map")
    labels = list(targets)
    expected_labels = [f"{index:02d}" for index in range(1, image_count - 1)]
    if labels != sorted(labels) or any(label not in expected_labels for label in labels):
        raise ValueError("redistribution targets must use sorted internal-image labels")
    values = [float(targets[label]) for label in labels]
    if not all(math.isfinite(value) and value > 0.0 for value in values):
        raise ValueError("redistribution target distances must be finite and positive")
    direction = monitored[0].get("monotonic_direction")
    differences = np.diff(values)
    if direction == "decreasing" and not np.all(differences < 0.0):
        raise ValueError("redistribution targets must be strictly decreasing")
    if direction == "increasing" and not np.all(differences > 0.0):
        raise ValueError("redistribution targets must be strictly increasing")
    if direction not in {"decreasing", "increasing"}:
        raise ValueError("redistribution requires a monitored-bond direction")
    if len(values) < int(monitored[0]["minimum_internal_images"]):
        raise ValueError("redistribution has fewer targets than the interval minimum")
    if float(redistribution.get("maximum_exact_bond_correction_A", 0.0)) <= 0.0:
        raise ValueError("redistribution maximum exact-bond correction must be positive")
    for key in (
        "apply_after_preconditioning",
        "apply_after_each_release_stage",
        "apply_before_ordinary_ml_neb",
    ):
        if not isinstance(redistribution.get(key), bool):
            raise ValueError(f"redistribution {key} must be boolean")
    _validate_product_side_arc_length(redistribution, labels, image_count)


def _load_request(request_path: Path) -> dict[str, Any]:
    request = load_json_object(request_path)
    if request.get("schema_version") != 1 or request.get("document_kind") != "dual_model_ml_neb_request":
        raise ValueError("invalid dual-model ML-NEB request")
    if request.get("result_class") != "predicted_path_candidate_only":
        raise ValueError("dual-model request must remain prediction-only")
    if request.get("automatic_vasp_submission") is not False:
        raise ValueError("automatic VASP submission must be explicitly false")
    models = request.get("models")
    if not isinstance(models, dict):
        raise ValueError("request models are missing")
    if models.get("primary", {}).get("backend") != "matris":
        raise ValueError("the TS-path primary backend must be matris")
    if models.get("secondary", {}).get("backend") != "aqcat25":
        raise ValueError("the fixed-path secondary backend must be aqcat25")
    for role in ("primary", "secondary"):
        _validate_sha256(models[role].get("checkpoint_sha256"), f"{role} checkpoint")
    images = request.get("images")
    if not isinstance(images, list) or len(images) < 3:
        raise ValueError("at least three explicit path images are required")
    labels = [str(row.get("image")) for row in images]
    if labels != [f"{index:02d}" for index in range(len(images))]:
        raise ValueError("request images must be consecutively labeled from 00")
    _validate_release_stages(request)
    _validate_reaction_coordinate_redistribution(request)
    if "sella_refinement" in request:
        validate_sella_settings(request["sella_refinement"])
    return request


def _load_images(request: dict[str, Any], request_root: Path) -> list[Atoms]:
    images: list[Atoms] = []
    for row in request["images"]:
        path = (request_root / str(row["path"])).resolve()
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            raise ValueError(f"image {row['image']} is missing or changed")
        atoms = read(path, format="vasp")
        images.append(atoms)
    symbols = images[0].get_chemical_symbols()
    fixed = _fixed_indices(images[0])
    cell = images[0].cell.array
    pbc = np.asarray(images[0].pbc, dtype=bool)
    for index, image in enumerate(images):
        if image.get_chemical_symbols() != symbols:
            raise ValueError(f"image {index:02d} atom order differs")
        if not np.allclose(image.cell.array, cell, atol=1.0e-8, rtol=0.0):
            raise ValueError(f"image {index:02d} cell differs")
        if not np.array_equal(np.asarray(image.pbc, dtype=bool), pbc):
            raise ValueError(f"image {index:02d} PBC differs")
        if _fixed_indices(image) != fixed:
            raise ValueError(f"image {index:02d} fixed mask differs")
    expected_fixed = sorted(int(value) for value in request["fixed_atom_indices_zero_based"])
    if fixed != expected_fixed:
        raise ValueError("request fixed-atom mask does not match path structures")
    return images


def _verify_checkpoint(path: Path, expected_sha256: str, role: str) -> None:
    if not path.is_file():
        raise ValueError(f"{role} checkpoint is missing: {path}")
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"{role} checkpoint SHA-256 mismatch")


def _selection_applies(image_index: int, image_count: int, selection: Any) -> bool:
    label = f"{image_index:02d}"
    return bool(
        selection == "internal" and 0 < image_index < image_count - 1
        or isinstance(selection, list) and label in selection
    )


def _constraint_pairs_for_image(
    image_index: int, image_count: int, constraints: list[dict[str, Any]]
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    label = f"{image_index:02d}"
    for rule in constraints:
        if _selection_applies(image_index, image_count, rule["images"]):
            pair = tuple(int(value) for value in rule["atoms_zero_based"])
            if len(pair) != 2 or pair[0] == pair[1]:
                raise ValueError(f"invalid temporary bond pair for image {label}")
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def _position_atoms_for_image(
    image_index: int, image_count: int, constraints: list[dict[str, Any]]
) -> list[int]:
    atoms: list[int] = []
    label = f"{image_index:02d}"
    for rule in constraints:
        if _selection_applies(image_index, image_count, rule["images"]):
            atom = int(rule["atom_zero_based"])
            if atom < 0:
                raise ValueError(f"invalid temporary position atom for image {label}")
            if atom not in atoms:
                atoms.append(atom)
    return atoms


def _apply_temporary_constraints(
    images: list[Atoms],
    bond_rules: list[dict[str, Any]],
    spring_eV_per_A2: float,
    position_rules: list[dict[str, Any]] | None = None,
    position_spring_eV_per_A2: float | None = None,
    target_images: list[Atoms] | None = None,
) -> tuple[list[list[Any]], dict[str, list[dict[str, Any]]]]:
    position_rules = position_rules or []
    position_spring = float(position_spring_eV_per_A2 or spring_eV_per_A2)
    original = [list(image.constraints) for image in images]
    if target_images is not None and len(target_images) != len(images):
        raise ValueError("constraint target-image count differs from the path")
    evidence: dict[str, list[dict[str, Any]]] = {}
    for index, image in enumerate(images):
        target_image = target_images[index] if target_images is not None else image
        pairs = _constraint_pairs_for_image(index, len(images), bond_rules)
        position_atoms = _position_atoms_for_image(index, len(images), position_rules)
        rows: list[dict[str, Any]] = []
        lengths = [
            float(target_image.get_distance(left, right, mic=True))
            for left, right in pairs
        ]
        targets = [target_image.positions[atom].copy() for atom in position_atoms]
        if pairs or position_atoms:
            image.set_constraint(
                [
                    *original[index],
                    *(
                        HarmonicBondRestraint(left, right, length, spring_eV_per_A2)
                        for (left, right), length in zip(pairs, lengths, strict=True)
                    ),
                    *(
                        HarmonicPositionRestraint(atom, target, position_spring)
                        for atom, target in zip(position_atoms, targets, strict=True)
                    ),
                ]
            )
            rows.extend(
                {
                    "type": "bilateral_harmonic_bond_restraint",
                    "atoms_zero_based": list(pair),
                    "target_distance_A": length,
                    "spring_constant_eV_per_A2": spring_eV_per_A2,
                    "target_reference": "initial_request_seed"
                    if target_images is not None
                    else "current_stage_start",
                }
                for pair, length in zip(pairs, lengths, strict=True)
            )
            rows.extend(
                {
                    "type": "periodic_harmonic_position_restraint",
                    "atom_zero_based": atom,
                    "target_position_A": target.tolist(),
                    "spring_constant_eV_per_A2": position_spring,
                    "target_reference": "initial_request_seed"
                    if target_images is not None
                    else "current_stage_start",
                }
                for atom, target in zip(position_atoms, targets, strict=True)
            )
        evidence[f"{index:02d}"] = rows
    return original, evidence


def _release_temporary_constraints(images: list[Atoms], original: list[list[Any]]) -> None:
    for image, constraints in zip(images, original, strict=True):
        image.set_constraint(constraints)
    if any(
        any(
            isinstance(item, (HarmonicBondRestraint, HarmonicPositionRestraint))
            for item in image.constraints
        )
        for image in images
    ):
        raise RuntimeError("temporary preconditioning constraints were not fully released")


def _maximum_movable_force_norm(image: Atoms, values: np.ndarray) -> float:
    fixed = set(_fixed_indices(image))
    movable = [index for index in range(len(image)) if index not in fixed]
    if not movable:
        return 0.0
    return float(np.linalg.norm(values[movable], axis=1).max())


def _temporary_restraint_forces(image: Atoms) -> np.ndarray:
    forces = np.zeros((len(image), 3), dtype=float)
    for constraint in image.constraints:
        if isinstance(constraint, (HarmonicBondRestraint, HarmonicPositionRestraint)):
            constraint.adjust_forces(image, forces)
    if not np.isfinite(forces).all():
        raise RuntimeError("temporary restraint returned non-finite forces")
    return forces


def _stage_force_decomposition(images: list[Atoms], neb: NEB) -> dict[str, Any]:
    """Separate model, temporary-restraint, and projected NEB forces.

    The temporary stages are path-preparation artifacts.  Reporting these
    components prevents a large artificial restraint force from being
    mistaken for a physical-model or final NEB instability.
    """

    physical = [
        np.asarray(image.get_forces(apply_constraint=False), dtype=float)
        for image in images
    ]
    restraint = [_temporary_restraint_forces(image) for image in images]
    if any(
        values.shape != (len(image), 3) or not np.isfinite(values).all()
        for image, values in zip(images, physical, strict=True)
    ):
        raise RuntimeError("primary model returned invalid physical forces")
    projected_internal = np.asarray(neb.get_forces(), dtype=float).reshape(
        (len(images) - 2, len(images[0]), 3)
    )
    if not np.isfinite(projected_internal).all():
        raise RuntimeError("NEB returned non-finite projected forces")

    rows: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        projected = np.zeros((len(image), 3), dtype=float)
        if 0 < index < len(images) - 1:
            projected = projected_internal[index - 1]
        rows.append(
            {
                "image": f"{index:02d}",
                "physical_force_max_eVA": _maximum_movable_force_norm(
                    image, physical[index]
                ),
                "restraint_force_max_eVA": _maximum_movable_force_norm(
                    image, restraint[index]
                ),
                "physical_plus_restraint_force_max_eVA": _maximum_movable_force_norm(
                    image, physical[index] + restraint[index]
                ),
                "projected_neb_force_max_eVA": _maximum_movable_force_norm(
                    image, projected
                ),
            }
        )
    return {
        "interpretation": (
            "physical=model_force_before_constraints; restraint=temporary_harmonic_"
            "force_only; projected_neb=optimizer_force_after_NEB_projection_and_springs"
        ),
        "images": rows,
        "maximum_physical_force_eVA": max(
            row["physical_force_max_eVA"] for row in rows
        ),
        "maximum_restraint_force_eVA": max(
            row["restraint_force_max_eVA"] for row in rows
        ),
        "maximum_projected_neb_force_eVA": max(
            row["projected_neb_force_max_eVA"] for row in rows
        ),
    }


def _optimizer_force_history(log_path: Path) -> dict[str, Any]:
    values: list[float] = []
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if fields and fields[0].startswith("FIRE:"):
                try:
                    values.append(float(fields[-1]))
                except ValueError:
                    continue
    recent = values[-10:]
    return {
        "sample_count": len(values),
        "initial_fmax_eVA": values[0] if values else None,
        "minimum_fmax_eVA": min(values) if values else None,
        "final_fmax_eVA": values[-1] if values else None,
        "recent_fmax_eVA": recent,
        "recent_net_change_eVA": recent[-1] - recent[0] if len(recent) >= 2 else None,
    }


def _persist_stage_snapshot(
    output: Path,
    images: list[Atoms],
    request: dict[str, Any],
    state: dict[str, Any],
    *,
    stage: str,
    converged: bool,
    steps: int,
) -> dict[str, Any]:
    """Write an immutable, hash-bound path snapshot for one completed stage."""

    root = output / "stage_snapshots" / stage
    if root.exists():
        raise FileExistsError(f"stage snapshot already exists: {root}")
    rows: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        path = root / "images" / f"{index:02d}" / "POSCAR"
        _write_vasp_atomic(path, image)
        rows.append(
            {
                "image": f"{index:02d}",
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "document_kind": "dual_model_ml_neb_stage_snapshot",
        "stage": stage,
        "source_request_sha256": state["source_request_sha256"],
        "runner_sha256": state["runner_sha256"],
        "converged": bool(converged),
        "steps": int(steps),
        "image_count": len(images),
        "images": rows,
        "geometry_guards": _geometry_guard_evidence(images, request),
        "temporary_bond_restraint_counts": [
            sum(isinstance(item, HarmonicBondRestraint) for item in image.constraints)
            for image in images
        ],
        "temporary_position_restraint_counts": [
            sum(isinstance(item, HarmonicPositionRestraint) for item in image.constraints)
            for image in images
        ],
        "scientific_status": "restrained_path_snapshot_not_mep",
    }
    manifest_path = root / "snapshot_manifest.json"
    write_json_atomic(manifest_path, manifest, ensure_ascii=True)
    return {
        "stage": stage,
        "manifest_path": manifest_path.relative_to(output).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
        "converged": bool(converged),
        "steps": int(steps),
    }


def _normalize_periodic_branches(images: list[Atoms]) -> list[dict[str, Any]]:
    normalizations: list[dict[str, Any]] = []
    for image_index, (left, right) in enumerate(
        zip(images[:-1], images[1:], strict=True)
    ):
        # Preserve both endpoint coordinate files exactly. If the final pair
        # cannot remain continuous without moving FS, the hard branch guard
        # must reject the path instead of rewriting the accepted endpoint.
        if image_index + 1 == len(images) - 1:
            continue
        fractional = np.linalg.solve(
            left.cell.array.T,
            (right.positions - left.positions).T,
        ).T
        periodic_axes = np.asarray(left.pbc, dtype=bool)
        shifts = np.zeros_like(fractional)
        shifts[:, periodic_axes] = np.round(fractional[:, periodic_axes])
        shifted_atoms = np.flatnonzero(np.any(shifts != 0.0, axis=1))
        if len(shifted_atoms):
            right.positions -= shifts @ left.cell.array
            normalizations.extend(
                {
                    "adjacent_images": [f"{image_index:02d}", f"{image_index + 1:02d}"],
                    "atom_zero_based": int(atom),
                    "lattice_shift": shifts[atom].astype(int).tolist(),
                }
                for atom in shifted_atoms
            )
    return normalizations


def _monitored_row(request: dict[str, Any], name: str) -> dict[str, Any]:
    rows = [
        row
        for row in request["geometry_guards"].get("monitored_bonds", [])
        if row.get("name") == name
    ]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one monitored bond named {name}")
    return rows[0]


def _backtrack_assessment(
    monitored_evidence: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    scope = str(policy.get("monitored_bond_monotonicity_scope", "all_path"))
    if scope not in {"all_path", "important_interval"}:
        raise ValueError(f"unsupported monitored-bond monotonicity scope: {scope}")
    distances = [float(value) for value in monitored_evidence["distances_A"]]
    backtracks = [float(value) for value in monitored_evidence["backtracks_A"]]
    if not backtracks:
        backtracks = [0.0] * max(0, len(distances) - 1)
    low, high = (float(value) for value in monitored_evidence["important_interval_A"])
    tolerance = float(monitored_evidence["important_interval_tolerance_A"])
    selected_pairs: list[int] = []
    for index, (left, right) in enumerate(zip(distances[:-1], distances[1:], strict=True)):
        overlaps_interval = min(left, right) <= high + tolerance and max(left, right) >= low - tolerance
        if scope == "all_path" or overlaps_interval:
            selected_pairs.append(index)
    selected_values = [backtracks[index] for index in selected_pairs]
    observed = max(selected_values, default=0.0)
    pass_limit = float(policy.get("maximum_monitored_bond_backtrack_A", 0.0))
    warning_limit = float(
        policy.get("borderline_monitored_bond_backtrack_A", pass_limit)
    )
    if not 0.0 <= pass_limit <= warning_limit:
        raise ValueError("monitored-bond backtrack thresholds are inconsistent")
    if observed <= pass_limit:
        level = "pass"
    elif observed <= warning_limit:
        level = "borderline_warning"
    else:
        level = "strong_warning_stop_candidate"
    return {
        "scope": scope,
        "pass_limit_A": pass_limit,
        "borderline_upper_limit_A": warning_limit,
        "selected_adjacent_pairs": [
            [f"{index:02d}", f"{index + 1:02d}"] for index in selected_pairs
        ],
        "maximum_observed_backtrack_A": observed,
        "level": level,
        "automatic_failure_from_backtrack_only": False
        if policy.get("monitored_bond_backtrack_mode") == "graded_warning"
        else observed > pass_limit,
    }


def _redistribute_by_monitored_bond(  # noqa: C901 - one linear scientific geometry gate.
    images: list[Atoms], request: dict[str, Any]
) -> dict[str, Any]:
    """Redistribute a continuous path onto a frozen monotonic bond-distance grid."""

    settings = request["reaction_coordinate_redistribution"]
    rule = _monitored_row(request, str(settings["monitored_bond_name"]))
    first, second = (int(value) for value in rule["atoms_zero_based"])
    target_map = {
        int(label): float(value)
        for label, value in settings["target_distances_A"].items()
    }
    before = [float(image.get_distance(first, second, mic=True)) for image in images]

    unwrapped = [images[0].positions.copy()]
    for previous, current in zip(images[:-1], images[1:], strict=True):
        delta, _ = find_mic(current.positions - previous.positions, previous.cell, previous.pbc)
        unwrapped.append(unwrapped[-1] + np.asarray(delta))

    fixed = _fixed_indices(images[0])
    anchor_parameters: dict[int, float] = {0: 0.0, len(images) - 1: float(len(images) - 1)}
    previous_parameter = 0.0
    for target_index, target in target_map.items():
        candidates: list[tuple[float, int, float]] = []
        for segment, (left, right) in enumerate(zip(before[:-1], before[1:], strict=True)):
            if math.isclose(left, right, abs_tol=1.0e-12, rel_tol=0.0):
                continue
            fraction = (target - left) / (right - left)
            parameter = segment + fraction
            if -1.0e-10 <= fraction <= 1.0 + 1.0e-10 and parameter >= previous_parameter - 1.0e-10:
                candidates.append((abs(parameter - target_index), segment, min(1.0, max(0.0, fraction))))
        if not candidates:
            raise RuntimeError(f"cannot map redistribution target {target_index:02d}={target:.6f} A")
        _distance, segment, fraction = min(candidates)
        parameter = segment + fraction
        anchor_parameters[target_index] = parameter
        previous_parameter = parameter

    source_parameters = [0.0] * len(images)
    anchor_indices = sorted(anchor_parameters)
    for left_index, right_index in zip(anchor_indices[:-1], anchor_indices[1:], strict=True):
        left_parameter = anchor_parameters[left_index]
        right_parameter = anchor_parameters[right_index]
        for image_index in range(left_index, right_index + 1):
            fraction = (image_index - left_index) / (right_index - left_index)
            source_parameters[image_index] = left_parameter + fraction * (
                right_parameter - left_parameter
            )

    product_side_evidence: dict[str, Any] | None = None
    product_side = settings.get("product_side_arc_length")
    if product_side is not None:
        start_index = int(product_side["start_image"])
        fixed_set = set(_fixed_indices(images[0]))
        movable = [
            index for index in range(len(images[0])) if index not in fixed_set
        ]
        start_parameter = anchor_parameters[start_index]
        end_parameter = float(len(images) - 1)
        breakpoints = [start_parameter]
        for value in range(math.ceil(start_parameter - 1.0e-12), len(images)):
            if value > start_parameter + 1.0e-12:
                breakpoints.append(float(value))
        if breakpoints[-1] < end_parameter:
            breakpoints.append(end_parameter)
        segments: list[tuple[float, float, float]] = []
        cumulative = [0.0]
        for left_parameter, right_parameter in zip(
            breakpoints[:-1], breakpoints[1:], strict=True
        ):
            segment = int(math.floor((left_parameter + right_parameter) / 2.0))
            displacement = unwrapped[segment + 1] - unwrapped[segment]
            length = float(np.linalg.norm(displacement[movable])) * (
                right_parameter - left_parameter
            )
            segments.append((left_parameter, right_parameter, length))
            cumulative.append(cumulative[-1] + length)
        if cumulative[-1] <= 1.0e-12:
            raise RuntimeError("product-side configuration arc length is zero")
        count = len(images) - start_index
        product_parameters: list[float] = []
        for offset in range(count):
            target_length = cumulative[-1] * offset / (count - 1)
            parameter = end_parameter
            for segment_index, (left_parameter, right_parameter, length) in enumerate(
                segments
            ):
                if target_length <= cumulative[segment_index + 1] + 1.0e-12:
                    fraction = (
                        0.0
                        if length <= 1.0e-12
                        else (target_length - cumulative[segment_index]) / length
                    )
                    parameter = left_parameter + fraction * (
                        right_parameter - left_parameter
                    )
                    break
            product_parameters.append(parameter)
        source_parameters[start_index:] = product_parameters
        product_side_evidence = {
            "method": product_side["method"],
            "start_image": f"{start_index:02d}",
            "end_image": f"{len(images) - 1:02d}",
            "configuration_arc_length_A": cumulative[-1],
            "source_path_parameters": product_parameters,
        }

    corrections: list[float] = []
    new_positions: list[np.ndarray] = []
    for target_index, parameter in enumerate(source_parameters):
        segment = min(len(images) - 2, int(math.floor(parameter)))
        fraction = parameter - segment
        positions = unwrapped[segment] + fraction * (unwrapped[segment + 1] - unwrapped[segment])
        if fixed:
            positions[fixed] = unwrapped[0][fixed]
        correction_norm = 0.0
        if target_index in target_map:
            target = target_map[target_index]
            vector, _ = find_mic(
                positions[second] - positions[first], images[0].cell, images[0].pbc
            )
            norm = float(np.linalg.norm(vector))
            if norm <= 1.0e-12:
                raise RuntimeError("redistribution encountered a zero monitored-bond vector")
            exact_second = positions[first] + np.asarray(vector) * (target / norm)
            correction, _ = find_mic(
                exact_second - positions[second], images[0].cell, images[0].pbc
            )
            correction_norm = float(np.linalg.norm(correction))
            if correction_norm > float(settings["maximum_exact_bond_correction_A"]):
                raise RuntimeError("redistribution exact-bond correction exceeded its limit")
            positions[second] += np.asarray(correction)
        new_positions.append(positions)
        corrections.append(correction_norm)

    for image, positions in zip(images, new_positions, strict=True):
        image.positions[:] = positions
    normalizations = _normalize_periodic_branches(images)
    after_evidence = _geometry_guard_evidence(images, request)
    after = after_evidence["monitored_bonds"][0]["distances_A"]
    if not all(
        math.isclose(after[index], target, abs_tol=1.0e-6, rel_tol=0.0)
        for index, target in target_map.items()
    ):
        raise RuntimeError("redistributed monitored-bond distances missed their targets")
    if not after_evidence["passed"]:
        failed_checks = [
            row["name"]
            for row in [
                *after_evidence["preserved_bonds"],
                *after_evidence["monitored_bonds"],
            ]
            if not row["passed"]
        ]
        failed_checks.extend(
            name
            for name, passed in (
                ("adjacent_rmsd", after_evidence["adjacent_rmsd_passed"]),
                (
                    "maximum_single_movable_atom_step",
                    after_evidence["maximum_single_movable_atom_step_passed"],
                ),
                ("minimum_pair_distance", after_evidence["minimum_pair_distance_passed"]),
                ("periodic_branch", after_evidence["periodic_branch_numeric_passed"]),
            )
            if not passed
        )
        raise RuntimeError(
            "redistributed path failed geometry guards: " + ", ".join(failed_checks)
        )
    return {
        "monitored_bond_name": settings["monitored_bond_name"],
        "before_distances_A": before,
        "target_distances_A": {
            f"{index:02d}": value for index, value in target_map.items()
        },
        "after_distances_A": after,
        "source_path_parameters": source_parameters,
        "product_side_arc_length": product_side_evidence,
        "exact_bond_corrections_A": corrections,
        "maximum_exact_bond_correction_A": max(corrections),
        "periodic_normalizations": normalizations,
        "geometry_guards": after_evidence,
        "scientific_status": "redistributed_restrained_path_not_mep",
    }


def _maximum_adjacent_atom_steps(images: list[Atoms]) -> list[float]:
    fixed = set(_fixed_indices(images[0]))
    movable = [index for index in range(len(images[0])) if index not in fixed]
    values: list[float] = []
    for left, right in zip(images[:-1], images[1:], strict=True):
        delta, _ = find_mic(right.positions - left.positions, left.cell, left.pbc)
        norms = np.linalg.norm(np.asarray(delta)[movable], axis=1)
        values.append(float(norms.max()) if len(norms) else 0.0)
    return values


def _geometry_guard_evidence(images: list[Atoms], request: dict[str, Any]) -> dict[str, Any]:
    guards = request["geometry_guards"]
    preserved: list[dict[str, Any]] = []
    passed = True
    for rule in guards.get("preserved_bonds", []):
        left, right = (int(value) for value in rule["atoms_zero_based"])
        distances = [float(image.get_distance(left, right, mic=True)) for image in images]
        assessment_mode = str(rule.get("assessment_mode", "hard"))
        if assessment_mode not in {"hard", "graded_warning"}:
            raise ValueError(f"unsupported preserved-bond assessment mode: {assessment_mode}")
        accepted_minimum = float(rule["minimum_A"])
        accepted_maximum = float(rule["maximum_A"])
        accepted_window_passed = (
            min(distances) >= accepted_minimum and max(distances) <= accepted_maximum
        )
        if assessment_mode == "graded_warning":
            hard_minimum = float(rule["hard_minimum_A"])
            hard_maximum = float(rule["hard_maximum_A"])
            if not (
                math.isfinite(hard_minimum)
                and math.isfinite(hard_maximum)
                and hard_minimum <= accepted_minimum <= accepted_maximum <= hard_maximum
            ):
                raise ValueError(
                    "graded preserved-bond windows must be finite and nested"
                )
        else:
            hard_minimum = accepted_minimum
            hard_maximum = accepted_maximum
        hard_passed = min(distances) >= hard_minimum and max(distances) <= hard_maximum
        level = (
            "pass"
            if accepted_window_passed
            else "warning"
            if hard_passed
            else "hard_failure"
        )
        rule_passed = hard_passed
        passed = passed and rule_passed
        preserved.append(
            {
                "name": rule["name"],
                "atoms_zero_based": [left, right],
                "distances_A": distances,
                "minimum_A": min(distances),
                "maximum_A": max(distances),
                "assessment_mode": assessment_mode,
                "accepted_window_A": [accepted_minimum, accepted_maximum],
                "accepted_window_passed": accepted_window_passed,
                "hard_window_A": [hard_minimum, hard_maximum],
                "hard_passed": hard_passed,
                "level": level,
                "passed": rule_passed,
            }
        )
    monitored: list[dict[str, Any]] = []
    for rule in guards.get("monitored_bonds", []):
        left, right = (int(value) for value in rule["atoms_zero_based"])
        distances = [float(image.get_distance(left, right, mic=True)) for image in images]
        low, high = (float(value) for value in rule["important_interval_A"])
        interval_tolerance_A = float(rule.get("important_interval_tolerance_A", 0.0))
        if not math.isfinite(interval_tolerance_A) or interval_tolerance_A < 0.0:
            raise ValueError("important-interval tolerance must be finite and non-negative")
        covered = [
            f"{index:02d}"
            for index, value in enumerate(distances[1:-1], start=1)
            if low <= value <= high
        ]
        borderline = [
            f"{index:02d}"
            for index, value in enumerate(distances[1:-1], start=1)
            if not low <= value <= high
            and low - interval_tolerance_A <= value <= high + interval_tolerance_A
        ]
        coverage_passed = len(covered) >= int(rule["minimum_internal_images"])
        coverage_review_required = (
            not coverage_passed
            and len(covered) + len(borderline) >= int(rule["minimum_internal_images"])
        )
        monotonic_direction = rule.get("monotonic_direction")
        maximum_backtrack_A = float(rule.get("maximum_backtrack_A", 0.0))
        if monotonic_direction is None:
            backtracks_A: list[float] = []
            monotonic_passed = True
        elif monotonic_direction == "decreasing":
            backtracks_A = [
                max(0.0, right_value - left_value)
                for left_value, right_value in zip(distances[:-1], distances[1:], strict=True)
            ]
            monotonic_passed = max(backtracks_A, default=0.0) <= maximum_backtrack_A
        elif monotonic_direction == "increasing":
            backtracks_A = [
                max(0.0, left_value - right_value)
                for left_value, right_value in zip(distances[:-1], distances[1:], strict=True)
            ]
            monotonic_passed = max(backtracks_A, default=0.0) <= maximum_backtrack_A
        else:
            raise ValueError(f"unsupported monitored-bond monotonic direction: {monotonic_direction}")
        rule_passed = coverage_passed and monotonic_passed
        passed = passed and rule_passed
        monitored.append(
            {
                "name": rule["name"],
                "atoms_zero_based": [left, right],
                "distances_A": distances,
                "important_interval_A": [low, high],
                "important_interval_tolerance_A": interval_tolerance_A,
                "effective_important_interval_A": [
                    low - interval_tolerance_A,
                    high + interval_tolerance_A,
                ],
                "covered_internal_images": covered,
                "borderline_internal_images": borderline,
                "minimum_internal_images": int(rule["minimum_internal_images"]),
                "coverage_passed": coverage_passed,
                "coverage_review_required": coverage_review_required,
                "coverage_continuation_passed": coverage_passed
                or coverage_review_required,
                "monotonic_direction": monotonic_direction,
                "maximum_backtrack_A": maximum_backtrack_A,
                "backtracks_A": backtracks_A,
                "maximum_observed_backtrack_A": max(backtracks_A, default=0.0),
                "monotonic_passed": monotonic_passed,
                "passed": rule_passed,
            }
        )
    adjacent = _adjacent_rmsd(images)
    maximum_atom_steps = _maximum_adjacent_atom_steps(images)
    minimum_distances = [_minimum_pair_distance(image) for image in images]
    maximum_atom_step_limit = guards.get("maximum_single_movable_atom_step_A")
    numeric = {
        "preserved_bonds": preserved,
        "monitored_bonds": monitored,
        "adjacent_rmsd_A": adjacent,
        "maximum_adjacent_rmsd_A": max(adjacent) if adjacent else 0.0,
        "adjacent_rmsd_passed": bool(adjacent) and max(adjacent) <= float(guards["maximum_adjacent_rmsd_A"]),
        "maximum_single_movable_atom_steps_A": maximum_atom_steps,
        "maximum_single_movable_atom_step_A": max(maximum_atom_steps)
        if maximum_atom_steps
        else 0.0,
        "maximum_single_movable_atom_step_limit_A": maximum_atom_step_limit,
        "maximum_single_movable_atom_step_passed": maximum_atom_step_limit is None
        or bool(maximum_atom_steps)
        and max(maximum_atom_steps) <= float(maximum_atom_step_limit),
        "minimum_pair_distances_A": minimum_distances,
        "minimum_pair_distance_passed": min(minimum_distances) >= float(guards["minimum_pair_distance_A"]),
        "periodic_branch_numeric_passed": _periodic_branch_continuous(images),
    }
    numeric["passed"] = bool(
        passed
        and numeric["adjacent_rmsd_passed"]
        and numeric["maximum_single_movable_atom_step_passed"]
        and numeric["minimum_pair_distance_passed"]
        and numeric["periodic_branch_numeric_passed"]
    )
    return numeric


def _assert_geometry_guards(
    images: list[Atoms],
    request: dict[str, Any],
    stage: str,
    monitored_guard_policy: dict[str, Any] | None = None,
) -> None:
    evidence = _geometry_guard_evidence(images, request)
    # O-H interval coverage is a final-path condition, not a per-step abort;
    # all other failures indicate immediate structural invalidity.
    hard_passed = all(row["passed"] for row in evidence["preserved_bonds"])
    hard_passed = hard_passed and evidence["adjacent_rmsd_passed"]
    hard_passed = hard_passed and evidence["maximum_single_movable_atom_step_passed"]
    hard_passed = hard_passed and evidence["minimum_pair_distance_passed"]
    hard_passed = hard_passed and evidence["periodic_branch_numeric_passed"]
    policy = monitored_guard_policy
    if policy is None and stage == "restrained_preconditioning":
        policy = request["preconditioning"]
    if policy and policy.get("enforce_monitored_bond_monotonicity", False):
        mode = str(policy.get("monitored_bond_backtrack_mode", "hard"))
        if mode not in {"hard", "graded_warning"}:
            raise ValueError(f"unsupported monitored-bond backtrack mode: {mode}")
        assessments = [
            _backtrack_assessment(row, policy) for row in evidence["monitored_bonds"]
        ]
        if mode == "hard":
            hard_passed = hard_passed and all(
                row["level"] == "pass" for row in assessments
            )
    if policy and policy.get("require_monitored_bond_interval_coverage", False):
        coverage_mode = str(policy.get("interval_coverage_mode", "strict"))
        if coverage_mode not in {"strict", "allow_borderline_review"}:
            raise ValueError(f"unsupported interval coverage mode: {coverage_mode}")
        hard_passed = hard_passed and all(
            row["coverage_passed"]
            if coverage_mode == "strict"
            else row["coverage_continuation_passed"]
            for row in evidence["monitored_bonds"]
        )
    if not hard_passed:
        raise RuntimeError(f"{stage} geometry guard failed")


def _optimizer_with_guard(
    images: list[Atoms],
    calculator: Any,
    output: Path,
    state: dict[str, Any],
    request: dict[str, Any],
    *,
    stage: str,
    climb: bool,
    fmax: float,
    max_steps: int,
    spring_constant: float,
    checkpoint_interval: int,
    monitored_guard_policy: dict[str, Any] | None = None,
) -> tuple[NEB, bool, int]:
    # Reuse the canonical optimizer while running hard geometry guards after
    # every optimizer step.  A checkpoint interval of one makes each accepted
    # step restartable and inspectable.
    if checkpoint_interval != 1:
        raise ValueError("dual-model guarded stages require checkpoint_interval=1")
    initial_normalizations = _normalize_periodic_branches(images)
    if initial_normalizations:
        state["periodic_branch_normalization_count"] = int(
            state.get("periodic_branch_normalization_count", 0)
        ) + len(initial_normalizations)
        state["latest_periodic_branch_normalizations"] = initial_normalizations
    def assert_or_record() -> None:
        evidence = _geometry_guard_evidence(images, request)
        if monitored_guard_policy and monitored_guard_policy.get(
            "enforce_monitored_bond_monotonicity", False
        ):
            state["latest_monitored_backtrack_assessment"] = [
                _backtrack_assessment(row, monitored_guard_policy)
                for row in evidence["monitored_bonds"]
            ]
        try:
            _assert_geometry_guards(
                images,
                request,
                stage,
                monitored_guard_policy=monitored_guard_policy,
            )
        except RuntimeError:
            failure = {
                "schema_version": 1,
                "document_kind": "dual_model_ml_neb_geometry_guard_failure",
                "stage": stage,
                "stage_steps": int(state.get("stage_steps", 0)),
                "source_request_sha256": state["source_request_sha256"],
                "runner_sha256": state["runner_sha256"],
                "geometry_guards": evidence,
                "monitored_guard_policy": monitored_guard_policy,
            }
            write_json_atomic(
                output / f"{stage}.geometry_guard_failure.json",
                failure,
                ensure_ascii=True,
            )
            raise

    assert_or_record()

    def normalize_and_guard() -> None:
        normalizations = _normalize_periodic_branches(images)
        if normalizations:
            state["periodic_branch_normalization_count"] = int(
                state.get("periodic_branch_normalization_count", 0)
            ) + len(normalizations)
            state["latest_periodic_branch_normalizations"] = normalizations
        assert_or_record()

    neb, converged, steps = _optimizer_stage(
        images,
        calculator,
        output,
        state,
        stage=stage,
        climb=climb,
        spring_constant=spring_constant,
        fmax=fmax,
        max_steps=max_steps,
        completed_steps=0,
        checkpoint_interval=1,
        step_guard=normalize_and_guard,
    )
    return neb, converged, steps


def _fixed_path_predictions(
    images: list[Atoms],
    primary: Any,
    secondary: Any,
    request: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    symbols = images[0].get_chemical_symbols()
    adsorbate_indices = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    changes = request["reaction"]["indexed_bond_changes"]
    records: list[dict[str, Any]] = []
    primary_values: list[tuple[float, np.ndarray]] = []
    secondary_values: list[tuple[float, np.ndarray]] = []
    for calculator, destination in ((primary, primary_values), (secondary, secondary_values)):
        for image in images:
            _attach_model_context(
                image,
                changes,
                adsorbate_indices,
                is_spin_off=False,
                is_low_fi=False,
            )
            image.calc = calculator
            energy = float(image.get_potential_energy())
            forces = np.asarray(image.get_forces(), dtype=float)
            if not math.isfinite(energy) or forces.shape != (len(image), 3) or not np.isfinite(forces).all():
                raise RuntimeError("model returned non-finite fixed-path energy or forces")
            destination.append((energy, forces.copy()))
    primary_reference = primary_values[0][0]
    secondary_reference = secondary_values[0][0]
    fixed = set(_fixed_indices(images[0]))
    movable = np.asarray([index for index in range(len(images[0])) if index not in fixed], dtype=int)
    for index, image in enumerate(images):
        primary_energy, primary_forces = primary_values[index]
        secondary_energy, secondary_forces = secondary_values[index]
        difference = primary_forces[movable] - secondary_forces[movable]
        norms = np.linalg.norm(difference, axis=1)
        path = output / "images" / f"{index:02d}" / "POSCAR"
        records.append(
            {
                "image": f"{index:02d}",
                "structure_path": path.relative_to(output).as_posix(),
                "structure_sha256": sha256_file(path),
                "primary_energy_eV": primary_energy,
                "secondary_energy_eV": secondary_energy,
                "primary_relative_energy_eV": primary_energy - primary_reference,
                "secondary_relative_energy_eV": secondary_energy - secondary_reference,
                "movable_force_vector_rmse_eVA": float(np.sqrt(np.mean(difference**2))),
                "movable_force_difference_max_norm_eVA": float(norms.max()) if len(norms) else 0.0,
                "key_bond_distances_A": _key_bond_distances(image, changes),
            }
        )
    return {
        "comparison_scope": "exact_structure_hashes; within_model_relative_energy_to_image_00",
        "interpretation": "model_model_disagreement_sampling_score_not_calibrated_uncertainty",
        "images": records,
    }


def _run_restrained_preconditioning(
    images: list[Atoms],
    primary: Any,
    output: Path,
    state: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    precondition = request["preconditioning"]
    target_reference = str(
        precondition.get("constraint_target_reference", "current_stage_start")
    )
    if target_reference not in {"current_stage_start", "initial_request_seed"}:
        raise ValueError(f"unsupported constraint target reference: {target_reference}")
    target_images = (
        [image.copy() for image in images]
        if target_reference == "initial_request_seed"
        else None
    )
    original_constraints, temporary_evidence = _apply_temporary_constraints(
        images,
        precondition["temporary_bond_constraints"],
        float(precondition["restraint_spring_constant_eV_per_A2"]),
        precondition.get("temporary_position_constraints", []),
        float(
            precondition.get(
                "position_restraint_spring_constant_eV_per_A2",
                precondition["restraint_spring_constant_eV_per_A2"],
            )
        ),
        target_images=target_images,
    )
    _neb, converged, steps = _optimizer_with_guard(
        images,
        primary,
        output,
        state,
        request,
        stage="restrained_preconditioning",
        climb=False,
        fmax=float(precondition["fmax_eV_per_A"]),
        max_steps=int(precondition["max_steps"]),
        spring_constant=float(request["ordinary_ml_neb"]["spring_constant_eV_per_A2"]),
        checkpoint_interval=1,
    )
    snapshot = _persist_stage_snapshot(
        output,
        images,
        request,
        state,
        stage="restrained_preconditioning_complete",
        converged=converged,
        steps=steps,
    )
    if precondition.get("require_convergence_before_release", False) and not converged:
        raise RuntimeError("restrained preconditioning did not converge before release")
    _release_temporary_constraints(images, original_constraints)
    return {
        "settings": precondition,
        "target_reference": target_reference,
        "target_images": target_images,
        "temporary_evidence": temporary_evidence,
        "converged": converged,
        "steps": steps,
        "stage_snapshots": [snapshot],
    }


def _record_reaction_coordinate_redistribution(
    images: list[Atoms],
    request: dict[str, Any],
    output: Path,
    state: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    stage: str,
    converged: bool,
    steps: int,
) -> None:
    evidence = _redistribute_by_monitored_bond(images, request)
    snapshot = _persist_stage_snapshot(
        output,
        images,
        request,
        state,
        stage=f"{stage}_reaction_coordinate_redistributed",
        converged=converged,
        steps=steps,
    )
    records.append({"source_stage": stage, "evidence": evidence, "snapshot": snapshot})


def _run_restraint_release_stage(
    images: list[Atoms],
    primary: Any,
    output: Path,
    state: dict[str, Any],
    request: dict[str, Any],
    preparation: dict[str, Any],
    release_stage: dict[str, Any],
    *,
    stage_index: int,
    nonconverged_stage_action: str,
    redistribution_settings: dict[str, Any] | None,
    redistribution_records: list[dict[str, Any]],
) -> dict[str, Any]:
    precondition = preparation["settings"]
    stage_name = f"restraint_release_{stage_index:02d}_{release_stage['name']}"
    original_constraints, constraint_evidence = _apply_temporary_constraints(
        images,
        precondition["temporary_bond_constraints"],
        float(release_stage["bond_spring_constant_eV_per_A2"]),
        precondition.get("temporary_position_constraints", []),
        float(release_stage["position_spring_constant_eV_per_A2"]),
        target_images=preparation["target_images"],
    )
    release_neb, converged, steps = _optimizer_with_guard(
        images,
        primary,
        output,
        state,
        request,
        stage=stage_name,
        climb=False,
        fmax=float(release_stage["fmax_eV_per_A"]),
        max_steps=int(release_stage["max_steps"]),
        spring_constant=float(request["ordinary_ml_neb"]["spring_constant_eV_per_A2"]),
        checkpoint_interval=1,
        monitored_guard_policy=release_stage,
    )
    snapshot = _persist_stage_snapshot(
        output,
        images,
        request,
        state,
        stage=f"{stage_name}_complete",
        converged=converged,
        steps=steps,
    )
    force_decomposition = _stage_force_decomposition(images, release_neb)
    force_history = _optimizer_force_history(output / f"{stage_name}.log")
    warning_codes = [] if converged else ["RESTRAINT_RELEASE_FMAX_TARGET_NOT_REACHED"]
    diagnostic = {
        "schema_version": 1,
        "document_kind": "dual_model_restraint_release_stage_diagnostic",
        "stage": stage_name,
        "source_request_sha256": state["source_request_sha256"],
        "runner_sha256": state["runner_sha256"],
        "converged_to_stage_fmax_target": converged,
        "stage_fmax_target_eVA": float(release_stage["fmax_eV_per_A"]),
        "stage_max_steps": int(release_stage["max_steps"]),
        "stage_steps": steps,
        "nonconverged_stage_action": nonconverged_stage_action,
        "continuation_status": (
            "converged_continue"
            if converged
            else "warning_continue"
            if nonconverged_stage_action == "warning_continue"
            else "hard_fail"
        ),
        "warning_codes": warning_codes,
        "force_history": force_history,
        "force_decomposition": force_decomposition,
        "geometry_guards": _geometry_guard_evidence(images, request),
    }
    diagnostic_path = output / f"{stage_name}.stage_diagnostic.json"
    write_json_atomic(diagnostic_path, diagnostic, ensure_ascii=True)
    _release_temporary_constraints(images, original_constraints)
    if redistribution_settings and redistribution_settings["apply_after_each_release_stage"]:
        _record_reaction_coordinate_redistribution(
            images,
            request,
            output,
            state,
            redistribution_records,
            stage=stage_name,
            converged=converged,
            steps=steps,
        )
    if nonconverged_stage_action == "fail" and not converged:
        raise RuntimeError(f"{stage_name} did not converge before the next release")
    return {
        "stage": stage_name,
        "bond_spring_constant_eV_per_A2": float(
            release_stage["bond_spring_constant_eV_per_A2"]
        ),
        "position_spring_constant_eV_per_A2": float(
            release_stage["position_spring_constant_eV_per_A2"]
        ),
        "converged": converged,
        "steps": steps,
        "fmax_target_eVA": float(release_stage["fmax_eV_per_A"]),
        "nonconverged_stage_action": nonconverged_stage_action,
        "warning_codes": warning_codes,
        "force_history": force_history,
        "force_decomposition": force_decomposition,
        "stage_diagnostic": {
            "path": diagnostic_path.relative_to(output).as_posix(),
            "sha256": sha256_file(diagnostic_path),
        },
        "temporary_constraints_applied": constraint_evidence,
        "snapshot": snapshot,
    }


def _run_constraint_preparation(
    images: list[Atoms],
    primary: Any,
    output: Path,
    state: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    if request["preconditioning"].get("enabled", True) is False:
        _assert_geometry_guards(
            images,
            request,
            "unrestrained_seed",
            monitored_guard_policy=request["ordinary_ml_neb"].get(
                "monitored_geometry_guard"
            ),
        )
        snapshot = _persist_stage_snapshot(
            output,
            images,
            request,
            state,
            stage="unrestrained_seed_validated",
            converged=True,
            steps=0,
        )
        release_evidence = {
            "temporary_constraints_applied": [],
            "stage_snapshots": [snapshot],
            "staged_release": [],
            "nonconverged_stage_action": "not_applicable",
            "constraint_target_reference": "prevalidated_unrestrained_seed",
            "reaction_coordinate_redistributions": [],
            "released_before_ordinary_ml_neb": True,
            "post_release_fixed_atom_indices_zero_based": [
                _fixed_indices(image) for image in images
            ],
            "post_release_internal_coordinate_constraint_count": [
                0 for _image in images
            ],
            "post_release_position_restraint_count": [0 for _image in images],
        }
        _write_restart(output, images, {**state, "stage": "unrestrained_seed_validated"})
        return {
            "precondition_converged": True,
            "precondition_steps": 0,
            "release_evidence": release_evidence,
        }
    preparation = _run_restrained_preconditioning(images, primary, output, state, request)
    redistribution_settings = request.get("reaction_coordinate_redistribution")
    redistribution_records: list[dict[str, Any]] = []
    if redistribution_settings and redistribution_settings["apply_after_preconditioning"]:
        _record_reaction_coordinate_redistribution(
            images,
            request,
            output,
            state,
            redistribution_records,
            stage="restrained_preconditioning",
            converged=preparation["converged"],
            steps=preparation["steps"],
        )

    release_request = request.get("restraint_release", {})
    nonconverged_stage_action = release_request.get(
        "nonconverged_stage_action",
        "fail"
        if release_request.get("require_each_stage_convergence", False)
        else "warning_continue",
    )
    stage_records = [
        _run_restraint_release_stage(
            images,
            primary,
            output,
            state,
            request,
            preparation,
            release_stage,
            stage_index=stage_index,
            nonconverged_stage_action=nonconverged_stage_action,
            redistribution_settings=redistribution_settings,
            redistribution_records=redistribution_records,
        )
        for stage_index, release_stage in enumerate(
            release_request.get("stages", []), start=1
        )
    ]
    preparation["stage_snapshots"].extend(record["snapshot"] for record in stage_records)
    if redistribution_settings and redistribution_settings["apply_before_ordinary_ml_neb"]:
        _record_reaction_coordinate_redistribution(
            images,
            request,
            output,
            state,
            redistribution_records,
            stage="pre_ordinary_ml_neb",
            converged=True,
            steps=0,
        )

    release_evidence = {
        "temporary_constraints_applied": preparation["temporary_evidence"],
        "stage_snapshots": preparation["stage_snapshots"],
        "staged_release": stage_records,
        "nonconverged_stage_action": nonconverged_stage_action,
        "constraint_target_reference": preparation["target_reference"],
        "reaction_coordinate_redistributions": redistribution_records,
        "released_before_ordinary_ml_neb": True,
        "post_release_fixed_atom_indices_zero_based": [_fixed_indices(image) for image in images],
        "post_release_internal_coordinate_constraint_count": [
            sum(isinstance(item, HarmonicBondRestraint) for item in image.constraints)
            for image in images
        ],
        "post_release_position_restraint_count": [
            sum(isinstance(item, HarmonicPositionRestraint) for item in image.constraints)
            for image in images
        ],
    }
    _write_restart(output, images, {**state, "stage": "temporary_constraints_released"})
    return {
        "precondition_converged": preparation["converged"],
        "precondition_steps": preparation["steps"],
        "release_evidence": release_evidence,
    }


def _assert_final_path_or_record(
    images: list[Atoms],
    request: dict[str, Any],
    output: Path,
    state: dict[str, Any],
    final_steps: int,
) -> dict[str, Any]:
    geometry = _geometry_guard_evidence(images, request)
    policy = request.get(
        "final_geometry_guard",
        {
            "enforce_monitored_bond_monotonicity": True,
            "maximum_monitored_bond_backtrack_A": 0.0,
            "require_monitored_bond_interval_coverage": True,
        },
    )
    try:
        _assert_geometry_guards(
            images,
            request,
            "final_path",
            monitored_guard_policy=policy,
        )
    except RuntimeError:
        write_json_atomic(
            output / "final_path.geometry_guard_failure.json",
            {
                "schema_version": 1,
                "document_kind": "dual_model_ml_neb_geometry_guard_failure",
                "stage": "final_path",
                "stage_steps": int(final_steps),
                "source_request_sha256": state["source_request_sha256"],
                "runner_sha256": state["runner_sha256"],
                "geometry_guards": geometry,
                "monitored_guard_policy": policy,
            },
            ensure_ascii=True,
        )
        raise
    return geometry


def _run_primary_path(
    images: list[Atoms],
    primary: Any,
    output: Path,
    state: dict[str, Any],
    request: dict[str, Any],
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    ordinary = request["ordinary_ml_neb"]
    ordinary_neb, ordinary_converged, ordinary_steps = _optimizer_with_guard(
        images,
        primary,
        output,
        state,
        request,
        stage="ordinary_ml_neb",
        climb=False,
        fmax=float(ordinary["fmax_eV_per_A"]),
        max_steps=int(ordinary["max_steps"]),
        spring_constant=float(ordinary["spring_constant_eV_per_A2"]),
        checkpoint_interval=1,
        monitored_guard_policy=ordinary.get("monitored_geometry_guard"),
    )
    settings = RunSettings(
        images_per_segment=3,
        spring_constant_eV_per_A2=float(ordinary["spring_constant_eV_per_A2"]),
        ordinary_fmax_eV_per_A=float(ordinary["fmax_eV_per_A"]),
        ordinary_max_steps=int(ordinary["max_steps"]),
        ml_ci=str(ordinary["ml_ci"]),
        ci_fmax_eV_per_A=float(ordinary["ci_fmax_eV_per_A"]),
        ci_max_steps=int(ordinary["ci_max_steps"]),
        max_adjacent_rmsd_A=float(request["geometry_guards"]["maximum_adjacent_rmsd_A"]),
        minimum_pair_distance_A=float(request["geometry_guards"]["minimum_pair_distance_A"]),
        checkpoint_interval=1,
    )
    _ordinary_rows, ordinary_summary = _evaluate_path(
        images, ordinary_neb, changes, output / "ordinary", settings
    )
    ready, readiness_reasons = _ci_readiness(
        ordinary_summary["energies_eV"],
        ordinary_summary["adjacent_rmsd_A"],
        ordinary_converged,
        settings.max_adjacent_rmsd_A,
    )
    run_ci = settings.ml_ci in {"auto", "on"} and ready
    final_neb = ordinary_neb
    final_stage = "ordinary_ml_neb"
    final_converged = ordinary_converged
    final_steps = ordinary_steps
    ci_record: dict[str, Any] = {
        "requested": settings.ml_ci,
        "readiness_passed": ready,
        "readiness_reasons": readiness_reasons,
        "ran": run_ci,
    }
    if run_ci:
        final_neb, final_converged, final_steps = _optimizer_with_guard(
            images,
            primary,
            output,
            state,
            request,
            stage="ml_ci_neb",
            climb=True,
            fmax=settings.ci_fmax_eV_per_A,
            max_steps=settings.ci_max_steps,
            spring_constant=settings.spring_constant_eV_per_A2,
            checkpoint_interval=1,
            monitored_guard_policy=ordinary.get("monitored_geometry_guard"),
        )
        final_stage = "ml_ci_neb"
        ci_record.update({"converged": final_converged, "steps": final_steps})

    rows, summary = _evaluate_path(images, final_neb, changes, output, settings)
    return {
        "rows": rows,
        "summary": summary,
        "geometry": _assert_final_path_or_record(
            images, request, output, state, final_steps
        ),
        "ordinary_converged": ordinary_converged,
        "ordinary_steps": ordinary_steps,
        "ci_record": ci_record,
        "final_stage": final_stage,
        "final_converged": final_converged,
        "final_steps": final_steps,
    }


def _add_fixed_path_comparison(
    images: list[Atoms],
    primary: Any,
    secondary: Any,
    request: dict[str, Any],
    output: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    comparison = _fixed_path_predictions(images, primary, secondary, request, output)
    comparison_by_image = {row["image"]: row for row in comparison["images"]}
    for row in rows:
        compared = comparison_by_image[row["image"]]
        row["model_disagreement"] = {
            "movable_force_vector_rmse_eVA": compared["movable_force_vector_rmse_eVA"],
            "movable_force_difference_max_norm_eVA": compared[
                "movable_force_difference_max_norm_eVA"
            ],
        }
        row["model_disagreement_reason"] = "two_distinct_models_exact_same_structure"
        row["uncertainty_status"] = "sampling_score_not_calibrated_uncertainty"
    return comparison


def _build_candidate_manifest(
    request_path: Path,
    output: Path,
    request: dict[str, Any],
    models: dict[str, Any],
    preparation: dict[str, Any],
    path_result: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    summary = path_result["summary"]
    peaks = _strict_internal_peaks(summary["energies_eV"])
    return {
        "schema_version": 1,
        "document_kind": "dual_model_gpu_ml_neb_path_manifest",
        "status": "needs_work_review",
        "result_class": "predicted_path_candidate_only",
        "run_kind": request["run_kind"],
        "source_request": {
            "path": os.path.relpath(request_path, output),
            "sha256": sha256_file(request_path),
        },
        "models": models,
        "runner_sha256": sha256_file(Path(__file__)),
        "reaction": request["reaction"],
        "optimizer": {
            "restrained_preconditioning": {
                "converged": preparation["precondition_converged"],
                "steps": preparation["precondition_steps"],
            },
            "constraint_release": preparation["release_evidence"],
            "ordinary_ml_neb": {
                "converged": path_result["ordinary_converged"],
                "steps": path_result["ordinary_steps"],
            },
            "ml_ci_neb": path_result["ci_record"],
            "final_stage": path_result["final_stage"],
            "final_converged": path_result["final_converged"],
            "final_steps": path_result["final_steps"],
        },
        "images": path_result["rows"],
        "adjacent_rmsd_A": summary["adjacent_rmsd_A"],
        "geometry_guards": path_result["geometry"],
        "single_strict_internal_peak": len(peaks) == 1,
        "strict_internal_peak_images": [f"{index:02d}" for index in peaks],
        "fixed_path_model_comparison": comparison,
        "restrictions": {
            "predicted_candidate_only": True,
            "reportable_dft": False,
            "automatic_vasp_submission": False,
            "dimer_parent_accepted": False,
        },
    }


def run_dual_model_request(
    request_path: Path,
    primary_checkpoint: Path,
    secondary_checkpoint: Path,
    output: Path,
    *,
    device: str,
    calculator_loader: CalculatorLoader = _load_calculator,
) -> dict[str, Any]:
    request_path = request_path.resolve()
    request = _load_request(request_path)
    if "sella_refinement" in request:
        require_sella()  # Fail before loading models or spending NEB steps.
    models = request["models"]
    _verify_checkpoint(primary_checkpoint, models["primary"]["checkpoint_sha256"], "primary")
    _verify_checkpoint(secondary_checkpoint, models["secondary"]["checkpoint_sha256"], "secondary")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    images = _load_images(request, request_path.parent)
    if "sella_refinement" in request and any(
        not isinstance(constraint, FixAtoms) for image in images for constraint in image.constraints
    ):
        raise ValueError("Sella branch requires full-atom Selective Dynamics; partial masks are not supported")
    changes = request["reaction"]["indexed_bond_changes"]
    symbols = images[0].get_chemical_symbols()
    adsorbate_indices = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    for image in images:
        _attach_model_context(image, changes, adsorbate_indices, is_spin_off=False, is_low_fi=False)

    primary = calculator_loader("matris", primary_checkpoint, device)
    state: dict[str, Any] = {
        "document_kind": "dual_model_ml_neb_runtime_state",
        "source_request_sha256": sha256_file(request_path),
        "runner_sha256": sha256_file(Path(__file__)),
        "stage": "initialized",
        "image_count": len(images),
    }
    _write_restart(output, images, state)

    preparation = _run_constraint_preparation(images, primary, output, state, request)
    path_result = _run_primary_path(
        images, primary, output, state, request, changes
    )
    secondary = calculator_loader("aqcat25", secondary_checkpoint, device)
    comparison = _add_fixed_path_comparison(
        images,
        primary,
        secondary,
        request,
        output,
        path_result["rows"],
    )

    manifest = _build_candidate_manifest(
        request_path,
        output,
        request,
        models,
        preparation,
        path_result,
        comparison,
    )
    if "sella_refinement" in request:
        manifest["sella_refinement"] = _refine_path_peak(images, primary, request, manifest, output)
    manifest_path = output / "dual_model_gpu_ml_neb_path_manifest.candidate.json"
    write_json_atomic(manifest_path, manifest, ensure_ascii=True)
    state.update(
        {
            "stage": "complete_awaiting_work_review",
            "candidate_manifest": str(manifest_path),
            "candidate_manifest_sha256": sha256_file(manifest_path),
        }
    )
    _write_restart(output, images, state)
    return manifest


def _refine_path_peak(images, primary, request, manifest, output):
    peaks = manifest["strict_internal_peak_images"]
    if (not manifest["optimizer"]["final_converged"]
            or manifest["geometry_guards"].get("passed") is not True or len(peaks) != 1):
        return {"status": "blocked", "reason": "requires_converged_geometry_valid_single_peak_path",
                "model_error_assumed": False, "scientifically_validated_ts": False}
    peak = int(peaks[0])

    def geometry_check(candidate):
        trial = list(images)
        trial[peak] = candidate
        return _geometry_guard_evidence(trial, request)

    result = refine_peak(images[peak], primary, request["sella_refinement"], output / "sella",
                         source={"source_request_sha256": manifest["source_request"]["sha256"],
                                 "checkpoint_sha256": request["models"]["primary"]["checkpoint_sha256"],
                                 "peak_image": peaks[0],
                                 "seed_structure_sha256": manifest["images"][peak]["structure_sha256"]},
                         geometry_check=geometry_check)
    return {"status": result["status"], "path": "sella/candidate_manifest.json",
            "sha256": sha256_file(output / "sella/candidate_manifest.json"),
            "scientifically_validated_ts": False}


def seal_successful_run(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_path = output / "dual_model_gpu_ml_neb_path_manifest.candidate.json"
    if not manifest_path.is_file() or load_json_object(manifest_path) != manifest:
        raise ValueError("cannot seal a changed or missing dual-model candidate manifest")
    exit_record = {
        "gpu_job_id": str(os.environ.get("SLURM_JOB_ID", "local_test")),
        "hostname": socket.gethostname(),
        "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "exit_code": 0,
        "status": "success",
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    }
    exit_path = output / "producer_exit_record.json"
    write_json_atomic(exit_path, exit_record, ensure_ascii=True)
    sealed = {
        **manifest,
        "producer": {
            "backend": "aqcat_gpu",
            "hostname": exit_record["hostname"],
            "gpu_job_id": exit_record["gpu_job_id"],
        },
        "producer_exit_record": {
            "path": exit_path.relative_to(output).as_posix(),
            "sha256": sha256_file(exit_path),
            "status": "success",
            "exit_code": 0,
            "evidence_class": exit_record["evidence_class"],
        },
    }
    write_json_atomic(manifest_path, sealed, ensure_ascii=True)
    return sealed


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--primary-checkpoint", type=Path, required=True)
    parser.add_argument("--secondary-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    manifest = run_dual_model_request(
        args.request,
        args.primary_checkpoint,
        args.secondary_checkpoint,
        args.output,
        device=args.device,
    )
    sealed = seal_successful_run(args.output, manifest)
    print(
        json.dumps(
            {
                "status": sealed["status"],
                "run_kind": sealed["run_kind"],
                "images": len(sealed["images"]),
                "geometry_passed": sealed["geometry_guards"]["passed"],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
