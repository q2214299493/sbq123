"""Run one reviewed local peak from a saved rough ML path, without rerunning NEB."""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import socket
import time
from pathlib import Path

import numpy as np
from ase.constraints import FixAtoms

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.aqcat25_ml_neb import _attach_model_context, _strict_internal_peaks
from scripts.dual_model_ml_neb import _geometry_guard_evidence, _load_request, _verify_checkpoint
from scripts.execution_backends import require_gpu_write_path
from scripts.ml_candidate_source import load_candidate_path
from scripts.ml_sella_candidate import BudgetCalculator, refine_peak, require_sella, validate_settings
from scripts.mlip_same_structure_benchmark import _load_calculator
from scripts.prepare_dual_model_ts_active_learning_round import _safe_snapshot_file


def _bound_file(root, ref):
    path = (root / ref["path"]).resolve()
    if not path.is_file() or sha256_file(path) != ref["sha256"]:
        raise ValueError("local-peak source evidence changed or missing")
    return path


def _validate_scope(entry, review, manifest):
    if (review.get("document_kind") != "sella_local_peak_work_review"
            or review.get("decision") != "accepted_for_bounded_local_search"
            or review.get("single_event_review_passed") is not True
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or not isinstance(review.get("reaction_event"), str) or not review["reaction_event"].strip()):
        raise ValueError("a work review of one reaction event is required")
    for key in ("segment", "settings", "limits"):
        if review.get(key) != entry[key]:
            raise ValueError(f"local-peak review does not bind {key}")
    for key in ("source_request", "parent_manifest"):
        if review.get(f"{key}_sha256") != entry[key]["sha256"]:
            raise ValueError("local-peak review source binding mismatch")
    segment = entry["segment"]
    if not isinstance(segment, dict) or set(segment) != {"start_image", "peak_image", "end_image"}:
        raise ValueError("one explicit local segment is required")
    start, peak, end = (segment[key] for key in ("start_image", "peak_image", "end_image"))
    if (any(type(value) is not int for value in (start, peak, end))
            or not 0 <= start < peak < end < len(manifest["images"])):
        raise ValueError("seed must be an internal image of the reviewed segment")
    energies = [row["predicted_energy_eV"] for row in manifest["images"]]
    if any(type(value) not in (int, float) or not np.isfinite(value) for value in energies):
        raise ValueError("finite primary-model path energies are required")
    local_peaks = [start + index for index in _strict_internal_peaks(energies[start:end + 1])]
    if local_peaks != [peak]:
        raise ValueError("review each local peak separately; segment must contain one strict peak")


def _validate_limits(entry):
    validate_settings(entry["settings"])
    limits = entry["limits"]
    if not isinstance(limits, dict) or set(limits) != {
        "maximum_evaluations", "maximum_wall_seconds", "maximum_displacement_A"
    }:
        raise ValueError("explicit evaluation, wall-time and displacement limits are required")
    for key in ("maximum_evaluations", "maximum_wall_seconds"):
        if type(limits[key]) is not int or limits[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    value = limits["maximum_displacement_A"]
    if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
        raise ValueError("maximum_displacement_A must be finite and positive")


def validate_request(path):
    """Read-only preflight: no imports of Sella/torch or calculator calls."""
    entry = load_json_object(path)
    required = {"schema_version", "document_kind", "execution_authorized", "source_request", "parent_manifest",
                "review", "segment", "settings", "limits"}
    if (set(entry) != required or entry.get("schema_version") != 1
            or entry.get("document_kind") != "matris_sella_local_peak_request"
            or type(entry.get("execution_authorized")) is not bool):
        raise ValueError("invalid local-peak request")
    _validate_limits(entry)
    paths = {name: _bound_file(path.parent, entry[name]) for name in ("source_request", "parent_manifest", "review")}
    request = _load_request(paths["source_request"])
    manifest = load_json_object(paths["parent_manifest"])
    if (manifest.get("document_kind") != "dual_model_gpu_ml_neb_path_manifest"
            or manifest.get("result_class") != "predicted_path_candidate_only"
            or manifest.get("geometry_guards", {}).get("passed") is not True
            or manifest.get("source_request", {}).get("sha256") != entry["source_request"]["sha256"]
            or manifest.get("models") != request["models"] or manifest.get("reaction") != request["reaction"]):
        raise ValueError("parent path model/reaction/source binding mismatch")
    review = load_json_object(paths["review"])
    _validate_scope(entry, review, manifest)
    atoms, rows = load_candidate_path(request, manifest, paths["parent_manifest"], paths["source_request"],
                                      method="ml_neb_sella", minimum_images=3)
    if any(not isinstance(item, FixAtoms) for image in atoms for item in image.constraints):
        raise ValueError("local Sella requires full-atom Selective Dynamics")
    if len(request["fixed_atom_indices_zero_based"]) == len(atoms[0]):
        raise ValueError("local Sella needs movable atoms")
    return entry, paths, request, manifest, atoms, rows


def prepare_request(source_request, parent_manifest, review_path, destination):
    """Package an existing work review without granting execution authority."""
    if destination.exists():
        raise FileExistsError(f"request already exists: {destination}")
    review = load_json_object(review_path)
    entry = {"schema_version": 1, "document_kind": "matris_sella_local_peak_request", "execution_authorized": False,
             **{key: review[key] for key in ("segment", "settings", "limits")}}
    for key, path in (("source_request", source_request), ("parent_manifest", parent_manifest), ("review", review_path)):
        entry[key] = {"path": str(path.resolve()), "sha256": sha256_file(path)}
    # Validate the exact scope before writing the prepared request.
    manifest = load_json_object(parent_manifest)
    _validate_limits(entry)
    _validate_scope(entry, review, manifest)
    request = _load_request(source_request)
    if (manifest.get("source_request", {}).get("sha256") != sha256_file(source_request)
            or manifest.get("models") != request["models"] or manifest.get("reaction") != request["reaction"]):
        raise ValueError("parent path model/reaction/source binding mismatch")
    load_candidate_path(request, manifest, parent_manifest, source_request, method="ml_neb_sella", minimum_images=3)
    # A movable input bundle preserves every reviewed JSON/structure byte. Large
    # checkpoints stay outside it and are checked independently at execution.
    bundle = destination.parent / f"{destination.stem}_inputs"
    if bundle.exists():
        raise FileExistsError(f"input bundle already exists: {bundle}")
    source_files = [(source_request, Path("source/request.json")), (parent_manifest, Path("parent/manifest.json")),
                    (review_path, Path("review.json"))]
    for row in request["images"]:
        source_files.append((_safe_snapshot_file(source_request.parent, row["path"]), Path("source") / row["path"]))
    for row in manifest["images"]:
        source_files.append((_safe_snapshot_file(parent_manifest.parent, row["structure_path"]),
                             Path("parent") / row["structure_path"]))
    bundle.mkdir(parents=True, exist_ok=False)
    for original, relative in source_files:
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        if sha256_file(original) != sha256_file(target):
            raise ValueError("source changed during input packaging")
    for key, relative in (("source_request", "source/request.json"), ("parent_manifest", "parent/manifest.json"),
                          ("review", "review.json")):
        entry[key]["path"] = (Path(bundle.name) / relative).as_posix()
    write_json_atomic(destination, entry)
    return entry


def candidate_geometry(candidate, images, request, segment, limits):
    peak = segment["peak_image"]
    seed = images[peak]
    fixed = request["fixed_atom_indices_zero_based"]
    identity = (np.array_equal(candidate.numbers, seed.numbers) and np.array_equal(candidate.pbc, seed.pbc)
                and np.allclose(candidate.cell, seed.cell, rtol=0, atol=1e-10)
                and np.allclose(candidate.positions[fixed], seed.positions[fixed], rtol=0, atol=1e-8))
    if not identity or not np.isfinite(candidate.positions).all():
        return {"passed": False, "reason": "identity_or_finite_geometry"}
    displacement = float(np.linalg.norm(candidate.positions - seed.positions, axis=1).max())
    trial = list(images)
    trial[peak] = candidate
    geometry = _geometry_guard_evidence(trial, request)
    return {"passed": geometry["passed"] and displacement <= limits["maximum_displacement_A"],
            "maximum_displacement_A": displacement, "parent_path_geometry": geometry,
            "reviewed_segment": segment, "single_event_identity": "work_review_required"}


def run(request_path, checkpoint, output, *, device="cuda", calculator_loader=_load_calculator):
    entry, paths, request, parent, images, rows = validate_request(request_path)
    request_sha256 = sha256_file(request_path)
    if entry["execution_authorized"] is not True:
        raise ValueError("explicit bounded local-search execution authorization is required")
    _verify_checkpoint(checkpoint, request["models"]["primary"]["checkpoint_sha256"], "primary")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    require_sella()
    segment, limits = entry["segment"], entry["limits"]
    peak = segment["peak_image"]
    seed = images[peak].copy()
    _attach_model_context(seed, request["reaction"]["indexed_bond_changes"],
                          [i for i, symbol in enumerate(seed.get_chemical_symbols()) if symbol != "Fe"],
                          is_spin_off=False, is_low_fi=False)

    def geometry_check(atoms):
        return candidate_geometry(atoms, images, request, segment, limits)

    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    receipt = {"document_kind": "matris_sella_local_peak_run", "status": "running",
               "request_sha256": request_sha256, "segment": segment,
               "runner_sha256": sha256_file(Path(__file__)), "model_error_assumed": False,
               "automatic_submission": False, "scientifically_validated_ts": False}
    write_json_atomic(output / "run_record.json", receipt)
    try:
        calculator = BudgetCalculator(calculator_loader("matris", checkpoint, device),
                                      limits["maximum_evaluations"], limits["maximum_wall_seconds"],
                                      geometry_check=geometry_check)
        calculator.started = started  # Include model loading in the cooperative wall budget.
        source = {"source_request_sha256": entry["source_request"]["sha256"],
                  "checkpoint_sha256": request["models"]["primary"]["checkpoint_sha256"],
                  "peak_image": f"{peak:02d}", "seed_structure_sha256": parent["images"][peak]["structure_sha256"],
                  "entry_mode": "reviewed_rough_local_peak", "local_peak_request_sha256": request_sha256,
                  "parent_manifest_sha256": entry["parent_manifest"]["sha256"], "segment": segment}
        result = refine_peak(seed, calculator, entry["settings"], output / "sella",
                             source=source, geometry_check=geometry_check)
        if sha256_file(request_path) != request_sha256:
            raise ValueError("local-search request changed during execution")
        validate_request(request_path)
        _verify_checkpoint(checkpoint, request["models"]["primary"]["checkpoint_sha256"], "primary")
        manifest = _export_candidate(output, parent, rows, result, paths, request_path)
        receipt.update(status=result["status"], model_evaluations=calculator.evaluations,
                       elapsed_seconds=time.monotonic() - started)
        write_json_atomic(output / "run_record.json", receipt)
        return manifest
    except Exception as exc:
        receipt.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)},
                       elapsed_seconds=time.monotonic() - started)
        write_json_atomic(output / "run_record.json", receipt)
        raise


def _export_candidate(output, parent, rows, result, paths, request_path):
    """Keep the complete, unchanged parent path for existing VASP-label consumers."""
    manifest = copy.deepcopy(parent)
    for key in ("producer", "producer_exit_record"):
        manifest.pop(key, None)  # An earlier NEB process did not execute this search.
    (output / "structures").mkdir()
    for row, image in zip(rows, manifest["images"], strict=True):
        destination = output / row["path"]
        shutil.copy2(row["source_path"], destination)
        if sha256_file(destination) != row["sha256"]:
            raise ValueError("parent structure changed while copying")
        image["structure_path"] = row["path"]
    manifest["source_request"]["path"] = os.path.relpath(paths["source_request"], output)
    manifest["local_peak_entry"] = {"path": os.path.relpath(request_path, output), "sha256": sha256_file(request_path)}
    manifest["sella_refinement"] = {"status": result["status"], "path": "sella/candidate_manifest.json",
                                    "sha256": sha256_file(output / "sella/candidate_manifest.json"),
                                    "scientifically_validated_ts": False}
    manifest["status"] = "needs_work_review"
    # Parent optimizer/convergence/energy fields describe only the unchanged parent.
    write_json_atomic(output / "dual_model_gpu_ml_neb_path_manifest.candidate.json", manifest)
    return manifest


def validate_candidate_entry(manifest, manifest_path, sella):
    """Recheck the reviewed early entry when handing a candidate back to work."""
    entry_path = _bound_file(manifest_path.parent, manifest["local_peak_entry"])
    entry, _, request, parent, images, _ = validate_request(entry_path)
    source = sella["source"]
    if (source.get("entry_mode") != "reviewed_rough_local_peak"
            or entry["execution_authorized"] is not True
            or source.get("local_peak_request_sha256") != sha256_file(entry_path)
            or source.get("parent_manifest_sha256") != entry["parent_manifest"]["sha256"]
            or source.get("segment") != entry["segment"]
            or source.get("peak_image") != f"{entry['segment']['peak_image']:02d}"
            or sella.get("settings") != entry["settings"]
            or manifest["models"] != request["models"]
            or manifest["optimizer"] != parent["optimizer"]
            or [row["predicted_energy_eV"] for row in manifest["images"]]
            != [row["predicted_energy_eV"] for row in parent["images"]]):
        raise ValueError("early Sella candidate does not match reviewed segment/source/settings")
    if ([row["structure_sha256"] for row in manifest["images"]]
            != [row["structure_sha256"] for row in parent["images"]]):
        raise ValueError("early Sella parent path changed")
    return entry, images, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--source-request", type=Path)
    parser.add_argument("--parent-manifest", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if args.source_request is None or args.parent_manifest is None or args.review is None:
            parser.error("--prepare requires --source-request, --parent-manifest and --review")
        prepare_request(args.source_request, args.parent_manifest, args.review, args.request)
        print(json.dumps({"status": "prepared_not_authorized", "jobs_submitted": 0}))
        return
    if args.preflight:
        entry, *_ = validate_request(args.request)
        print(json.dumps({"status": "preflight_passed", "segment": entry["segment"], "jobs_submitted": 0}))
        return
    if args.checkpoint is None or args.output is None:
        parser.error("execution requires --checkpoint and --output")
    if socket.gethostname() != "MZ73" or not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("production execution requires an allocated Slurm job on MZ73")
    require_gpu_write_path(str(args.output.resolve()))
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("allocated CUDA device unavailable")
    result = run(args.request, args.checkpoint, args.output)
    status = result["sella_refinement"]["status"]
    print(json.dumps({"status": status, "scientifically_validated_ts": False}))
    raise SystemExit(1 if status == "failed" else 0)


if __name__ == "__main__":
    main()
