from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.neb_agent.magnetic_continuity import evaluate_magnetic_continuity
from scripts.neb_agent.path_quality_service import (
    PathQualityRequest,
    build_path_quality_report,
)
from scripts.neb_agent.utils_structure import numbered_image_dirs
from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.scheduler_evidence import (
    query_lsf_job,
    verify_lsf_evidence_live,
)
from scripts.vasp_result_gate import final_scf_status, incar_value, read_incar_values

THRESHOLDS = Path(__file__).parents[2] / "configs" / "neb_agent" / "default_thresholds.yaml"
SHARED_INPUTS = ("KPOINTS", "POTCAR.spec", "script.lsf")


def build_pilot_path_quality_result(request: PathQualityRequest) -> dict[str, Any]:
    """Build shared path-quality evidence without changing pilot acceptance."""

    return build_path_quality_report(request)


def _image_result(pilot_dir: Path, image: Path) -> dict[str, Any]:
    files = {name: image / name for name in ("POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")}
    missing = [name for name, path in files.items() if not path.is_file() or not path.stat().st_size]
    if missing:
        return {"image": image.name, "passed": False, "errors": [f"missing:{name}" for name in missing]}
    outcar = parse_outcar(files["OUTCAR"])
    oszicar = parse_oszicar(files["OSZICAR"])
    scf = final_scf_status(files["OSZICAR"], pilot_dir / "INCAR", files["OUTCAR"])
    errors = []
    if not outcar.get("normal_completion"):
        errors.append("normal_completion_missing")
    if outcar.get("fatal_keywords"):
        errors.append("fatal_keywords=" + ",".join(outcar["fatal_keywords"]))
    if not scf["electronically_converged"]:
        errors.append("electronic_convergence_failed")
    if oszicar["ionic_steps"] != 1:
        errors.append(f"expected_one_ionic_step_got_{oszicar['ionic_steps']}")
    magnetization = outcar.get("total_magnetization_history_muB") or []
    if not magnetization:
        errors.append("total_magnetization_missing")
    return {
        "image": image.name,
        "passed": not errors,
        "errors": errors,
        "ionic_steps": oszicar["ionic_steps"],
        "final_total_magnetization_muB": magnetization[-1] if magnetization else None,
        **scf,
        "files": {name: sha256_file(path) for name, path in files.items()},
    }


def _collect_images(pilot_dir: Path) -> list[dict[str, Any]]:
    count = int(float(incar_value(pilot_dir / "INCAR", "IMAGES")))
    images = numbered_image_dirs(pilot_dir)
    if [path.name for path in images] != [f"{index:02d}" for index in range(count + 2)]:
        raise ValueError("pilot image sequence does not match INCAR IMAGES")
    return [_image_result(pilot_dir, image) for image in images[1:-1]]


def _input_compatibility_hash(directory: Path, *, expected_nsw: int | None) -> str:
    incar = read_incar_values(directory / "INCAR")
    nsw = int(float(incar.pop("NSW")))
    if expected_nsw is not None and nsw != expected_nsw:
        raise ValueError(f"expected NSW={expected_nsw}, got {nsw}")
    files = {name: sha256_file(directory / name) for name in SHARED_INPUTS}
    return sha256_json({"incar_without_nsw": incar, "files": files})


def _path_input_hash(directory: Path) -> str:
    images = numbered_image_dirs(directory)
    files = {
        image.name: sha256_file(image / "POSCAR")
        for image in images
    }
    files["path_generation_report.json"] = sha256_file(
        directory / "path_generation_report.json"
    )
    return sha256_json(files)


def build_pilot_result(pilot_dir: Path, production_dir: Path, job_id: str) -> dict[str, Any]:
    scheduler = query_lsf_job(job_id, stage="neb_pilot")
    if scheduler["status"] != "DONE":
        raise ValueError(f"NEB pilot job {job_id} is not DONE")
    scheduler_path = write_json(pilot_dir / "scheduler_evidence.json", scheduler)
    images = _collect_images(pilot_dir)
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    magnetic_continuity = evaluate_magnetic_continuity(
        images,
        float(thresholds["magnetic_continuity_warning_threshold_muB"]),
    )
    path_hash = sha256_file(pilot_dir / "path_generation_report.json")
    if path_hash != sha256_file(production_dir / "path_generation_report.json"):
        raise ValueError("pilot and production path-generation reports differ")
    for image in images:
        production_poscar = production_dir / image["image"] / "POSCAR"
        if image.get("files", {}).get("POSCAR") != sha256_file(production_poscar):
            raise ValueError(f"pilot/production POSCAR mismatch for image {image['image']}")
    path_input_hash = _path_input_hash(pilot_dir)
    if path_input_hash != _path_input_hash(production_dir):
        raise ValueError("pilot and production path inputs differ")
    input_hash = _input_compatibility_hash(pilot_dir, expected_nsw=1)
    if input_hash != _input_compatibility_hash(production_dir, expected_nsw=None):
        raise ValueError("pilot and production electronic inputs differ")
    payload = {
        "schema_version": 2,
        "document_kind": "neb_pilot_result",
        "passed": all(image["passed"] for image in images),
        "scheduler_status": scheduler["status"],
        "job_id": str(job_id),
        "images": len(images),
        "path_generation_sha256": path_hash,
        "path_input_sha256": path_input_hash,
        "input_compatibility_sha256": input_hash,
        "source_directory": os.path.relpath(pilot_dir, production_dir),
        "scheduler_evidence_sha256": sha256_file(scheduler_path),
        "thresholds_sha256": sha256_file(THRESHOLDS),
        "magnetic_continuity": magnetic_continuity,
        "image_results": images,
    }
    write_json(production_dir / "neb_pilot_result.json", payload)
    return payload


def validate_pilot_result(result_path: Path, production_dir: Path) -> dict[str, Any]:
    payload = load_json_object(result_path)
    required = {
        "schema_version", "document_kind", "passed", "scheduler_status", "job_id",
        "images", "path_generation_sha256", "source_directory",
        "path_input_sha256", "input_compatibility_sha256",
        "scheduler_evidence_sha256", "thresholds_sha256",
        "magnetic_continuity", "image_results",
    }
    if (
        set(payload) != required
        or payload["schema_version"] != 2
        or payload["document_kind"] != "neb_pilot_result"
    ):
        raise ValueError("invalid NEB pilot result document")
    pilot_dir = (production_dir / payload["source_directory"]).resolve()
    if pilot_dir.parent != production_dir.resolve().parent:
        raise ValueError("NEB pilot evidence must be a sibling calculation directory")
    scheduler_path = pilot_dir / "scheduler_evidence.json"
    if sha256_file(scheduler_path) != payload["scheduler_evidence_sha256"]:
        raise ValueError("NEB pilot scheduler-evidence hash mismatch")
    verify_lsf_evidence_live(load_json_object(scheduler_path), required_status="DONE")
    images = _collect_images(pilot_dir)
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    magnetic_continuity = evaluate_magnetic_continuity(
        images,
        float(thresholds["magnetic_continuity_warning_threshold_muB"]),
    )
    valid = (
        payload["passed"] is True
        and payload["scheduler_status"] == "DONE"
        and payload["images"] == len(images)
        and payload["image_results"] == images
        and payload["thresholds_sha256"] == sha256_file(THRESHOLDS)
        and payload["magnetic_continuity"] == magnetic_continuity
        and payload["path_generation_sha256"]
        == sha256_file(production_dir / "path_generation_report.json")
        and payload["path_input_sha256"] == _path_input_hash(pilot_dir)
        and payload["path_input_sha256"] == _path_input_hash(production_dir)
        and payload["input_compatibility_sha256"]
        == _input_compatibility_hash(pilot_dir, expected_nsw=1)
        and payload["input_compatibility_sha256"]
        == _input_compatibility_hash(production_dir, expected_nsw=None)
    )
    for image in images:
        valid = valid and image["files"]["POSCAR"] == sha256_file(
            production_dir / image["image"] / "POSCAR"
        )
    if not valid:
        raise ValueError("NEB pilot result does not match current scheduler/files/path")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hash-bound evidence for a completed NEB pilot.")
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--production-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    result = build_pilot_result(args.pilot_dir, args.production_dir, args.job_id)
    print("PASS" if result["passed"] else "STOP")


if __name__ == "__main__":
    main()
