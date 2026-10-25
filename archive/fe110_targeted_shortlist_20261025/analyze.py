"""Select a few existing sources; create no executable calculation or label request."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from archive.fe110_combined_force_package_20261023.prepare import isolate
from archive.fe110_reico_followup_20261024.analyze import paused_c3_sources
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.adsorption.reico_environment_audit import read_geometry
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.neb_agent.submission import submission_status

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/targeted_shortlist_20261025_v1.json"


def pick_labelled(rows, composition, graph, exclude_group=None):
    eligible = [r for r in rows if r["partition"] == "train" and r["composition"] == composition
        and r.get("data_qc_status") == "PASS" and not r.get("magnetic_review_flags")
        and r.get("magnetic_review_level") == "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"
        and r["adsorbate_component_count"] == 1 and r["graph_signature"] == graph
        and r["source_group"] != exclude_group and np.isfinite(r["movable_fmax_eV_A"])]
    if not eligible:
        raise ValueError("no reviewed connected training source matching the target graph")
    return min(eligible, key=lambda r: (r["movable_fmax_eV_A"], r["sample_id"]))


def geometry(row, rules):
    atoms = read_geometry(row)
    symbols = atoms.get_chemical_symbols()
    distances = atoms.get_all_distances(mic=True)
    environment = chemical_environment(atoms, rules)
    environment["adsorbate_edges_local_0based"] = [list(edge) for edge in environment["adsorbate_edges_local_0based"]]
    nearest = []
    for index in range(45, len(atoms)):
        if symbols[index] not in {"C", "O"}:
            continue
        fe = int(np.argmin(distances[index, :45]))
        nearest.append({"adsorbate_atom_1based": index + 1, "element": symbols[index],
            "Fe_atom_1based": fe + 1, "distance_A": float(distances[index, fe])})
    co = [float(distances[i, j]) for i in range(45, len(atoms)) if symbols[i] == "C"
          for j in range(45, len(atoms)) if symbols[j] == "O"]
    pairs = [(float(distances[i, j]), i + 1, j + 1) for i in range(len(atoms)) for j in range(i + 1, len(atoms))]
    contact = min(pairs)
    return {"symbols": symbols, **environment, "minimum_C_O_A": min(co) if co else None,
        "nearest_Fe_by_C_O": nearest, "minimum_contact_A": contact[0], "minimum_contact_atoms_1based": list(contact[1:]),
        "minimum_adsorbate_height_above_top_Fe_A": float(atoms.positions[45:, 2].min() - atoms.positions[:45, 2].max()),
        "fixed_atoms": 18, "low_force_or_stability_inferred_from_geometry": False}


def scope(evidence_root):
    config_path = evidence_root / CONFIG.relative_to(ROOT)
    config = load_json_object(config_path)
    paths = {key: evidence_root / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen source changed: " + key)
    if not source_file_manifest_valid(load_json_object(paths["joint_summary"])):
        raise ValueError("joint coverage binding changed")
    return config_path, config, paths


def build():
    config_path, config, paths = scope(ROOT)
    training = load_json_object(paths["training"])["frames"]
    pool = {r["sample_id"]: r for r in load_json_object(paths["pool"])["frames"]}
    scores = {r["sample_id"]: r for r in load_json_object(paths["soap_scores"])["frames"]}
    rules = yaml.safe_load(paths["rules"].read_text(encoding="utf-8"))["connectivity"]
    paused = {r["name"]: {**r, "sample_id": r["name"], "composition": "C3H2O"} for r in paused_c3_sources()}
    graph05 = geometry(paused[config["graph_reference05"]], rules)["graph_signature"]
    graph07 = geometry(paused[config["paused07"]], rules)["graph_signature"]
    anchor = next(r for r in training if r["sample_id"] == config["C2_low_force_anchor"])
    c3 = pick_labelled(training, "C3H2O", graph05)
    c2 = pick_labelled(training, "C2H3", anchor["graph_signature"], anchor["source_group"])
    magnetic = load_json_object(paths["magnetic_case"])
    if magnetic["data_qc_status"] != "MAGNETIC_REVIEW_REQUIRED":
        raise ValueError("magnetic quarantine authority changed")
    candidates = [
        (c3, "A", "EXISTING_DFT_C3_SAMPLING_SOURCE", "Try to obtain intact C3 near-equilibrium frames;initial single-point already exists"),
        (c2, "A", "EXISTING_DFT_C2_SAMPLING_SOURCE", "Try to obtain low-force C2H3 from a source outside10_B"),
        (magnetic, "A", "EXISTING_MAGNETIC_LABEL_REVIEW", "Review the current magnetic branch using existing evidence before considering more labels"),
        (paused[config["paused07"]], "B", "PAUSED_ALTERNATIVE_C3_GRAPH", "Alternative C3 connectivity;no exact native distance-graph match in current training;keep paused"),
        (pool[config["conditional_offeq"]], "B", "CONDITIONAL_OFF_EQUILIBRIUM_STATIC", "One residual local environment/SOAP outlier;consider only after magnetic review and evidence of useful force error")]
    output = ROOT / config["output"]
    output.mkdir(parents=True, exist_ok=True)
    proposals, geometry_rows, source_rows = [], {}, []
    for row, priority, purpose, gap in candidates:
        sid = row["sample_id"]
        source_rows.append(row)
        detail = geometry(row, rules)
        native_path = output / "native_geometry_audits" / (sid + ".json")
        native = load_json_object(native_path)
        assert native["verdict"] == "pass" and native["fixed_atoms"] == detail["fixed_atoms"]
        assert abs(native["nearest_contact"]["distance_A"] - detail["minimum_contact_A"]) <= 5.1e-5
        if detail["minimum_C_O_A"] is not None:
            assert abs(native["co_distance"]["distance_A"] - detail["minimum_C_O_A"]) <= 5.1e-5
        geometry_rows[sid] = detail
        known = purpose.startswith("EXISTING_DFT_")
        proposals.append({"sample_id": sid, "priority": priority, "purpose": purpose, "gap_addressed": gap,
            "composition": row["composition"], "structure_path": row["structure_path"], "structure_sha256": row["structure_sha256"],
            "symbols": detail["symbols"], "split": "train", "source_family_id": row.get("family_id"),
            "source_job_id": row.get("source_job_id"), "existing_label_in_training": known,
            "existing_movable_fmax_eV_A": row["movable_fmax_eV_A"] if known else None,
            "source_magnetic_review_level": row.get("magnetic_review_level"),
            "source_data_qc_status": row.get("data_qc_status"), "source_partition": row.get("partition", "UNASSIGNED_PAUSED_SOURCE"),
            "SOAP_ratio": scores[sid]["novelty_ratio"] if sid in scores else None,
            "requires_future_relaxation_to_obtain_low_force": purpose.startswith("EXISTING_DFT_") or purpose == "PAUSED_ALTERNATIVE_C3_GRAPH",
            "is_confirmed_low_force_candidate": False, "new_DFT_authorized": False, "training_authorized": False})
    cfg = load_json_object(paths["coverage_config"])
    prior_path = ROOT / cfg["prior_manifest"]
    inventory_path = ROOT / cfg["inventory"]
    reserved = reserved_geometries(load_json_object(inventory_path), load_json_object(prior_path),
                                  prior_path.parent, cfg["reserved_geometry_catalogs"])
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    reserved_families = {r.get("family_id") for r, _ in reserved if r.get("family_id")}
    reserved_jobs = {r.get("source_job_id") for r, _ in reserved if r.get("source_job_id")}
    for row in source_rows:
        assert not row.get("family_id") or row["family_id"] not in reserved_families
        assert not row.get("source_job_id") or row["source_job_id"] not in reserved_jobs
    kept, isolation = isolate(proposals, output, reserved, read_poscar(slab_path), .20)
    receipt = submission_status(Path(paused[config["paused07"]]["structure_path"]).parent)
    assert receipt["status"] == "NOT_RESERVED", "prepared07 has a submission marker;do not reinterpret it"
    fe = magnetic["local_magnetization_muB"][:45]
    minimum = min((r for r in training if r["composition"] == "C3H2O"), key=lambda r: r["movable_fmax_eV_A"])
    sources = [config_path, Path(__file__), *paths.values(), prior_path, inventory_path, slab_path,
        ROOT / "archive/fe110_combined_force_package_20261023/prepare.py",
        ROOT / "archive/fe110_reico_followup_20261024/analyze.py",
        ROOT / "scripts/adsorption/reico_chemical_environments.py",
        ROOT / "scripts/adsorption/reico_environment_audit.py",
        ROOT / "scripts/adsorption/reico_dataset_audit.py",
        *[ROOT / p for p in cfg["reserved_geometry_catalogs"]],
        *sorted({Path(r["structure_path"]) for r, _ in reserved}),
        *[Path(r["structure_path"]) for r in source_rows],
        *[output / "native_geometry_audits" / (r["sample_id"] + ".json") for r in proposals]]
    save_once(output / "input_binding.json", {"source_files": source_file_manifest(sources)})
    save_once(output / "candidate_isolation.json", isolation)
    save_once(output / "geometry_details.json", {"candidates": geometry_rows})
    result = {"candidates": proposals, "geometry_isolation_passed_ids": [r["sample_id"] for r in kept],
        "magnetic_diagnostic": {"sample_id": magnetic["sample_id"], "SCF": magnetic["SCF"],
            "minimum_Fe_moment_muB": min(fe), "Fe_atom_1based": fe.index(min(fe)) + 1,
            "grade_changed": False, "new_DFT_needed_for_this_read_only_review": False},
        "C3_graph07_matches_in_current_training": sum(r["composition"] == "C3H2O" and r["graph_signature"] == graph07 for r in training),
        "excluded_low_force_shortcut": {"sample_id": minimum["sample_id"], "fmax_eV_A": minimum["movable_fmax_eV_A"],
            "adsorbate_components": minimum["adsorbate_component_count"], "reason": "Formula alone does not establish an intact C3 skeleton"},
        "paused07_native_receipt_status": receipt["status"], "paused_sources_resumed": False,
        "new_low_force_labels_created": 0, "new_DFT_started": False, "training_started": False,
        "source_files": source_file_manifest([output / "input_binding.json", output / "candidate_isolation.json", output / "geometry_details.json"])}
    save_once(output / "shortlist_local_only.json", result)
    print({"selected_ids": [r["sample_id"] for r in proposals], "isolation_comparisons": isolation["comparisons"],
           "geometry_conflicts": len(isolation["geometry_conflicts"]),
           "existing_C3_force": c3["movable_fmax_eV_A"], "existing_C2_force": c2["movable_fmax_eV_A"], "07_graph_matches": result["C3_graph07_matches_in_current_training"]})


if __name__ == "__main__":
    build()
