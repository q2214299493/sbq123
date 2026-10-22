"""Review the returned six-family pilot and prepare, never submit, six statics."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_adsorption_validation_20261018.runtime import digest, local_path, verify
from scripts.adsorption.reico_sampling import geometry_audit
from scripts.artifact_io import load_json_object, write_json_exclusive
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_active_learning_force_label

PACKAGE = Path("calculations/fe110_reico_pilot300_20261022/sampling6_v1")
PRIOR = Path("calculations/fe110_reico_pilot300_20261022/probe6_v1/checks/20261022T084625Z/gpu_comparison_v1")


def review():  # noqa: C901 - linear source/geometry/force checks with explicit fail-fast branches.
    request = verify(PACKAGE / "validation_request.json", PACKAGE / "submission_authorization.json")
    returned = PACKAGE / "returned"
    exit_record = load_json_object(returned / "output/producer_exit_record.json")
    if exit_record["exit_code"] != 0 or exit_record["request_sha256"] != digest(PACKAGE / "validation_request.json"):
        raise ValueError("failed or stale producer")
    device = load_json_object(returned / "output/candidate_device.json")
    if device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != request["gpu_uuid"]:
        raise ValueError("CUDA binding mismatch")
    result = load_json_object(returned / "output/sampling_result.json")
    if result["checkpoint_sha256"] != request["models"]["candidate"]["sha256"]:
        raise ValueError("checkpoint identity mismatch")
    originals = {r["sample_id"]: r for r in request["samples"]}
    if len(result["cases"]) != 6 or {r["sample_id"] for r in result["cases"]} != set(originals):
        raise ValueError("family membership changed")
    prior = load_json_object(PRIOR / "returned/output/candidate_forces.json")
    if prior["checkpoint_sha256"] != result["checkpoint_sha256"]:
        raise ValueError("initial comparison used a different model")
    prior = {r["sample_id"]: r for r in prior["samples"]}
    guards = load_json_object(PACKAGE / request["generation_config_path"])["pair_minimum_A"]
    targets = load_json_object(PACKAGE / "evidence/frozen_frame_targets.json")["target_step_by_family"]
    summaries, selected, comparisons = [], [], []
    frame_count = valid_count = 0
    for case in result["cases"]:
        family = case["sample_id"]
        source = originals[family]
        directory = returned / "output/sampling" / family
        frames = case["frames"]
        if ([f["step"] for f in frames] != list(range(case["optimizer_steps"] + 1))
                or case["optimizer_steps"] > request["limits"]["max_steps"] or case["partition"] != "train"):
            raise ValueError("trajectory step budget or partition changed")
        initial = read(directory / frames[0]["structure_path"], format="vasp")
        original = read(PACKAGE / source["structure_path"], format="vasp")
        _, delta = find_mic(initial.positions - original.positions, original.cell, [True, True, False])
        if delta.max() > 1e-12 or initial.get_chemical_symbols() != source["symbols"]:
            raise ValueError("initial coordinate correspondence failed")
        force_difference = float(np.max(np.abs(np.asarray(frames[0]["forces_eV_per_A"]) - prior[family]["predicted_forces_eV_per_A"])))
        previous, good = initial.positions.copy(), []
        for frame in frames:
            poscar = local_path(directory, frame["structure_path"])
            if digest(poscar) != frame["structure_sha256"]:
                raise ValueError("frame bytes changed")
            atoms = read(poscar, format="vasp")
            audit = geometry_audit(atoms, initial, guards, request["limits"])
            if audit["failures"] != frame["geometry_audit"]["failures"]:
                raise ValueError("independent geometry review disagrees")
            if np.linalg.norm(atoms.positions - previous, axis=1).max() > request["limits"]["maxstep_A"] + 1e-10:
                raise ValueError("step size exceeded")
            previous = atoms.positions.copy()
            force = np.asarray(frame["forces_eV_per_A"])
            if force.shape != (len(atoms), 3) or not np.isfinite(force).all():
                raise ValueError("invalid saved force vector")
            if not np.isclose(np.linalg.norm(force[45:], axis=1).max(), frame["ML_adsorbate_fmax_eV_A"], atol=1e-5):
                raise ValueError("force norm disagrees")
            frame_count += 1
            if not audit["failures"]:
                good.append(frame)
                valid_count += 1
            elif frame is not frames[-1]:
                raise ValueError("sampling continued after a failed geometry guard")
        candidates = [f for f in good if 0 < f["step"] <= targets[family]]
        if not candidates:
            raise ValueError("no noninitial frame for " + family)
        chosen = candidates[-1]
        chosen_path = directory / chosen["structure_path"]
        candidate_atoms = read(chosen_path, format="vasp")
        # Conservative same-order PBC near-duplicate diagnostic, without alignment.
        for earlier in [original] + [a for composition, a in comparisons if composition == case["composition"]]:
            _, diff = find_mic(candidate_atoms.positions[45:] - earlier.positions[45:], initial.cell, [True, True, False])
            if float(np.sqrt(np.mean(diff**2))) < .10:
                raise ValueError("selected candidate is a near duplicate;review without padding")
        comparisons.append((case["composition"], candidate_atoms))
        selected.append({"sample_id": family + f"_step{chosen['step']:03d}", "family_id": family,
                         "composition": case["composition"], "step": chosen["step"], "target_step": targets[family],
                         "structure_path": str(chosen_path), "structure_sha256": chosen["structure_sha256"],
                         "partition": "train", "geometry_audit": chosen["geometry_audit"]})
        summaries.append({"family_id": family, "composition": case["composition"], "status": case["status"],
                          "optimizer_steps": case["optimizer_steps"], "saved_frames": len(frames), "valid_frames": len(good),
                          "last_valid_step": good[-1]["step"], "error": case["error"],
                          "initial_ML_adsorbate_fmax_eV_A": frames[0]["ML_adsorbate_fmax_eV_A"],
                          "last_valid_ML_adsorbate_fmax_eV_A": good[-1]["ML_adsorbate_fmax_eV_A"],
                          "initial_force_max_abs_repeat_difference_eV_A": force_difference,
                          "selected_step": chosen["step"], "final_geometry_audit": frames[-1]["geometry_audit"]})
    report = {"document_kind": "reviewed_reico_sampling6_return", "request_sha256": digest(PACKAGE / "validation_request.json"),
              "return_manifest_sha256": digest(returned / "return_manifest.json"), "producer": exit_record,
              "device": device, "checkpoint_sha256": result["checkpoint_sha256"], "cases": summaries,
              "total_frames": frame_count, "geometry_guard_valid_frames": valid_count,
              "noninitial_guard_valid_frames": valid_count - 6, "DFT_labeled_initial_frames": 6,
              "new_DFT_labels": 0, "selected_candidates": selected, "scientific_acceptance": False,
              "dedup_scope": "selected six versus their seeds and same-composition selected frames;0.10A same-order adsorbate RMSD",
              "full_pool_clustering_or_permutation_invariance": False}
    write_json_exclusive(PACKAGE / "sampling_review.json", report)
    return report


def prepare(report):
    destination = PACKAGE / "dft_review6_v1"
    destination.mkdir(exist_ok=True)
    rows = []
    for candidate in report["selected_candidates"]:
        directory = destination / candidate["sample_id"]
        if directory.exists():
            # Resume a completed input preparation without rewriting any evidence.
            profile = load_json_object(directory / "input_profile.json")
            label = load_json_object(directory / "label_request.json")
            check = load_json_object(directory / "submission_preflight.json")
            if (digest(directory / "POSCAR") != candidate["structure_sha256"]
                    or label["sampling_request_sha256"] != report["request_sha256"]
                    or digest(Path(profile["profile_path"])) != profile["profile_sha256"]
                    or any(digest(directory / name) != sha for name, sha in check["files"].items())):
                raise ValueError("partial preparation changed;inspect before recovery")
        else:
            directory.mkdir(exist_ok=False)
            shutil.copyfile(candidate["structure_path"], directory / "POSCAR")
            profile = build_fe110_active_learning_force_label(directory)
            write_json_exclusive(directory / "input_profile.json", profile)
            write_json_exclusive(directory / "label_request.json", {
                "document_kind": "fe110_reico_sampled_fixed_geometry_force_label_request", **candidate,
                "sampling_request_sha256": report["request_sha256"], "source_return_manifest_sha256": report["return_manifest_sha256"],
                "requested_labels": ["compatible_TOTEN", "all_atom_forces", "total_and_local_magnetic_moments"],
                "ionic_convergence_required": False, "scientific_acceptance": False})
            # Canonical preflight itself owns submission_preflight.json.
            check = preflight(directory, "diagnostic_static")
        if not check["passed"]:
            raise ValueError("prepared static preflight failed: " + candidate["sample_id"])
        rows.append({**candidate, "directory": str(directory), "bundle_sha256": check["bundle_sha256"],
                     "input_hashes": check["files"], "cores": profile["cores"], "status": "PREPARED_NOT_SUBMITTED"})
    batch = {"document_kind": "fe110_reico_sampled_six_static_preparation", "samples": rows,
             "new_DFT_jobs_submitted": 0, "new_configurations_if_submitted": len(rows),
             "existing_pilot_labels": 6, "pilot_label_cap": 300, "label_cap_remaining_if_all_pass": 288,
             "requires_separate_VASP_execution_authorization_and_gates": True, "automatic_retry": False}
    write_json_exclusive(destination / "batch_request.json", batch)
    return batch


if __name__ == "__main__":
    existing = PACKAGE / "sampling_review.json"
    report = load_json_object(existing) if existing.exists() else review()
    if (report["request_sha256"] != digest(PACKAGE / "validation_request.json")
            or report["return_manifest_sha256"] != digest(PACKAGE / "returned/return_manifest.json")):
        raise ValueError("cannot resume a review with changed source bindings")
    batch = prepare(report)
    print(json.dumps({"frames": report["total_frames"], "guard_valid": report["geometry_guard_valid_frames"],
                      "prepared_statics": len(batch["samples"]), "DFT_submitted": 0}))
