"""Review all returned ML frames before any DFT handoff;no model selection."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from archive.fe110_adsorption_validation_20261018.review import surface_metrics
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, review, surface_pose_symmetries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy
from .prepare import OUTPUT, PACKAGE, ROOT
from .runtime import verify


def fragment_formulas(symbols, edges):
    remaining = set(range(len(symbols)))
    fragments = []
    while remaining:
        component, todo = set(), [min(remaining)]
        while todo:
            atom = todo.pop()
            if atom in component:
                continue
            component.add(atom)
            for a, b in edges:
                if atom in (a, b):
                    todo.append(b if atom == a else a)
        remaining -= component
        counts = {s: sum(symbols[i] == s for i in component) for s in ["C", "H", "O"]}
        fragments.append("".join(s + (str(n) if n > 1 else "") for s, n in counts.items() if n))
    return sorted(fragments)


def post_relaxation_geometry(seed, final, audit, rules):
    delta = minimum_image_delta_xy(final.frac - seed.frac) @ seed.cell
    distances = np.linalg.norm(minimum_image_delta_xy(final.frac[:, None] - final.frac[None]) @ final.cell, axis=2)
    np.fill_diagonal(distances, np.inf)
    cart = final.frac @ final.cell
    height = float(cart[45:, 2].min() - cart[:45, 2].max())
    slab_max = float(np.linalg.norm(delta[:45], axis=1).max())
    ready = bool(distances.min() >= rules["contact_validation"]["hard_contact_distance_angstrom"] and height > 0
        and slab_max <= rules["surface_reconstruction"]["maximum_slab_displacement_angstrom"])
    symbols = [s for s, n in zip(final.symbols, final.counts, strict=True) for _ in range(n)][45:]
    return {"status": "DIAGNOSTIC_DFT_GEOMETRY_READY" if ready else "NEEDS_GEOMETRY_REVIEW",
        "diagnostic_DFT_geometry_ready": ready, "scientifically_accepted": False,
        "minimum_pair_distance_A": float(distances.min()), "minimum_height_above_highest_relaxed_Fe_A": height,
        "maximum_slab_displacement_A": slab_max, "fragment_formulas_from_connectivity": fragment_formulas(symbols, audit["final_graph"]),
        "intact_original_target_retained": audit["final_graph_preserved"],
        "initial_CARE_placement_height_threshold_applied_as_final_gate": False,
        "interpretation": "C3 fragmentation is a diagnostic product candidate;not an intact C3 success" if not audit["final_graph_preserved"] else "intact ML candidate;DFT acceptance pending"}


def audit_frames(seed, frames, final):
    if not frames:
        raise ValueError("empty optimizer trajectory")
    ads = list(range(45, len(seed.frac)))
    graph = sorted(connectivity(seed, ads))
    changed, fmax_history = [], []
    minimum_contact, maximum_step, fixed_max = float("inf"), 0.0, 0.0
    previous = None
    for step, atoms in enumerate(frames):
        if len(atoms) != len(seed.frac) or not np.allclose(atoms.cell, seed.cell, rtol=0, atol=1e-12):
            raise ValueError("trajectory atom count or cell changed")
        fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
        if fixed != list(range(18)):
            raise ValueError("trajectory fixed mask changed")
        forces = atoms.get_forces(apply_constraint=False)
        frac = atoms.get_scaled_positions(wrap=False)
        if forces.shape != (len(seed.frac), 3) or not np.isfinite(forces).all() or not np.isfinite(frac).all():
            raise ValueError("invalid per-frame coordinates/forces")
        fixed_max = max(fixed_max, float(np.abs(minimum_image_delta_xy(frac[:18] - seed.frac[:18]) @ seed.cell).max()))
        if step == 0 and not np.allclose(minimum_image_delta_xy(frac - seed.frac) @ seed.cell, 0, rtol=0, atol=1e-10):
            raise ValueError("optimization did not start from frozen seed")
        if previous is not None:
            maximum_step = max(maximum_step, float(np.linalg.norm(minimum_image_delta_xy(frac - previous) @ seed.cell, axis=1).max()))
        previous = frac
        distances = np.linalg.norm(minimum_image_delta_xy(frac[:, None] - frac[None]) @ seed.cell, axis=2)
        np.fill_diagonal(distances, np.inf)
        minimum_contact = min(minimum_contact, float(distances.min()))
        if sorted(connectivity(replace(seed, frac=frac), ads)) != graph:
            changed.append(step)
        fmax_history.append(float(np.linalg.norm(forces[18:], axis=1).max()))
    if fixed_max > 1e-10 or not np.allclose(minimum_image_delta_xy(previous - final.frac) @ seed.cell, 0, rtol=0, atol=1e-10):
        raise ValueError("fixed layer moved or returned finalPOSCAR differs from trajectory")
    return {"frames": len(frames), "fixed_max_displacement_A": fixed_max, "maximum_adjacent_atom_displacement_A": maximum_step,
        "minimum_pair_distance_over_trajectory_A": minimum_contact, "graph_changed_frames_0based": changed,
        "seed_graph": graph, "final_graph": sorted(connectivity(final, ads)),
        "final_graph_preserved": sorted(connectivity(final, ads)) == graph, "ML_fmax_history_eV_A": fmax_history}


def review_results():
    request, _, scope = verify(PACKAGE / "request.json")
    returned = OUTPUT / "returned"
    manifest = load_json_object(OUTPUT / "final_manifest.json")
    for row in manifest["files"]:
        p = returned / row["path"]
        if p.stat().st_size != row["bytes"] or sha256_file(p) != row["sha256"]:
            raise ValueError("returned artifact changed")
    producer = load_json_object(returned / "output/producer_exit_record.json")
    controller = load_json_object(returned / "output/controller_exit_record.json")
    if any(r["exit_code"] != 0 or r["request_sha256"] != sha256_file(PACKAGE / "request.json") for r in [producer, controller]):
        raise ValueError("successful bounded execution not proved")
    selection = load_json_object(PACKAGE / "evidence/selection.json")
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    # The existing candidate manifest binds the verified clean surface used for symmetry.
    care = load_json_object(ROOT / "calculations/fe110_care8_isomers_20260716/candidate_manifest.json")
    slab = read_poscar(ROOT / care["source_slab"])
    operations = surface_pose_symmetries(slab)
    records, finals = [], {}
    for model, checkpoint in scope["models"].items():
        device = load_json_object(returned / "output" / (model + "_device.json"))
        if device["physical_gpu_uuid"] != scope["gpu_uuid"] or device["model_device"] != "cuda:0":
            raise ValueError("wrong actual model device")
        payload = load_json_object(returned / "output" / (model + "_cases.json"))
        if payload["checkpoint_sha256"] != checkpoint["sha256"]:
            raise ValueError("frozen model changed")
        for case, record in zip(scope["cases"], payload["cases"], strict=True):
            directory = returned / "output" / model / case["name"] / "seed"
            seed, final = read_poscar(PACKAGE / case["seed_path"]), read_poscar(directory / "POSCAR")
            frames = read(directory / "optimization.traj", index=":")
            audit = audit_frames(seed, frames, final)
            if (record["source_structure_sha256"] != case["seed_sha256"] or record["name"] != case["name"]
                    or record["optimizer_steps"] + 1 != len(frames) or record["error"] is not None
                    or not np.isclose(audit["ML_fmax_history_eV_A"][-1], record["ML_movable_fmax_eV_A"], rtol=1e-6)):
                raise ValueError("optimizer trajectory/receipt mismatch")
            contact = review(final, final, list(range(45, len(final.frac))))
            post = post_relaxation_geometry(seed, final, audit, rules)
            records.append({"model": model, **record, "composition": case["composition"], "trajectory_audit": audit,
                "initial_placement_checker_on_final_diagnostic_only": contact,
                "post_relaxation_geometry_review": post, "final_POSCAR_sha256": sha256_file(directory / "POSCAR"),
                "geometry_eligible_for_DFT_review": post["diagnostic_DFT_geometry_ready"],
                "DFT_force_or_convergence_verified": False})
            finals[(model, case["name"])] = final
    pair_geometry = {case["name"]: surface_metrics(finals[("control", case["name"])], finals[("new512", case["name"])], slab, operations) for case in scope["cases"]}
    for metrics in pair_geometry.values():
        metrics["same_graph_between_ML_models"] = metrics.pop("same_graph_as_DFT")
    result = {"status": "ML_PAIR2_RETURNED_AND_REVIEWED_NOT_DFT_VALIDATED", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "producer_elapsed_seconds": (datetime.fromisoformat(producer["finished_at"]) - datetime.fromisoformat(producer["started_at"])).total_seconds(),
        "cases": records, "old_new_final_geometry": pair_geometry, "selection_exposure": [c["exposure"] for c in selection["cases"]],
        "next_DFT_policy": {"paired_screening_jobs": 4, "cores_each": 32, "NSW_each": 80, "EDIFFG_eV_A": -0.02,
            "same_minimum_required_before_speedup_ratio": True, "no_automatic_continuation": True},
        "model_promoted": False, "DFT_submitted": False,
        "correction_to_v1": "CARE initial placement 1.35A height is diagnostic on relaxed finals;use fixed/cell/finite/configured contact/surface checks and explicit chemical reclassification;no model rerun",
        "source_files": source_file_manifest([Path(__file__), rules_path, PACKAGE / "request.json", OUTPUT / "final_manifest.json", OUTPUT / "collection_receipt.json", OUTPUT / "geometry_review.json"])}
    write_json_exclusive(OUTPUT / "geometry_review_v2.json", result)
    print({"status": result["status"], "elapsed": result["producer_elapsed_seconds"],
        "cases": [{k: r[k] for k in ["model", "name", "optimizer_steps", "ML_movable_fmax_eV_A", "geometry_eligible_for_DFT_review"]} for r in records],
        "graph_changes": {r["model"] + ":" + r["name"]: r["trajectory_audit"]["graph_changed_frames_0based"] for r in records}}, flush=True)


if __name__ == "__main__":
    review_results()
