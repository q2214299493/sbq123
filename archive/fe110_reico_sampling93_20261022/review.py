"""Review both returned sampling batches and select geometry-diverse DFT candidates."""
from __future__ import annotations

import csv
from collections import Counter

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_adsorption_validation_20261018.runtime import verify
from archive.fe110_reico_sampling93_20261022.prepare import DEST, GEOMETRY, PRIOR, ROOT
from scripts.adsorption.reico_sampling import geometry_audit
from scripts.adsorption.reico_selection import select_frames
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def checked_return(package):
    request = verify(package / "validation_request.json", package / "submission_authorization.json")
    returned = package / "returned"
    manifest = load_json_object(returned / "return_manifest.json")
    for entry in manifest["files"]:
        path = (returned / entry["path"]).resolve()
        if not path.is_relative_to(returned.resolve()) or sha256_file(path) != entry["sha256"]:
            raise ValueError("returned source bytes changed")
    exit_record = load_json_object(returned / "output/producer_exit_record.json")
    if exit_record["exit_code"] != 0 or exit_record["request_sha256"] != sha256_file(package / "validation_request.json"):
        raise ValueError("sampling producer failed or has stale request")
    device = load_json_object(returned / "output/candidate_device.json")
    if device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != request["gpu_uuid"]:
        raise ValueError("actual CUDA binding changed")
    result = load_json_object(returned / "output/sampling_result.json")
    if result["checkpoint_sha256"] != request["models"]["candidate"]["sha256"]:
        raise ValueError("sampling checkpoint changed")
    expected = {r["sample_id"] for r in request["samples"]}
    if len(result["cases"]) != len(expected) or {c["sample_id"] for c in result["cases"]} != expected:
        raise ValueError("sampling case membership changed")
    return request, result, exit_record, sha256_file(returned / "return_manifest.json")


def checked_frames(package, request, result):
    config = load_json_object(package / request["generation_config_path"])
    sources = {r["sample_id"]: r for r in request["samples"]}
    rows = []
    for case in result["cases"]:
        family = case["sample_id"]
        source = sources[family]
        directory = package / "returned/output/sampling" / family
        frames = case["frames"]
        if (case["optimizer_steps"] > request["limits"]["max_steps"]
                or [f["step"] for f in frames] != list(range(case["optimizer_steps"] + 1))
                or case["partition"] != source.get("partition", "train")):
            raise ValueError("trajectory step budget/partition changed")
        initial = read(package / source["structure_path"], format="vasp")
        previous = initial.positions.copy()
        for frame in frames:
            structure = directory / frame["structure_path"]
            if sha256_file(structure) != frame["structure_sha256"]:
                raise ValueError("sampled structure changed")
            if load_json_object(structure.with_suffix(".json")) != frame:
                raise ValueError("standalone frame/source summary mismatch")
            atoms = read(structure, format="vasp")
            audit = geometry_audit(atoms, initial, config["pair_minimum_A"], request["limits"])
            if audit["failures"] != frame["geometry_audit"]["failures"]:
                raise ValueError("independent geometry review disagrees")
            movement = float(np.linalg.norm(atoms.positions - previous, axis=1).max())
            if movement > request["limits"]["maxstep_A"] + 1e-10:
                raise ValueError("frame displacement exceeded cap")
            if frame["step"] == 0 and movement > 1e-12:
                raise ValueError("initial frame differs from source")
            previous = atoms.positions.copy()
            forces = np.asarray(frame["forces_eV_per_A"])
            if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
                raise ValueError("incomplete/nonfinite saved model force")
            if audit["failures"] and frame is not frames[-1]:
                raise ValueError("sampling continued after geometry guard")
            rows.append({"sample_id": family + f"_step{frame['step']:03d}", "family_id": family,
                         "composition": case["composition"], "partition": case["partition"], "step": frame["step"],
                         "structure_path": str(structure.resolve()), "structure_sha256": frame["structure_sha256"],
                         "frame_metadata_path": str(structure.with_suffix(".json").resolve()),
                         "frame_metadata_sha256": sha256_file(structure.with_suffix(".json")),
                         "geometry_guard_failures": audit["failures"], "already_DFT_labeled": False})
    return rows


def existing_labels():
    old = ROOT / "calculations/fe110_reico_pilot300_20261022/probe6_v1/checks/20261022T084625Z"
    labels = {}
    for row in load_json_object(old / "dataset_review.json")["samples"]:
        assert row["electronic_converged"] and row["normal_completion"] and row["geometry_review_pass"]
        labels[row["sample_id"] + "_step000"] = {"structure_path": old / row["structure_path"],
            "structure_sha256": row["structure_sha256"], "job_id": row["source_job_id"],
            "review_path": old / "dataset_review.json"}
    new = PRIOR / "dft_review6_v1/checks/20261022T143902Z"
    binding = load_json_object(new / "validated_completion.json")
    assert sha256_file(new / "completion_review.json") == binding["completion_review_sha256"]
    for row in load_json_object(new / "completion_review.json")["samples"]:
        assert row["static_label_validation"] == "PASS"
        labels[row["sample_id"]] = {"structure_path": new / "vasp" / row["sample_id"] / "POSCAR",
            "structure_sha256": row["input_hashes"]["POSCAR"], "job_id": row["job_id"],
            "review_path": new / "completion_review.json"}
    assert len(labels) == 12
    return labels


def bind_labels(rows, labels):
    for row in rows:
        label = labels.get(row["sample_id"])
        if label is None:
            continue
        if sha256_file(label["structure_path"]) != label["structure_sha256"]:
            raise ValueError("existing DFT POSCAR changed")
        atoms = read(row["structure_path"], format="vasp")
        reference = read(label["structure_path"], format="vasp")
        if (atoms.get_chemical_symbols() != reference.get_chemical_symbols()
                or not np.allclose(atoms.cell, reference.cell, atol=1e-12, rtol=0)):
            raise ValueError("DFT/sampling order or cell changed")
        _, delta = find_mic(atoms.positions - reference.positions, atoms.cell, [True, True, False])
        if delta.max() > 1e-12:
            raise ValueError("existing DFT label is not the sampled coordinates")
        row.update({"already_DFT_labeled": True, "sampling_structure_path": row["structure_path"],
                    "sampling_structure_sha256": row["structure_sha256"],
                    "structure_path": str(label["structure_path"].resolve()),
                    "structure_sha256": label["structure_sha256"], "DFT_job_id": label["job_id"],
                    "DFT_review_path": str(label["review_path"].resolve()),
                    "DFT_review_sha256": sha256_file(label["review_path"])})
    if sum(r["already_DFT_labeled"] for r in rows) != 12:
        raise ValueError("existing12 labels not exactly recovered")


def review():
    rows, runs = [], []
    for package in (PRIOR, DEST):
        request, result, exit_record, manifest_sha = checked_return(package)
        rows.extend(checked_frames(package, request, result))
        runs.append({"package": str(package), "producer": exit_record, "manifest_sha256": manifest_sha,
                     "case_status_counts": dict(Counter(c["status"] for c in result["cases"]))})
    summary = load_json_object(GEOMETRY / "summary_0100.json")
    families = {r["family_id"]: r for r in summary["families"] if r["status"] == "CPU_GEOMETRY_CANDIDATE"}
    if {r["family_id"] for r in rows} != set(families):
        raise ValueError("combined sampling does not cover exactly99 frozen families")
    for row in rows:
        if any(row[k] != families[row["family_id"]][k] for k in ("partition", "composition")):
            raise ValueError("combined family provenance/partition changed")
    bind_labels(rows, existing_labels())
    selection = select_frames(rows)
    selection.update({"source_runs": runs, "successful_random_families": 99, "failed_generator_family": "family_0084",
                      "independent_final_test_forces_inspected": False, "DFT_submissions_performed": 0})
    output = DEST / "selection"
    output.mkdir(exist_ok=False)
    write_json_exclusive(output / "frame_inventory.json", {"frames": rows})
    write_json_exclusive(output / "selected_frames.json", selection)
    with (output / "selected_frames.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        columns = ["sample_id", "family_id", "composition", "partition", "step", "already_DFT_labeled",
                   "structure_path", "structure_sha256"]
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selection["selected"])
    print({k: selection[k] for k in ("input_frame_count", "guard_valid_frame_count", "selected_count", "existing_DFT_labels",
                                    "new_DFT_candidates", "partition_counts", "composition_counts", "short_families")})


if __name__ == "__main__":
    review()
