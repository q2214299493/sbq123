#!/usr/bin/env python3
"""Run a hash-bound AQCat25 ASE ML-NEB path and emit reviewable evidence.

The runner never submits VASP and never marks its own path scientifically
accepted.  It uses one shared AQCat25 calculator serially across all images so
the checkpoint is loaded once on the GPU rather than once per image.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import ase
from ase import Atoms
from ase.constraints import FixAtoms
from ase.geometry import find_mic
from ase.io import read, write
from ase.mep import NEB
from ase.mep.neb import NEBState
from ase.optimize import FIRE

try:
    from scripts.aqcat25_handoff import validate_handoff
    from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from aqcat25_handoff import validate_handoff
    from artifact_io import load_json_object, sha256_file, write_json_atomic


CalculatorFactory = Callable[[], Any]


@dataclass(frozen=True)
class RunSettings:
    images_per_segment: int = 5
    spring_constant_eV_per_A2: float = 0.10
    ordinary_fmax_eV_per_A: float = 0.10
    ordinary_max_steps: int = 300
    ml_ci: str = "auto"
    ci_fmax_eV_per_A: float = 0.05
    ci_max_steps: int = 200
    max_adjacent_rmsd_A: float = 0.75
    minimum_pair_distance_A: float = 0.65
    checkpoint_interval: int = 5

    def __post_init__(self) -> None:
        if self.images_per_segment < 3:
            raise ValueError("images_per_segment must be at least 3")
        if self.ml_ci not in {"auto", "on", "off"}:
            raise ValueError("ml_ci must be auto, on, or off")
        positive = (
            self.spring_constant_eV_per_A2,
            self.ordinary_fmax_eV_per_A,
            self.ci_fmax_eV_per_A,
            self.max_adjacent_rmsd_A,
            self.minimum_pair_distance_A,
        )
        if any(value <= 0 or not math.isfinite(value) for value in positive):
            raise ValueError("ML-NEB force, spring, distance, and RMSD settings must be finite and positive")
        if self.ordinary_max_steps < 0 or self.ci_max_steps < 0 or self.checkpoint_interval < 1:
            raise ValueError("ML-NEB step limits must be non-negative and checkpoint interval positive")


def _structure_path(root: Path, ref: dict[str, Any]) -> Path:
    path = (root / str(ref["path"])).resolve()
    if not path.is_file() or sha256_file(path) != ref["sha256"]:
        raise ValueError(f"structure reference is missing or changed: {ref['path']}")
    return path


def _fixed_indices(atoms: Atoms) -> list[int]:
    fixed: set[int] = set()
    for constraint in atoms.constraints:
        # Internal-coordinate constraints also expose ``get_indices``.  They
        # must not be mistaken for the slab's Selective-Dynamics FixAtoms mask.
        if isinstance(constraint, FixAtoms):
            fixed.update(int(index) for index in constraint.get_indices())
    return sorted(fixed)


def _movable_indices(atoms: Atoms) -> np.ndarray:
    movable = np.ones(len(atoms), dtype=bool)
    movable[_fixed_indices(atoms)] = False
    return np.flatnonzero(movable)


def _attach_model_context(
    atoms: Atoms,
    bond_changes: list[dict[str, Any]],
    adsorbate_indices: list[int],
    *,
    is_spin_off: bool,
    is_low_fi: bool,
) -> None:
    atoms.info["is_spin_off"] = is_spin_off
    atoms.info["is_low_fi"] = is_low_fi
    atoms.info["bonds_TS"] = [
        [change["atoms_1based"][0] - 1, change["atoms_1based"][1] - 1, change["change"]]
        for change in bond_changes
    ]
    atoms.info["indices_ads"] = adsorbate_indices


def _read_states(handoff: dict[str, Any], root: Path) -> list[Atoms]:
    transition = handoff["transition_state"]
    refs = [
        transition["initial_structure"],
        *transition["waypoint_structures"],
        transition["final_structure"],
    ]
    states = [read(_structure_path(root, ref), format="vasp") for ref in refs]
    if len(states) < 2:
        raise ValueError("ML-NEB requires at least IS and FS")
    fixed = _fixed_indices(states[0])
    for state in states[1:]:
        if _fixed_indices(state) != fixed:
            raise ValueError("ML-NEB endpoint/waypoint fixed masks differ")
        if fixed:
            delta, _ = find_mic(
                state.positions[fixed] - states[0].positions[fixed], states[0].cell, states[0].pbc
            )
            if not np.allclose(delta, 0.0, atol=1.0e-8, rtol=0.0):
                raise ValueError("ML-NEB endpoint/waypoint fixed atom coordinates differ")
    return states


def build_idpp_path(states: list[Atoms], images_per_segment: int) -> list[Atoms]:
    if images_per_segment < 3:
        raise ValueError("images_per_segment must be at least 3")
    try:
        from ase.mep.neb import idpp_interpolate
    except ImportError:  # ASE < 3.23 compatibility on a deployed GPU image.
        from ase.neb import idpp_interpolate

    result: list[Atoms] = []
    for segment_index, (left, right) in enumerate(zip(states[:-1], states[1:], strict=True)):
        segment = [left.copy(), *(left.copy() for _ in range(images_per_segment - 2)), right.copy()]
        neb = NEB(segment, method="improvedtangent")
        neb.interpolate(method="linear", mic=True, apply_constraint=True)
        idpp_interpolate(neb, fmax=0.05, mic=True, steps=200, traj=None, log=None)
        _unwrap_path(segment)
        result.extend(segment if segment_index == 0 else segment[1:])
    return result


def _unwrap_path(images: list[Atoms]) -> None:
    for previous, current in zip(images[:-1], images[1:], strict=True):
        delta, _ = find_mic(current.positions - previous.positions, previous.cell, previous.pbc)
        current.positions[:] = previous.positions + delta


def _write_vasp_atomic(path: Path, atoms: Atoms) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    # VASP POSCAR cannot serialize transient internal-coordinate constraints.
    # Restart structures retain only the Selective-Dynamics FixAtoms mask;
    # stage-specific constraints are recreated from the hash-bound request.
    serializable = atoms.copy()
    serializable.set_constraint(
        [constraint for constraint in serializable.constraints if isinstance(constraint, FixAtoms)]
    )
    write(temporary, serializable, format="vasp", direct=True, vasp5=True)
    os.replace(temporary, path)


def _write_restart(
    output: Path,
    images: list[Atoms],
    state: dict[str, Any],
) -> None:
    restart = output / "restart"
    for index, image in enumerate(images):
        _write_vasp_atomic(restart / f"{index:02d}" / "POSCAR", image)
    write_json_atomic(output / "ml_neb_state.json", state, ensure_ascii=True)


def _load_restart(output: Path, image_count: int) -> list[Atoms]:
    paths = [output / "restart" / f"{index:02d}" / "POSCAR" for index in range(image_count)]
    if not all(path.is_file() for path in paths):
        raise ValueError("resume requested but the restart image set is incomplete")
    return [read(path, format="vasp") for path in paths]


def _optimizer_stage(
    images: list[Atoms],
    calculator: Any,
    output: Path,
    state: dict[str, Any],
    *,
    stage: str,
    climb: bool,
    spring_constant: float,
    fmax: float,
    max_steps: int,
    completed_steps: int,
    checkpoint_interval: int,
    step_guard: Callable[[], None] | None = None,
) -> tuple[NEB, bool, int]:
    for image in images:
        image.calc = calculator
    neb = NEB(
        images,
        k=spring_constant,
        climb=climb,
        parallel=False,
        method="improvedtangent",
        allow_shared_calculator=True,
    )
    remaining = max(0, max_steps - completed_steps)
    optimizer = FIRE(neb, logfile=str(output / f"{stage}.log"))

    def checkpoint() -> None:
        total_steps = completed_steps + int(optimizer.nsteps)
        state.update({"stage": f"{stage}_running", "stage_steps": total_steps})
        _write_restart(output, images, state)

    optimizer.attach(checkpoint, interval=max(1, checkpoint_interval))
    if step_guard is not None:
        optimizer.attach(step_guard, interval=1)
    converged = bool(optimizer.run(fmax=fmax, steps=remaining))
    total_steps = completed_steps + int(optimizer.nsteps)
    state.update({"stage": f"{stage}_complete", "stage_steps": total_steps, "converged": converged})
    _write_restart(output, images, state)
    return neb, converged, total_steps


def _max_atom_norm(values: np.ndarray, movable: np.ndarray) -> float:
    if not len(movable):
        return 0.0
    return float(np.linalg.norm(values[movable], axis=1).max())


def _spring_forces(neb: NEB) -> np.ndarray:
    spring_forces = np.zeros((len(neb.images), len(neb.images[0]), 3), dtype=float)
    state = NEBState(neb, neb.images, np.asarray(neb.energies, dtype=float))
    spring1 = state.spring(0)
    for index in range(1, len(neb.images) - 1):
        spring2 = state.spring(index)
        tangent = neb.neb_method.get_tangent(state, spring1, spring2, index)
        if not (neb.climb and index == state.imax):
            spring_forces[index] = (spring2.nt * spring2.k - spring1.nt * spring1.k) * tangent
        spring1 = spring2
    return spring_forces


def _adjacent_rmsd(images: list[Atoms]) -> list[float]:
    movable = _movable_indices(images[0])
    values: list[float] = []
    for left, right in zip(images[:-1], images[1:], strict=True):
        delta, _ = find_mic(right.positions - left.positions, left.cell, left.pbc)
        values.append(float(np.sqrt(np.mean(np.sum(delta[movable] ** 2, axis=1)))))
    return values


def _periodic_branch_continuous(images: list[Atoms], tolerance: float = 1.0e-8) -> bool:
    for left, right in zip(images[:-1], images[1:], strict=True):
        fractional = np.linalg.solve(left.cell.array.T, (right.positions - left.positions).T).T
        periodic_axes = np.asarray(left.pbc, dtype=bool)
        if np.any(np.abs(fractional[:, periodic_axes]) > 0.5 + tolerance):
            return False
    return True


def _minimum_pair_distance(atoms: Atoms) -> float:
    distances = atoms.get_all_distances(mic=True)
    upper = distances[np.triu_indices(len(atoms), k=1)]
    return float(upper.min()) if upper.size else math.inf


def _key_bond_distances(atoms: Atoms, changes: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for change in changes:
        first, second = change["atoms_1based"]
        label = f"{change['change']}:{first}-{second}"
        result[label] = float(atoms.get_distance(first - 1, second - 1, mic=True))
    return result


def _reaction_progress(images: list[Atoms], changes: list[dict[str, Any]]) -> list[float]:
    bond_rows = [_key_bond_distances(image, changes) for image in images]
    labels = list(bond_rows[0])
    progress: list[float] = []
    for row in bond_rows:
        components = []
        for label in labels:
            start, finish = bond_rows[0][label], bond_rows[-1][label]
            if abs(finish - start) > 1.0e-8:
                components.append((row[label] - start) / (finish - start))
        progress.append(float(np.mean(components)) if components else 0.0)
    return progress


def _strict_internal_peaks(energies: list[float]) -> list[int]:
    return [
        index
        for index in range(1, len(energies) - 1)
        if energies[index - 1] < energies[index] > energies[index + 1]
    ]


def _ci_readiness(
    energies: list[float], adjacent_rmsd_A: list[float], ordinary_converged: bool, threshold_A: float
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    peaks = _strict_internal_peaks(energies)
    if not ordinary_converged:
        reasons.append("ordinary_ml_neb_not_converged")
    if len(peaks) != 1:
        reasons.append(f"strict_internal_peak_count_{len(peaks)}")
    if not adjacent_rmsd_A or max(adjacent_rmsd_A) > threshold_A:
        reasons.append("adjacent_rmsd_exceeds_continuity_threshold")
    return not reasons, reasons


def _evaluate_path(
    images: list[Atoms],
    neb: NEB,
    changes: list[dict[str, Any]],
    output: Path,
    settings: RunSettings,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    projected = np.asarray(neb.get_forces(), dtype=float).reshape((len(images) - 2, len(images[0]), 3))
    energies = [float(image.get_potential_energy()) for image in images]
    physical = [np.asarray(image.get_forces(), dtype=float) for image in images]
    spring = _spring_forces(neb)
    progress = _reaction_progress(images, changes)
    adjacent = _adjacent_rmsd(images)
    rows: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        image_path = output / "images" / f"{index:02d}" / "POSCAR"
        _write_vasp_atomic(image_path, image)
        movable = _movable_indices(image)
        projected_force = np.zeros((len(image), 3), dtype=float)
        if 0 < index < len(images) - 1:
            projected_force = projected[index - 1]
        rows.append(
            {
                "image": f"{index:02d}",
                "structure_path": image_path.relative_to(output).as_posix(),
                "structure_sha256": sha256_file(image_path),
                "predicted_energy_eV": energies[index],
                "predicted_physical_force_max_eVA": _max_atom_norm(physical[index], movable),
                "projected_neb_force_max_eVA": _max_atom_norm(projected_force, movable),
                "spring_force_max_eVA": _max_atom_norm(spring[index], movable),
                "reaction_coordinate_value": progress[index],
                "key_bond_distances_A": _key_bond_distances(image, changes),
                "minimum_pair_distance_A": _minimum_pair_distance(image),
                "model_disagreement": None,
                "model_disagreement_reason": "single_checkpoint_has_no_committee_disagreement",
                "uncertainty_status": "single_checkpoint_no_per_image_uncertainty",
            }
        )
    numeric = {
        "adjacent_rmsd_passed": bool(adjacent and max(adjacent) <= settings.max_adjacent_rmsd_A),
        "periodic_branch_numeric_passed": _periodic_branch_continuous(images),
        "minimum_pair_distance_passed": all(
            row["minimum_pair_distance_A"] >= settings.minimum_pair_distance_A for row in rows
        ),
        "single_strict_internal_peak": len(_strict_internal_peaks(energies)) == 1,
        "strict_internal_peak_images": [f"{index:02d}" for index in _strict_internal_peaks(energies)],
    }
    return rows, {"adjacent_rmsd_A": adjacent, "numeric_screen": numeric, "energies_eV": energies}


def _label_candidates(rows: list[dict[str, Any]], adjacent_rmsd: list[float]) -> list[dict[str, Any]]:
    internal = rows[1:-1]
    if not internal:
        return []
    peak = max(internal, key=lambda row: row["predicted_energy_eV"])
    peak_index = int(peak["image"])
    selected: dict[int, set[str]] = {}

    def add(index: int, reason: str) -> None:
        if 0 <= index < len(rows):
            selected.setdefault(index, set()).add(reason)

    add(peak_index, "highest_predicted_energy")
    add(peak_index - 1, "peak_left_neighbor")
    add(peak_index + 1, "peak_right_neighbor")
    if peak_index > 1:
        add(max(1, peak_index // 2), "rising_path_representative")
    if peak_index < len(rows) - 2:
        add(min(len(rows) - 2, peak_index + (len(rows) - 1 - peak_index) // 2), "falling_path_representative")
    if adjacent_rmsd:
        largest_link = int(np.argmax(adjacent_rmsd))
        add(largest_link, "largest_adjacent_rmsd_link")
        add(largest_link + 1, "largest_adjacent_rmsd_link")
    return [
        {"image": f"{index:02d}", "reasons": sorted(reasons)}
        for index, reasons in sorted(selected.items())
    ]


def _build_aqcat_calculator(checkpoint: Path, is_spin_off: bool, is_low_fi: bool) -> Any:
    import torch
    from fairchem.core.common.relaxation.ase_utils import patched_calc
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the production AQCat25 ML-NEB runner")
    return patched_calc(
        checkpoint_path=str(checkpoint),
        is_spin_off=is_spin_off,
        is_low_fi=is_low_fi,
    )


def run_from_handoff(
    handoff_path: Path,
    checkpoint: Path,
    output: Path,
    *,
    schema_path: Path,
    settings: RunSettings,
    calculator_factory: CalculatorFactory,
    is_spin_off: bool = False,
    is_low_fi: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    handoff = validate_handoff(handoff_path, root=handoff_path.parent, schema_path=schema_path)
    if handoff.get("workflow_kind") != "transition_state":
        raise ValueError("ML-NEB runner requires a transition_state handoff")
    if sha256_file(checkpoint) != handoff["model"]["checkpoint_sha256"]:
        raise ValueError("checkpoint SHA256 does not match the handoff")
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    transition = handoff["transition_state"]
    states = _read_states(handoff, handoff_path.parent)
    image_count = 1 + (len(states) - 1) * (settings.images_per_segment - 1)
    state_path = output / "ml_neb_state.json"
    state = load_json_object(state_path) if resume and state_path.is_file() else {
        "document_kind": "aqcat25_ml_neb_runtime_state",
        "source_handoff_sha256": sha256_file(handoff_path),
        "checkpoint_sha256": sha256_file(checkpoint),
        "model_identifier": handoff["model"]["identifier"],
        "runner_sha256": sha256_file(Path(__file__)),
        "software": {"ase_version": ase.__version__, "numpy_version": np.__version__},
        "run_settings": asdict(settings),
        "image_count": image_count,
        "stage": "initialized",
        "stage_steps": 0,
    }
    if state["source_handoff_sha256"] != sha256_file(handoff_path) or state["checkpoint_sha256"] != sha256_file(
        checkpoint
    ):
        raise ValueError("resume state is not bound to the current handoff/checkpoint")
    if state.get("runner_sha256") != sha256_file(Path(__file__)) or state.get("run_settings") != asdict(settings):
        raise ValueError("resume state is not bound to the current runner/settings")
    if resume and state["stage"] == "complete_awaiting_work_review":
        completed_manifest = output / "gpu_ml_neb_path_manifest.candidate.json"
        if not completed_manifest.is_file():
            raise ValueError("completed resume state has no candidate manifest")
        return load_json_object(completed_manifest)
    images = _load_restart(output, image_count) if resume and state["stage"] != "initialized" else build_idpp_path(
        states, settings.images_per_segment
    )
    symbols = images[0].get_chemical_symbols()
    adsorbate_indices = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    for image in images:
        _attach_model_context(
            image,
            transition["indexed_bond_changes"],
            adsorbate_indices,
            is_spin_off=is_spin_off,
            is_low_fi=is_low_fi,
        )
    calculator = calculator_factory()

    ordinary_completed = int(state.get("stage_steps", 0)) if str(state["stage"]).startswith("ordinary_ml_neb") else 0
    current_stage = str(state["stage"])
    if current_stage.startswith("ml_ci_neb") or current_stage == "ordinary_ml_neb_complete":
        ordinary_converged = bool(state.get("ordinary_converged"))
        ordinary_steps = int(state.get("ordinary_steps", 0))
        ordinary_neb = NEB(
            images,
            k=settings.spring_constant_eV_per_A2,
            climb=False,
            method="improvedtangent",
            allow_shared_calculator=True,
        )
        for image in images:
            image.calc = calculator
    else:
        ordinary_neb, ordinary_converged, ordinary_steps = _optimizer_stage(
            images,
            calculator,
            output,
            state,
            stage="ordinary_ml_neb",
            climb=False,
            spring_constant=settings.spring_constant_eV_per_A2,
            fmax=settings.ordinary_fmax_eV_per_A,
            max_steps=settings.ordinary_max_steps,
            completed_steps=ordinary_completed,
            checkpoint_interval=settings.checkpoint_interval,
        )
        state.update({"ordinary_converged": ordinary_converged, "ordinary_steps": ordinary_steps})
        _write_restart(output, images, state)

    _ordinary_rows, ordinary_summary = _evaluate_path(
        images, ordinary_neb, transition["indexed_bond_changes"], output / "ordinary", settings
    )
    ready, readiness_reasons = _ci_readiness(
        ordinary_summary["energies_eV"],
        ordinary_summary["adjacent_rmsd_A"],
        ordinary_converged,
        settings.max_adjacent_rmsd_A,
    )
    run_ci = settings.ml_ci in {"auto", "on"} and ready
    ci_record: dict[str, Any] = {
        "requested": settings.ml_ci,
        "readiness_passed": ready,
        "readiness_reasons": readiness_reasons,
        "ran": run_ci,
    }
    final_neb = ordinary_neb
    final_stage = "ordinary_ml_neb"
    final_converged = ordinary_converged
    final_steps = ordinary_steps
    if run_ci and current_stage == "ml_ci_neb_complete":
        for image in images:
            image.calc = calculator
        final_neb = NEB(
            images,
            k=settings.spring_constant_eV_per_A2,
            climb=True,
            parallel=False,
            method="improvedtangent",
            allow_shared_calculator=True,
        )
        final_converged = bool(state.get("converged"))
        final_steps = int(state.get("stage_steps", 0))
        final_stage = "ml_ci_neb"
        ci_record.update({"converged": final_converged, "steps": final_steps})
    elif run_ci:
        ci_completed = int(state.get("stage_steps", 0)) if str(state["stage"]).startswith("ml_ci_neb") else 0
        final_neb, final_converged, final_steps = _optimizer_stage(
            images,
            calculator,
            output,
            state,
            stage="ml_ci_neb",
            climb=True,
            spring_constant=settings.spring_constant_eV_per_A2,
            fmax=settings.ci_fmax_eV_per_A,
            max_steps=settings.ci_max_steps,
            completed_steps=ci_completed,
            checkpoint_interval=settings.checkpoint_interval,
        )
        final_stage = "ml_ci_neb"
        ci_record.update({"converged": final_converged, "steps": final_steps})

    rows, summary = _evaluate_path(images, final_neb, transition["indexed_bond_changes"], output, settings)
    manifest = {
        "schema_version": 1,
        "document_kind": "gpu_ml_neb_path_manifest",
        "status": "needs_work_review",
        "result_class": "predicted_path_candidate_only",
        "source_handoff": {
            "path": Path(os.path.relpath(handoff_path.resolve(), output.resolve())).as_posix(),
            "sha256": sha256_file(handoff_path),
        },
        "checkpoint_sha256": sha256_file(checkpoint),
        "model_identifier": handoff["model"]["identifier"],
        "runner_sha256": sha256_file(Path(__file__)),
        "software": {"ase_version": ase.__version__, "numpy_version": np.__version__},
        "run_settings": asdict(settings),
        "contract_sha256": transition["normalized_reaction_contract_sha256"],
        "atom_map_sha256": transition["atom_map_sha256"],
        "compatibility_sha256": handoff["compatibility"]["sha256"],
        "optimizer": {
            "calculator_attachment": "one_shared_aqcat25_checkpoint_serially_attached_to_every_image",
            "ordinary_ml_neb": {"converged": ordinary_converged, "steps": ordinary_steps},
            "ml_ci_neb": ci_record,
            "final_stage": final_stage,
            "final_converged": final_converged,
            "final_steps": final_steps,
        },
        "domain_assessment": {
            "status": "uncalibrated",
            "model_disagreement_available": False,
            "reason": "single_checkpoint_requires_local_vasp_triad_or_calibrated_ts_domain",
        },
        "images": rows,
        "adjacent_rmsd_A": summary["adjacent_rmsd_A"],
        "path_review": {
            "geometry_continuity": "needs_review",
            "periodic_mapping": "needs_review",
            "reaction_coordinate_resolution": "needs_review",
            "elementary_step_assignment": "needs_review",
            "numeric_screen": summary["numeric_screen"],
        },
        "vasp_label_candidates": _label_candidates(rows, summary["adjacent_rmsd_A"]),
        "restrictions": {
            "predicted_candidate_only": True,
            "reportable_dft": False,
            "automatic_vasp_submission": False,
            "dimer_parent_accepted": False,
        },
    }
    manifest_path = output / "gpu_ml_neb_path_manifest.candidate.json"
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


def seal_successful_run(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_path = output / "gpu_ml_neb_path_manifest.candidate.json"
    if not manifest_path.is_file() or load_json_object(manifest_path) != manifest:
        raise ValueError("cannot seal a changed or missing ML-NEB candidate manifest")
    finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    exit_record = {
        "gpu_job_id": str(os.environ.get("SLURM_JOB_ID", "local_test")),
        "hostname": socket.gethostname(),
        "finished_utc": finished,
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
            "evidence_class": "producer_process_only_not_scheduler_accounting",
        },
    }
    write_json_atomic(manifest_path, sealed, ensure_ascii=True)
    internal_peak = max(sealed["images"][1:-1], key=lambda row: row["predicted_energy_eV"])["image"]
    review_draft_path = output / "gpu_ml_neb_path_review.draft.json"
    if not review_draft_path.exists():
        write_json_atomic(
            review_draft_path,
            {
                "document_kind": "gpu_ml_neb_path_review",
                "status": "needs_review",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "geometry_continuity": "needs_review",
                "periodic_mapping": "needs_review",
                "reaction_coordinate_resolution": "needs_review",
                "elementary_step_assignment": "needs_review",
                "candidate_peak_image": internal_peak,
                "numeric_screen": sealed["path_review"]["numeric_screen"],
                "reviewer": None,
                "reviewed_at": None,
            },
            ensure_ascii=True,
        )
    state_path = output / "ml_neb_state.json"
    state = load_json_object(state_path)
    state["candidate_manifest_sha256"] = sha256_file(manifest_path)
    state["producer_exit_record_sha256"] = sha256_file(exit_path)
    state["path_review_draft_sha256"] = sha256_file(review_draft_path)
    write_json_atomic(state_path, state, ensure_ascii=True)
    return sealed


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--images-per-segment", type=int, default=5)
    parser.add_argument("--spring-constant", type=float, default=0.10)
    parser.add_argument("--ordinary-fmax", type=float, default=0.10)
    parser.add_argument("--ordinary-steps", type=int, default=300)
    parser.add_argument("--ml-ci", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--ci-fmax", type=float, default=0.05)
    parser.add_argument("--ci-steps", type=int, default=200)
    parser.add_argument("--max-adjacent-rmsd", type=float, default=0.75)
    parser.add_argument("--minimum-pair-distance", type=float, default=0.65)
    parser.add_argument("--checkpoint-interval", type=int, default=5)
    parser.add_argument("--is-spin-off", action="store_true")
    parser.add_argument("--is-low-fi", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    settings = RunSettings(
        images_per_segment=args.images_per_segment,
        spring_constant_eV_per_A2=args.spring_constant,
        ordinary_fmax_eV_per_A=args.ordinary_fmax,
        ordinary_max_steps=args.ordinary_steps,
        ml_ci=args.ml_ci,
        ci_fmax_eV_per_A=args.ci_fmax,
        ci_max_steps=args.ci_steps,
        max_adjacent_rmsd_A=args.max_adjacent_rmsd,
        minimum_pair_distance_A=args.minimum_pair_distance,
        checkpoint_interval=args.checkpoint_interval,
    )
    manifest = run_from_handoff(
        args.handoff,
        args.checkpoint,
        args.output,
        schema_path=args.schema,
        settings=settings,
        calculator_factory=lambda: _build_aqcat_calculator(
            args.checkpoint, args.is_spin_off, args.is_low_fi
        ),
        is_spin_off=args.is_spin_off,
        is_low_fi=args.is_low_fi,
        resume=args.resume,
    )
    if "producer_exit_record" not in manifest:
        manifest = seal_successful_run(args.output, manifest)
    print(json.dumps({"status": manifest["status"], "images": len(manifest["images"])}, ensure_ascii=True))


if __name__ == "__main__":
    main()
