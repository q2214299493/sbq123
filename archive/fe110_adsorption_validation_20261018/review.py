"""Review returned exact-force and surface-anchored geometry comparisons."""

from __future__ import annotations

import csv
import argparse
import itertools
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy

from .prepare import BASE, DEST, ROOT
from .validation_helpers import force_metrics


def rms(displacement) -> float:
    return float(np.sqrt(np.mean(np.sum(displacement * displacement, axis=1))))


def hydrogen_maps(reference) -> list[list[int]]:
    symbols = expanded_symbols(reference)[45:]
    graph = sorted(connectivity(reference, list(range(45, len(reference.frac)))))
    hydrogens = [i for i, symbol in enumerate(symbols) if symbol == "H"]
    result = []
    for order in itertools.permutations(hydrogens):
        indices = list(range(len(symbols)))
        for a, b in zip(hydrogens, order, strict=True):
            indices[a] = b
        mapped = sorted(tuple(sorted((indices[a], indices[b]))) for a, b in graph)
        if mapped == graph:
            result.append(indices)
    return result


def surface_metrics(reference, candidate, slab, operations) -> dict:
    if expanded_symbols(reference) != expanded_symbols(candidate) or not np.allclose(reference.cell, candidate.cell):
        raise ValueError("geometry order/cell mismatch")
    scores = []
    maps = hydrogen_maps(reference)
    heavy = [i for i, s in enumerate(expanded_symbols(reference)[45:]) if s != "H"]
    for rotation, translation in operations:
        mapped_clean = slab.frac @ rotation.T + translation
        distances = np.linalg.norm(minimum_image_delta_xy(mapped_clean[:, None, :] - slab.frac[None, :, :]) @ slab.cell, axis=2)
        mapping = np.argmin(distances, axis=1)
        if len(set(mapping)) != 45 or distances[np.arange(45), mapping].max() > .01:
            raise ValueError("invalid clean-slab symmetry")
        transformed = candidate.frac @ rotation.T + translation
        fe = minimum_image_delta_xy(transformed[:45] - reference.frac[mapping]) @ reference.cell
        for indices in maps:
            delta = minimum_image_delta_xy(transformed[45:][indices] - reference.frac[45:]) @ reference.cell
            scores.append({"adsorbate_RMSD_A": rms(delta), "heavy_adsorbate_RMSD_A": rms(delta[heavy]),
                           "movable_Fe_RMSD_A": rms(fe[18:]), "slab_RMSD_A": rms(fe),
                           "adsorbate_max_displacement_A": float(np.linalg.norm(delta, axis=1).max())})
    best = min(scores, key=lambda row: (max(row["adsorbate_RMSD_A"], row["slab_RMSD_A"]), row["adsorbate_RMSD_A"]))
    ads = list(range(45, len(reference.frac)))
    ref_graph, final_graph = [sorted(connectivity(pose, ads)) for pose in (reference, candidate)]
    cart = candidate.frac @ candidate.cell
    delta = minimum_image_delta_xy(candidate.frac[:, None, :] - candidate.frac[None, :, :]) @ candidate.cell
    distances = np.linalg.norm(delta, axis=2)
    np.fill_diagonal(distances, np.inf)
    symbols = expanded_symbols(candidate)
    best.update(reference_graph=ref_graph, final_graph=final_graph, same_graph_as_DFT=ref_graph == final_graph,
        minimum_pair_distance_A=float(distances.min()),
        nearest_Fe=[{"atom_index_0based": i, "symbol": symbols[i], "Fe_index_0based": int(np.argmin(distances[i, :45])),
                     "distance_A": float(distances[i, :45].min()), "height_A": float(cart[i, 2])} for i in ads],
        C_O_distances=[{"C_index_0based": i, "O_index_0based": j, "distance_A": float(distances[i, j])}
                       for i in ads for j in ads if symbols[i] == "C" and symbols[j] == "O"])
    return best


def review_forces(request: dict, returned: Path, model: str) -> dict:
    payload = json.loads((returned / "output" / (model + "_heldout.json")).read_bytes())
    if payload["checkpoint_sha256"] != request["models"][model]["sha256"]:
        raise ValueError("force predictions use another checkpoint")
    rows = {row["sample_id"]: row for row in request["heldout"]}
    if len(payload["samples"]) != len(rows) or {s["sample_id"] for s in payload["samples"]} != set(rows):
        raise ValueError("incomplete heldout prediction")
    sums, records = {}, []
    for sample in payload["samples"]:
        row = rows[sample["sample_id"]]
        if sample["structure_sha256"] != row["structure_sha256"]:
            raise ValueError("predictions are not exact-structure")
        metrics = force_metrics(row["forces_eV_per_A"], sample["predicted_forces_eV_per_A"], row["symbols"], row["fixed_atom_indices_0based"])
        records.append({"sample_id": row["sample_id"], "metrics": metrics})
        for name, values in metrics.items():
            count = values["atom_count"]
            if not count:
                continue
            total = sums.setdefault(name, {"count": 0, "squared": 0., "max": 0.})
            total["count"] += count
            total["squared"] += count * values["vector_rmse_eV_A"]**2
            total["max"] = max(total["max"], values["vector_max_eV_A"])
    return {"samples": records, "groups": {name: {"atom_count": val["count"],
        "vector_RMSE_eV_A": float(np.sqrt(val["squared"] / val["count"])),
        "maximum_vector_error_eV_A": val["max"]} for name, val in sums.items()}}


def review() -> None:
    request = json.loads((DEST / "validation_request.json").read_bytes())
    returned = DEST / "returned"
    record = json.loads((returned / "output/producer_exit_record.json").read_bytes())
    if record["exit_code"] or record["request_sha256"] != sha256_file(DEST / "validation_request.json"):
        raise ValueError("producer failed or source request changed; review partial results separately")
    for model in request["models"]:
        device = json.loads((returned / "output" / (model + "_device.json")).read_bytes())
        if not device["model_device"].startswith("cuda") or device["physical_gpu_uuid"] != request["gpu_uuid"]:
            raise ValueError("model was not on the authorized GPU")
    forces = {model: review_forces(request, returned, model) for model in request["models"]}
    slab = read_poscar(DEST / "geometry/clean_Fe45_CONTCAR")
    operations = surface_pose_symmetries(slab)
    geometry = []
    for case in request["geometry_cases"]:
        reference = read_poscar(DEST / case["reference_path"])
        if sha256_file(DEST / case["reference_path"]) != case["reference_sha256"]:
            raise ValueError("DFT reference changed")
        for model in request["models"]:
            for origin in ("seed", "minimum"):
                folder = returned / "output" / model / case["name"] / origin
                result = json.loads((folder / "case_record.json").read_bytes())
                metrics = surface_metrics(reference, read_poscar(folder / "POSCAR"), slab, operations)
                geometry.append({"name": case["name"], "model": model, "origin": origin, **result, **metrics})
    group_changes = {}
    for name, before in forces["baseline"]["groups"].items():
        after = forces["candidate"]["groups"][name]
        group_changes[name] = {"baseline_RMSE_eV_A": before["vector_RMSE_eV_A"], "candidate_RMSE_eV_A": after["vector_RMSE_eV_A"],
            "reduction_percent": 100 * (before["vector_RMSE_eV_A"] - after["vector_RMSE_eV_A"]) / before["vector_RMSE_eV_A"]}
    result = {"status": "VALIDATION_EVIDENCE_NOT_AUTOMATIC_PROMOTION", "request_sha256": sha256_file(DEST / "validation_request.json"),
        "producer": record, "heldout_count": len(request["heldout"]),
        "independent_source_jobs": sorted({s["calculation_group"] for s in request["heldout"]}),
        "forces": forces, "force_group_changes": group_changes, "geometry": geometry,
        "geometry_metric": "real face-preserving clean-Fe45 symmetries,xyPBC and graph-equivalent H only; no height/COM/Kabsch fit",
        "training_performed": False, "new_VASP": False, "model_promoted": False, "VASP_acceleration_proved": False}
    write_json_exclusive(DEST / "validation_review.json", result)
    columns = ["name", "model", "origin", "status", "optimizer_steps", "ML_movable_fmax_eV_A", "adsorbate_RMSD_A", "movable_Fe_RMSD_A", "same_graph_as_DFT"]
    with (DEST / "geometry_comparison.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(geometry)
    print(json.dumps({"heldout_group_changes": group_changes,
        "geometry": [{key: row.get(key) for key in columns} for row in geometry]}, indent=2))


def record() -> None:
    result = json.loads((DEST / "validation_review.json").read_bytes())
    request = json.loads((DEST / "validation_request.json").read_bytes())
    failed = next(row for row in result["geometry"] if row["model"] == "candidate" and row["name"] == "06_C" and row["origin"] == "seed")
    if failed["same_graph_as_DFT"] or result["producer"]["exit_code"]:
        raise ValueError("case outcome differs from reviewed evidence")
    write_json_exclusive(DEST / "failure_case.json", {
        "case_id": "fe110_adsorption_2185_06c_target_motif_lost_20261018",
        "classification": "TARGET_MOTIF_LOST_NOT_ENGINEERING_FAILURE",
        "model_sha256": request["models"]["candidate"]["sha256"],
        "source_review_sha256": sha256_file(DEST / "validation_review.json"),
        "source_geometry": "returned/output/candidate/06_C/seed/POSCAR",
        "source_geometry_sha256": sha256_file(DEST / "returned/output/candidate/06_C/seed/POSCAR"),
        "predicted_final_identity": "CO* + C* + H*", "target_identity": "intact C-O-CH",
        "ML_movable_fmax_eV_A": failed["ML_movable_fmax_eV_A"],
        "adsorbate_RMSD_to_reviewed_DFT_A": failed["adsorbate_RMSD_A"],
        "DFT_force_error_at_failed_ML_geometry": "NOT_MEASURED",
        "root_cause": "UNRESOLVED_MODEL_ERROR_VS_DIFFERENT_BASIN_SELECTION",
        "automatic_training_or_new_VASP": False})
    pool_path = BASE / "adsorption_calibration_20261018_v1/current_trajectories/dataset_review.json"
    pool = json.loads(pool_path.read_bytes())
    write_json_exclusive(DEST / "next_exact_force_comparison_plan.json", {
        "status": "LOCAL_PLAN_NOT_SUBMITTED", "scope": "baseline and frozen2185 on existing24 exact DFT frames",
        "models": request["models"], "source_dataset_sha256": sha256_file(pool_path),
        "source_dataset_path": pool_path.relative_to(ROOT).as_posix(),
        "samples": [{key: row[key] for key in ("sample_id", "source_name", "structure_path", "structure_sha256", "source_OUTCAR_sha256")} for row in pool["samples"]],
        "priority": "06_C off-equilibrium region; quantify error before choosing another fine-tune",
        "training": False, "new_VASP": False, "model_promoted": False,
        "GPU_execution_requires_separate_authorization": True})
    now = datetime.now(timezone.utc).isoformat()
    paths = [(ROOT / "docs/reviews/fe110_adsorption_validation_2185_20261018.md", "repository_document"),
             (ROOT / "archive/fe110_adsorption_validation_20261018/authorization.md", "user_authorization"),
             (DEST / "validation_request.json", "repository_document"),
             (DEST / "validation_review.json", "module_validation"),
             (DEST / "returned/output/producer_exit_record.json", "calculation_file"),
             (DEST / "failure_case.json", "module_validation"),
             (DEST / "validation_junit.xml", "module_validation")]
    event_id = "task-fe110-adsorption-2185-validated-mixed-20261018"
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "Authorized frozen2185 GPU validation completed;heldout force errors improve but06_C loses target motif;no model promotion/training/VASP.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p), "authority": authority, "observed_at": now} for p, authority in paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-calibration-ready-20261018"],
        "payload": {
            "objective": "Use completed frozen2185 validation evidence to improve adsorption acceleration without promoting a chemically unreliable raw-seed optimizer.",
            "phase": "active",
            "current_evidence": [
                "User authorized validation;only one GPU1 direct run v2 executed;actual model PID2578442 on cuda:0;producer exit0 after22.34s;59 returned files hash-verified.",
                "Frozen16 frames from2whole heldout jobs:adsorbate force vectorRMSE0.234745→0.106876eV/A(-54.5%);all reported Fe/C/O/H groups improve;no training or epoch selection.",
                "Same-seed adsorbate RMSD to the same existing DFT reference:06_C0.866→1.694A with CO+C+H prediction;07_B1.623→1.595A;08_A0.956→0.611A. Geometry is mixed,not general acceleration success.",
                "Minimum-start drift is small underML fmax0.10,but candidate06_C/07_B stop at0steps;do not interpret this as equality of DFT and ML stationary points.",
                "Failure case saved:06_C target motif lost;DFT error at the failed ML geometry remains unmeasured;model error versus basin selection is unresolved.",
                "Existing24 compatible DFT frames remain untrained. Local next-force-comparison plan only;no new VASP or automatic training,default-model change,or retry."
            ],
            "one_executable_step": "Prepare a bounded exact-structure baseline/candidate force comparison on the existing24DFT frames,prioritizing06_C off-equilibrium;obtain new GPU authorization before execution,then decide whether fine-tuning is justified.",
            "submission_boundary": "The authorized16heldout/3geometry GPU validation has finished. No further GPU/VASP/training/promotion is authorized.",
            "done_when": [
                "Completed frozen validation force/geometry evidence and the06_C failure case are preserved without an acceleration/global-stability claim.",
                "New-domain exact-structure errors are reviewed before selecting a targeted adaptation or alternative pre-relaxation strategy.",
                "Any adopted acceleration is ultimately checked against compatible matched VASP steps/time and reviewed final chemistry."
            ],
            "constraints": ["Do not use the observed16heldout frames for gradients or retrospective epoch choice.",
                "LowML force alone does not preserve an adsorption motif;06_C failed-target prediction cannot replace its intactDFT reference.",
                "Do not change VASP parameters,other jobs,backend roles or existing checkpoints. MatRIS remains an optional audit model."],
            "authoritative_references": ["configs/execution_backends.yaml", "modules/adsorption_workflow/README.md",
                "docs/reviews/fe110_adsorption_validation_2185_20261018.md", (DEST / "validation_review.json").relative_to(ROOT).as_posix()]
        }}
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"event": str(target), "sha256": sha256_file(target)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("review", "record"), default="review", nargs="?")
    args = parser.parse_args()
    {"review": review, "record": record}[args.action]()
