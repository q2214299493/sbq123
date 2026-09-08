from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from scripts.artifact_io import source_file_manifest

from .cli_common import add_common_arguments
from .magnetic_continuity import evaluate_magnetic_continuity
from .utils_report import write_json
from .utils_structure import numbered_image_dirs
from .utils_vasp import (
    classify_force_trend,
    parse_oszicar,
    parse_outcar,
    trailing_threshold_count,
)


ROOT = Path(__file__).resolve().parents[2]


def _incar_integer(path: Path, key: str) -> int | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].strip()
        if "=" not in clean:
            continue
        name, value = (part.strip() for part in clean.split("=", 1))
        if name.upper() == key.upper():
            try:
                return int(float(value.split()[0]))
            except ValueError:
                return None
    return None


def _incar_float(path: Path, key: str) -> float | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].strip()
        if "=" not in clean:
            continue
        name, value = (part.strip() for part in clean.split("=", 1))
        if name.upper() == key.upper():
            try:
                return float(value.split()[0])
            except ValueError:
                return None
    return None


def _incar_logical(path: Path, key: str) -> bool | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].strip()
        if "=" not in clean:
            continue
        name, value = (part.strip() for part in clean.split("=", 1))
        if name.upper() == key.upper():
            token = value.split()[0].strip(".").upper()
            if token in {"TRUE", "T"}:
                return True
            if token in {"FALSE", "F"}:
                return False
    return None


def classify_high_force_observations(
    rows: list[dict],
    thresholds: dict,
) -> list[dict]:
    """Classify high forces without treating early samples as failures."""

    minimum_warning_steps = int(thresholds["min_ionic_steps_for_force_warning"])
    minimum_failure_steps = int(
        thresholds["persistent_high_force_failure_min_ionic_steps"]
    )
    threshold = float(thresholds["high_force_warning_threshold_eVA"])
    observations = []
    for row in rows:
        force = row.get("final_neb_force_eVA")
        if force is None or force <= threshold:
            continue
        ionic_steps = int(row.get("ionic_steps") or 0)
        trend = row.get("neb_force_trend")
        warning_eligible = ionic_steps >= minimum_warning_steps
        warning_triggered = warning_eligible and trend != "decreasing"
        failure_eligible = ionic_steps >= minimum_failure_steps
        failure_triggered = failure_eligible and trend != "decreasing"
        observations.append(
            {
                "image": row["image"],
                "ionic_steps": ionic_steps,
                "force_eVA": force,
                "trend": trend,
                "warning_eligible": warning_eligible,
                "warning_triggered": warning_triggered,
                "failure_eligible": failure_eligible,
                "failure_triggered": failure_triggered,
                "classification": (
                    "persistent_high_force_failure"
                    if failure_triggered
                    else "high_force_warning"
                    if warning_triggered
                    else "decreasing_high_force_no_warning"
                    if warning_eligible
                    else "initial_high_force_allowed"
                ),
            }
        )
    return observations


def analyze(workdir: Path, thresholds_path: Path, reaction_indices: list[int] | None = None) -> dict:
    thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    nelm = _incar_integer(workdir / "INCAR", "NELM")
    nsw = _incar_integer(workdir / "INCAR", "NSW")
    images = _incar_integer(workdir / "INCAR", "IMAGES")
    ediffg = _incar_float(workdir / "INCAR", "EDIFFG")
    climb = _incar_logical(workdir / "INCAR", "LCLIMB")
    dirs = numbered_image_dirs(workdir)
    rows: list[dict] = []
    for directory in dirs:
        oszicar = parse_oszicar(directory / "OSZICAR")
        outcar = parse_outcar(directory / "OUTCAR")
        energies = outcar.get("sigma0_energies") or oszicar.get("energies") or []
        neb_forces = outcar.get("neb_force_history") or []
        atomic_forces = outcar.get("atomic_force_history") or []
        total_magnetization = outcar.get("total_magnetization_history_muB") or []
        local_magnetization = outcar.get("local_magnetization_last_muB") or []
        rows.append(
            {
                "image": directory.name,
                "ionic_steps": max(oszicar.get("ionic_steps", 0), len(neb_forces), len(atomic_forces)),
                "final_energy_eV": energies[-1] if energies else None,
                "final_neb_force_eVA": neb_forces[-1] if neb_forces else None,
                "final_atomic_force_eVA": atomic_forces[-1] if atomic_forces else None,
                "energy_history_last10_eV": energies[-10:],
                "neb_force_history_last10_eVA": neb_forces[-10:],
                "atomic_force_history_last10_eVA": atomic_forces[-10:],
                "neb_force_trend": classify_force_trend(neb_forces),
                "atomic_force_trend": classify_force_trend(atomic_forces),
                "scf_iterations_last_ionic_step": (oszicar.get("scf_iterations") or [None])[-1],
                "scf_iterations_last10": (oszicar.get("scf_iterations") or [])[-10:],
                "reached_required_accuracy": outcar.get("reached_required_accuracy", False),
                "electronically_converged": outcar.get("electronic_convergence_reached", False),
                "normal_completion": outcar.get("normal_completion", False),
                "final_total_magnetization_muB": total_magnetization[-1] if total_magnetization else None,
                "reaction_atom_local_magnetization_muB": {
                    str(index): local_magnetization[index]
                    for index in reaction_indices or []
                    if index < len(local_magnetization)
                },
                "fatal_keywords": outcar.get("fatal_keywords", []),
                "has_output": bool(oszicar.get("exists") or outcar.get("exists")),
            }
        )
    baseline = rows[0]["final_energy_eV"] if rows else None
    for row in rows:
        row["relative_energy_eV"] = (
            row["final_energy_eV"] - baseline if baseline is not None and row["final_energy_eV"] is not None else None
        )
    complete_energy = len(rows) >= 2 and all(row["final_energy_eV"] is not None for row in rows)
    maximum_image = None
    internal_maximum = False
    internal_minima: list[str] = []
    monotonic = False
    if complete_energy:
        maximum_image = max(rows, key=lambda row: row["final_energy_eV"])["image"]
        internal_maximum = maximum_image not in {rows[0]["image"], rows[-1]["image"]}
        tolerance = float(thresholds["internal_minimum_warning_eV"])
        internal_minima = [
            rows[index]["image"]
            for index in range(1, len(rows) - 1)
            if rows[index]["final_energy_eV"] < min(rows[index - 1]["final_energy_eV"], rows[index + 1]["final_energy_eV"]) - tolerance
        ]
        differences = [rows[i + 1]["final_energy_eV"] - rows[i]["final_energy_eV"] for i in range(len(rows) - 1)]
        monotonic = all(value >= 0 for value in differences) or all(value <= 0 for value in differences)
    fatal = sorted({keyword for row in rows for keyword in row["fatal_keywords"]})
    scf_exhausted = [
        row["image"]
        for row in rows
        if nelm and any(value >= nelm for value in row["scf_iterations_last10"])
    ]
    scf_persistent = [
        row["image"]
        for row in rows
        if trailing_threshold_count(row["scf_iterations_last10"], nelm)
        >= int(thresholds["scf_consecutive_exhaustion_hard_min"])
    ]
    nsw_exhausted = [row["image"] for row in rows[1:-1] if nsw and row["ionic_steps"] >= nsw and not row["reached_required_accuracy"]]
    expected_names = [f"{index:02d}" for index in range(images + 2)] if images is not None else []
    image_sequence_complete = bool(expected_names and [directory.name for directory in dirs] == expected_names)
    force_target = abs(ediffg) if ediffg is not None and ediffg < 0 else None
    internal_rows = rows[1:-1]
    technically_converged = bool(
        image_sequence_complete
        and internal_rows
        and force_target is not None
        and all(
            row["normal_completion"]
            and row["reached_required_accuracy"]
            and row["final_neb_force_eVA"] is not None
            and row["final_neb_force_eVA"] <= force_target
            for row in internal_rows
        )
    )
    magnetic_continuity = evaluate_magnetic_continuity(
        rows,
        float(thresholds["magnetic_continuity_warning_threshold_muB"]),
    )
    high_force_observations = classify_high_force_observations(internal_rows, thresholds)
    high_force_warnings = [
        {
            "image": row["image"],
            "ionic_steps": row["ionic_steps"],
            "force_eVA": row["force_eVA"],
            "trend": row["trend"],
        }
        for row in high_force_observations
        if row["warning_triggered"]
    ]
    persistent_high_force_failure_images = [
        row["image"] for row in high_force_observations if row["failure_triggered"]
    ]
    barrierless_candidate = bool(
        complete_energy
        and not internal_maximum
        and internal_rows
        and all(
            row["final_neb_force_eVA"] is not None
            and row["final_neb_force_eVA"] <= float(thresholds["barrierless_force_threshold_eVA"])
            for row in internal_rows
        )
    )
    payload = {
        "schema_version": 1,
        "document_kind": "neb_output_analysis",
        "producer": "scripts.neb_agent.analyze_neb_outputs",
        "source_files": source_file_manifest(
            [
                workdir / "INCAR",
                thresholds_path,
                *[
                    path
                    for directory in dirs
                    for path in (directory / "OSZICAR", directory / "OUTCAR")
                ],
            ]
        ),
        "status": "NO_OUTPUT" if not any(row["has_output"] for row in rows) else "ANALYZED",
        "images": rows,
        "complete_energy_profile": complete_energy,
        "maximum_image": maximum_image,
        "internal_maximum": internal_maximum,
        "internal_minimum_warning": bool(internal_minima),
        "internal_minimum_images": internal_minima,
        "monotonic_energy_profile": monotonic,
        "fatal_keywords": fatal,
        "configured_nelm": nelm,
        "configured_nsw": nsw,
        "configured_images": images,
        "configured_ediffg_eVA": ediffg,
        "parent_neb_method": (
            "ci_neb" if climb is True else "ordinary_neb" if climb is False else "needs_confirmation"
        ),
        "image_sequence_complete": image_sequence_complete,
        "scf_exhausted_images": scf_exhausted,
        "scf_persistent_failure_images": scf_persistent,
        "scf_warning": bool(scf_exhausted),
        "scf_failure": bool(fatal or scf_persistent),
        "force_warning_policy": {
            "threshold_eVA": float(thresholds["high_force_warning_threshold_eVA"]),
            "startup_window_ionic_steps": int(
                thresholds["min_ionic_steps_for_force_warning"]
            ),
            "persistent_failure_minimum_ionic_steps": int(
                thresholds["persistent_high_force_failure_min_ionic_steps"]
            ),
            "requires_non_decreasing_trend": True,
            "early_high_force_is_failure": False,
            "warning_is_hard_failure": False,
            "high_force_with_independent_geometry_periodic_or_magnetic_anomaly_is_failure": True,
        },
        "high_force_observations": high_force_observations,
        "high_force_warnings": high_force_warnings,
        "persistent_high_force_failure_images": persistent_high_force_failure_images,
        "nsw_stopped_without_convergence_images": nsw_exhausted,
        "technically_converged": technically_converged,
        "geometry_validated": False,
        "path_reviewed": False,
        "scientifically_valid": False,
        "magnetic_continuity": magnetic_continuity,
        "barrierless_candidate": barrierless_candidate,
        "energy_profile_status": "interim_neb_only_not_reportable_barrier",
    }
    write_json(workdir / "neb_analysis.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze NEB energies, forces, SCF behavior, and image-level convergence.")
    add_common_arguments(parser)
    parser.add_argument("--thresholds", type=Path, default=ROOT / "configs" / "neb_agent" / "default_thresholds.yaml")
    args = parser.parse_args()
    payload = analyze(args.workdir, args.thresholds)
    print(payload["status"])


if __name__ == "__main__":
    main()
