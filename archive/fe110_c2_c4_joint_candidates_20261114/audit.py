"""Audit existing joint-pool coordinates, nominal binding and source isolation."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import restore_input_lattice
from scripts.adsorption.build_fe110_adsorption import Poscar, read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect_sources import BASE, OUT, PRIOR, ROOT
from .geometry import geometry_report, iron_maps, nearest, packed_pose

PACKAGE = BASE / "combined_force_package_20261113_v1"
SLAB = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
PAPER = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/paper_aqcat25_ft512_20261112_v1"


def external_c2_proposals(operations, maps):
    root = BASE / "independent_nearstable_inventory_20261113_v1"
    plan = load_json_object(root / "source_plan.json")
    inventory = load_json_object(root / "physical_inventory.json")
    candidates = [r for r in plan["near_force_candidate_references"]
                  if r["proposed_role"] == "external_C2_isomer_force_candidate_not_admitted"]
    summaries = {r["job_id"]: r for r in inventory["source_summaries"]}
    entries, bound = [], {root / "source_plan.json", root / "physical_inventory.json"}
    for job in sorted({r["source_job_id"] for r in candidates}):
        rows = [r for r in candidates if r["source_job_id"] == job]
        xdatcar = Path(rows[0]["source_XDATCAR"])
        initial_path = next(Path(x["path"]) for x in summaries[job]["source_files"] if Path(x["path"]).name == "POSCAR")
        if sha256_file(xdatcar) != rows[0]["source_XDATCAR_sha256"]:
            raise ValueError("external C2 trajectory changed")
        initial = read(initial_path, format="vasp")
        base = read_poscar(initial_path)
        frames = read(xdatcar, format="vasp-xdatcar", index=":")
        for row in rows:
            atoms = frames[row["ionic_step"] - 1]
            restore_input_lattice(atoms, initial, xdatcar)
            pose = Poscar("", base.cell, base.symbols, base.counts, atoms.get_scaled_positions(wrap=False), base.flags)
            entries.append({**packed_pose(pose, operations, maps), "id": row["candidate_id"], "source": str(xdatcar),
                            "source_locator": "ionic_step=" + str(row["ionic_step"]),
                            "dedup_key": row["source_XDATCAR_sha256"] + ":" + str(row["ionic_step"]),
                            "source_job_id": job, "protected_scope": "prospective_external_C2_validation;not_training"})
        bound.update([xdatcar, initial_path])
    if len(entries) != 26:
        raise ValueError("external C2 validation proposal scope changed")
    return entries, bound


def reference_sets(operations, maps):
    config_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    config = load_json_object(config_path)
    prior = ROOT / config["prior_manifest"]
    reserved = reserved_geometries(load_json_object(ROOT / config["inventory"]), load_json_object(prior),
                                   prior.parent, [ROOT / p for p in config["reserved_geometry_catalogs"]])
    if len(reserved) != 513:
        raise ValueError("reserved513 scope changed;review before proceeding")
    manifest = load_json_object(PACKAGE / "training_manifest.json")
    result = {"protected": [], "train536": [], "existing_label": [], "paper_training_family": []}
    bound = {config_path, ROOT / config["inventory"], prior, PACKAGE / "training_manifest.json"}

    def append(kind, name, path, extra=None):
        path = Path(path)
        packed = packed_pose(read_poscar(path), operations, maps)
        digest = sha256_file(path)
        result[kind].append({**packed, "id": name, "source": str(path), "sha256": digest, "dedup_key": digest, **(extra or {})})
        bound.add(path)

    for row, _ in reserved:
        append("protected", row["sample_id"], row["structure_path"], {"family_id": row.get("family_id"), "source_job_id": row.get("source_job_id")})
    for split, rows in manifest["splits"].items():
        for row in rows:
            append("train536" if split == "train" else "protected", row["sample_id"], PACKAGE / row["structure_path"],
                   {"family_id": row.get("family_id"), "source_job_id": row.get("source_job_id")})
    for row in manifest["quarantined_observed_heldout"]:
        append("protected", row["sample_id"], PACKAGE / row["structure_path"])
    labels_path = BASE / "energy_reaction_sidecar_20261113_v1/energy_label_sidecar_final_v2.json"
    labels = load_json_object(labels_path)["records"]
    seen = set()
    for row in labels:
        path = Path(row["structure_path"])
        key = sha256_file(path)
        if key in seen:
            continue
        seen.add(key)
        append("existing_label", row["sample_id"], path, {"physical_label_key": row.get("physical_label_key"),
               "partition": row.get("partition"), "existing_QC_flags": row["flags"],
               "coordinate_force_match": row.get("coordinate_force_match"), "raw_magnetic_grade": row.get("raw_magnetic_grade")})
    paper_labels = []
    physical = set()
    for path in sorted(PAPER.glob("labels/*/force_label_review*/vasp_force_label.json")):
        row = load_json_object(path)
        bound.add(path)
        key = (row["outcar"]["sha256"], row["structure"]["sha256"])
        if key in physical:
            continue
        physical.add(key)
        geometry = Path(row["structure"]["path"])
        if sha256_file(geometry) != row["structure"]["sha256"]:
            raise ValueError("paper label geometry changed")
        append("paper_training_family", "paper_round" + str(row["round_index"]), geometry)
        paper_labels.append({"label_path": str(path), "label_sha256": sha256_file(path), "round_index": row["round_index"],
                             "structure": row["structure"], "outcar": row["outcar"],
                             "electronically_converged": row["electronically_converged"],
                             "original_force_only_eligibility_preserved": row["eligible_for_force_only_training"],
                             "compatibility_sha256": row["compatibility_sha256"],
                             "backend_source": row["scheduler_evidence"].get("backend_id"),
                             "permitted_use": "EXTERNAL_TRAINING_FAMILY_REVIEW_ONLY_NOT_INDEPENDENT_VALIDATION",
                             "new_backend_or_magnetic_admission": False})
    # Existing revised C3 validation seeds are protected as proposals; no virtual transfer is made.
    seed_path = BASE / "c3_independent_validation_proposal_20261113_v1/proposal_evidence.json"
    for row in load_json_object(seed_path)["candidates"]:
        if row["proposed_pose_file"]:
            append("protected", row["candidate_id"], row["proposed_pose_file"], {"protected_scope": "prospective_C3_validation_seed"})
    c2, c2_files = external_c2_proposals(operations, maps)
    result["protected"].extend(c2)
    bound.update(c2_files)
    for path in sorted(PAPER.glob("labels/*/POSCAR")):
        append("paper_training_family", path.parent.name, path, {"scope": "existing_training_or_label_request_family;completion_not_inferred"})
    bound.update([labels_path, seed_path])
    # Keep source aliases in the output manifest; avoid repeating hash-equivalent comparisons.
    result = {kind: list({r["dedup_key"]: r for r in rows}.values()) for kind, rows in result.items()}
    write_json_exclusive(OUT / "existing_paper_label_sources_v4.json", {"records": paper_labels,
                         "unique_physical_sources": len(paper_labels), "raw_labels_not_readmitted": True,
                         "source_files": source_file_manifest([Path(r["label_path"]) for r in paper_labels])})
    return result, bound


def audited_pool(refs, slab, rules, pair_minimum, operations, maps):
    coverage = load_json_object(PRIOR / "reico536_coverage_v3.json")
    pool_path = BASE / "joint_coverage_20261023_v3/pool_environments.json"
    pool = {r["sample_id"]: r for r in load_json_object(pool_path)["frames"]}
    bindings = {r["sample_id"]: r for r in load_json_object(PRIOR / "reico_pool_label_bindings_v3.json")["records"]}
    groups = {r["representative_id"]: r for r in coverage["groups"] if r["robust_missing_frames_all_scales"] > 0}
    # Historical SOAP outliers are inspected, not automatically selected.
    for name in ("family_0013_step016", "family_0028_step001", "family_0028_step002"):
        groups.setdefault(name, None)
    protected_families = {r.get("family_id") for r in refs["protected"] if r.get("family_id")}
    results, bound = [], {pool_path, PRIOR / "reico536_coverage_v3.json", PRIOR / "reico_pool_label_bindings_v3.json"}
    for number, (name, group) in enumerate(groups.items()):
        source = pool[name]
        path = Path(source["structure_path"])
        if sha256_file(path) != source["structure_sha256"]:
            raise ValueError("pool geometry changed")
        pose = read_poscar(path)
        metadata_path = Path(source["frame_metadata_path"])
        if sha256_file(metadata_path) != source["frame_metadata_sha256"]:
            raise ValueError("sampling metadata changed")
        metadata = load_json_object(metadata_path)
        geo = geometry_report(pose, slab, rules, pair_minimum)
        distances = {kind: nearest(pose, rows) for kind, rows in refs.items()}
        reasons = []
        protected = distances["protected"].get("minimum_ads_pose_RMSD_A_any_reference")
        if source["family_id"] in protected_families:
            reasons.append("PROTECTED_FAMILY")
        if protected is not None and protected <= .20:
            reasons.append("PROTECTED_ADSORBATE_POSE_WITHIN0p20A")
        if not geo["bottom18_only_fixed"] or not geo["same_clean_cell_within1e-6A"] or geo["pair_guard_failures"]:
            reasons.append("GEOMETRY_OR_MASK_REVIEW_REQUIRED")
        if bindings[name]["label_status"] != "NO_SAME_COORDINATE_DFT_LABEL_IN_AUDITED_CATALOG":
            reasons.append("EXISTING_LABEL_REVIEW_BEFORE_NEW_DFT")
        for kind in ("existing_label", "paper_training_family"):
            distance = distances[kind]["full_RMSD_A"]
            if distance is not None and distance <= 1e-7:
                reasons.append("POSSIBLE_EQUIVALENT_EXISTING_LABEL_NEEDS_ATOMMAP_NOT_NEW_DFT")
        record = {"candidate_id": name, "family_id": source["family_id"], "composition": source["composition"],
                  "source_path": str(path), "source_sha256": source["structure_sha256"],
                  "frame_metadata_path": str(metadata_path), "frame_metadata_sha256": source["frame_metadata_sha256"],
                  "source_kind": "EXISTING_REICO_SHORT_ML_TRAJECTORY_NOT_DFT_REACTION_PATH",
                  "ML_step": source["step"], "stored_old_ML_fmax_eV_A": metadata.get("ML_movable_fmax_eV_A"),
                  "geometry": geo, "isolation": distances, "new_SP_review_blockers": sorted(set(reasons)),
                  "family_risk_note": "prior sibling had magnetic or SCF failure;not proof this coordinate fails" if source["family_id"] in {"family_0028", "family_0086", "family_0021"} else None,
                  "prior_label_status": bindings[name]["label_status"],
                  "robust_missing_frames_all_scales": group["robust_missing_frames_all_scales"] if group else 0,
                  "pool_frames_of_joint_type": group["pool_frames"] if group else 0,
                  "historical512_SOAP_ratio": group["representative_SOAP_ratio"] if group else None,
                  "joint_signature": source["joint_signature"], "joint_by_scale": source["joint_by_scale"],
                  "candidate_class": "NEW_SP_REVIEW_CANDIDATE" if not reasons else "BLOCKED_OR_REUSE_REVIEW",
                  "new_training_admission": False}
        results.append((record, pose, packed_pose(pose, operations, maps)))
        bound.update([path, metadata_path])
        if number % 10 == 0:
            print({"audited_candidates": number + 1}, flush=True)
    return results, bound


def local_care_headers():
    path = OUT / "CARE_geometry_paths_noignore.txt"
    records = []
    for text in path.read_text(encoding="utf-8").splitlines():
        p = Path(text)
        if p.stat().st_size > 2 * 1024**2:
            raise ValueError("unexpected large CARE export")
        atoms = read(p, index=0)
        counts = Counter(atoms.get_chemical_symbols())
        records.append({"path": str(p), "sha256": sha256_file(p), "composition_counts": dict(counts),
                        "total_C": counts["C"], "Fe_count": counts["Fe"],
                        "forces_or_energy_stored": bool(atoms.calc and atoms.calc.results)})
    write_json_exclusive(OUT / "CARE_geometry_audit_v4.json", {"records": records, "new_structures": False,
                         "C4_C5_C6_records": sum(4 <= r["total_C"] <= 6 for r in records),
                         "source_files": source_file_manifest([path] + [Path(r["path"]) for r in records])})


def run():
    local_care_headers()
    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    maps = iron_maps(slab, operations)
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    geometry_path = ROOT / "configs/fe110_reico_pilot/geometry_v1.json"
    pairs = load_json_object(geometry_path)["pair_minimum_A"]
    refs, bound = reference_sets(operations, maps)
    audited, pool_files = audited_pool(refs, slab, rules, pairs, operations, maps)
    write_json_exclusive(OUT / "coordinate_site_isolation_audit_v4.json", {
        "records": [r for r, _, _ in audited], "reference_counts_unique_source_bindings": {k: len(v) for k, v in refs.items()},
        "surface_operations": len(operations), "source_protection_rule": "whole-family and conservative adsorbate symmetry RMSD<=0.20A",
        "geometric_equivalence_is_not_force_label_equivalence": True,
        "no_training_inference_DFT_geometry_generation_or_acceptance": True,
        "source_files": source_file_manifest(sorted(bound | pool_files | {SLAB, Path(__file__), rules_path, geometry_path,
                                                Path(__file__).with_name("geometry.py")}))})
    print({"audited": len(audited), "classes": dict(Counter(r["candidate_class"] for r, _, _ in audited)),
           "unique_reference_counts": {k: len(v) for k, v in refs.items()}}, flush=True)


if __name__ == "__main__":
    run()
