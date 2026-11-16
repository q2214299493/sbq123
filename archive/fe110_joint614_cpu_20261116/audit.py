"""CPU-only descriptive inventory. Never select, delete, relabel, or admit frames."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path

import numpy as np
import yaml
from ase import Atoms

from archive.fe110_c2_c4_gap_inventory_20261114.inventory import component_sizes
from archive.fe110_c2_c4_joint_candidates_20261114.geometry import (
    canonical_iron, distance_metrics, iron_maps, packed_pose,
)
from archive.fe110_force_diagnosis536_20261114.prepare import force_stage
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, write_json_exclusive,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "joint614_cpu_audit_20261116_v1"
PRIOR = BASE / "c2_c4_gap_inventory_20261114_v1"
PACKAGE = BASE / "combined_force_package_20261113_v1"
SCALES = (1.2, 1.25, 1.3)
BINS = [force_stage(x) for x in (.02, .05, .10, .50, 1.)]
REUSE, REPEAT, MISSING = "已有标签可复用", "现有数据重复偏多", "确实缺少标注"
BLOCKED = "已有记录但尚不可复用"


def gap_category(has_records, has_ready_records):
    return REUSE if has_ready_records else BLOCKED if has_records else MISSING


def source_root(row):
    if row.get("family_id"):
        return "reico:" + row["family_id"], "explicit family_id;different DFT jobs remain one family"
    if row.get("calculation_group"):
        return row["calculation_group"], "explicit calculation_group;not statistical independence proof"
    if row.get("source_job_id"):
        return "job:" + str(row["source_job_id"]), "source_job_id fallback"
    raise ValueError("missing explicit source root")


def force_stats(row):
    forces = np.asarray(row["DFT_forces_eV_per_A"], dtype=float)
    if forces.shape != (len(row["symbols"]), 3) or not np.isfinite(forces).all():
        raise ValueError("invalid DFT forces")
    free = sorted(set(range(len(forces))) - set(row["fixed_atom_indices_0based"]))
    groups = dict(row["force_role_groups"])
    if sorted(i for indices in groups.values() for i in indices) != free:
        raise ValueError("roles do not partition movable atoms")
    groups["movable_Fe"] = [i for i in free if row["symbols"][i] == "Fe"]
    groups["all_movable"] = free
    values = {}
    for name, indices in groups.items():
        magnitudes = np.linalg.norm(forces[indices], axis=1) if indices else np.array([])
        values[name] = {"atoms": len(indices), "fmax_eV_A": float(magnitudes.max()) if indices else None,
                        "mean_force_norm_eV_A": float(magnitudes.mean()) if indices else None}
    index = max(free, key=lambda i: np.linalg.norm(forces[i]))
    return values, {"index_1based": index + 1, "element": row["symbols"][index],
                    "original_role": next(k for k, v in row["force_role_groups"].items() if index in v)}


def component_formulas(symbols, edges):
    unseen, components = set(range(len(symbols))), []
    neighbors = defaultdict(set)
    for i, j in edges:
        neighbors[i].add(j)
        neighbors[j].add(i)
    while unseen:
        todo, members = [min(unseen)], set()
        while todo:
            i = todo.pop()
            if i in members:
                continue
            members.add(i)
            todo.extend(neighbors[i] - members)
        unseen -= members
        counts = Counter(symbols[i] for i in members)
        components.append("".join(s + (str(counts[s]) if counts[s] > 1 else "")
                                  for s in ("C", "H", "O") if counts[s]))
    return sorted(components)


def cluster_key(row):
    # Never let a development, legacy-scope, or different-force-bin frame replace another.
    return (row["partition"], row["qualification_scope"], row["composition"],
            row["force_bin"], row["joint_signature"])


def radius_clusters(records, distance, radius):
    """Deterministic representative-radius grouping, without single-linkage chaining."""
    representatives = defaultdict(list)
    assignment = {}
    for row in sorted(records, key=lambda r: r["sample_id"]):
        candidates = representatives[cluster_key(row)]
        close = [(distance(row["sample_id"], name), name) for name in candidates]
        close = [value for value in close if value[0] <= radius + 1e-12]
        if close:
            separation, name = min(close)
        else:
            name, separation = row["sample_id"], 0.
            candidates.append(name)
        assignment[row["sample_id"]] = {"representative_id": name, "representative_radius_A": separation}
    return assignment


def summarize(rows):
    return {"frames": len(rows), "source_roots": len({r["source_root"] for r in rows}),
            "DFT_jobs_with_known_ID": len({r["source_job_id"] for r in rows if r["source_job_id"]}),
            "frames_without_scheduler_ID": sum(not r["source_job_id"] for r in rows),
            "graphs": len({r["graph_signature"] for r in rows}),
            "joint_environments": len({r["joint_signature"] for r in rows}),
            "radius_representatives": len({r["near_duplicate"]["representative_id"] for r in rows}),
            "force_bins": dict(Counter(r["force_bin"] for r in rows)),
            "low_force_le0p05": sum(r["DFT_fmax_eV_A"] <= .05 for r in rows),
            "low_force_source_roots": sorted({r["source_root"] for r in rows if r["DFT_fmax_eV_A"] <= .05}),
            "low_force_C_backbone_connected": sum(r["DFT_fmax_eV_A"] <= .05 and r["carbon_backbone_connected"] for r in rows),
            "strict_frames": sum(r["qualification_scope"] == "STRICT_RAW_E_F_LOCALMAG" for r in rows),
            "maximum_force_element_counts": dict(Counter(r["max_force_atom"]["element"] for r in rows))}


def gap_inventory(training):
    """Reuse exact-coordinate label bindings; absence is bounded by that audited catalog."""
    coverage = load_json_object(PRIOR / "reico536_coverage_v3.json")
    bindings = {r["sample_id"]: r for r in load_json_object(PRIOR / "reico_pool_label_bindings_v3.json")["records"]}
    signatures = {r["joint_signature"] for r in training}
    gaps = []
    for group in coverage["groups"]:
        if group["joint_signature"] in signatures:
            continue
        labels, blocked, unlabeled = [], [], []
        for name in group["sample_ids"]:
            bound = bindings[name]
            if sha256_file(Path(bound["structure_path"])) != bound["structure_sha256"]:
                raise ValueError("candidate coordinates changed")
            physical = {r["physical_label_key"]: r for r in bound["physical_labels"]}
            if physical:
                labels.append({"sample_id": name, "structure_sha256": bound["structure_sha256"],
                               "label_status": bound["label_status"], "protected": bound["protected_exact_hash_or_family"],
                               "physical_labels": list(physical.values())})
            else:
                unlabeled.append(name)
            if bound["protected_exact_hash_or_family"] or bound["prior_geometry_guard_failures"]:
                blocked.append(name)
        ready = [r for r in labels if not r["protected"] and any(
            p["partition"] == "train" and p["coordinate_force_match"] and p["electronic_raw_pass"]
            and p["energy_force_evidence_ready_for_review"] for p in r["physical_labels"])]
        gaps.append({"gap_id": f"GAP_{len(gaps)+1:03d}", "composition": group["composition"],
                     "joint_signature": group["joint_signature"], "pool_frames": group["pool_frames"],
                     "pool_families": group["pool_families"], "robust_missing_frames_all_scales": group["robust_missing_frames_all_scales"],
                     "category": gap_category(bool(labels), bool(ready)),
                     "reuse_substatus": "COMPATIBLE_LABEL_REVIEW_CANDIDATE" if ready else "EXISTING_LABEL_ADMISSION_BLOCKED" if labels else "NO_SAME_COORDINATE_LABEL_IN_AUDITED_CATALOG",
                     "existing_labeled_members": labels, "unlabeled_sample_ids": unlabeled,
                     "blocked_member_ids": blocked, "representative_id_from_geometry_audit": group["representative_id"],
                     "DFT_force_bin_of_unlabeled_members": None, "frozen536_force_error": None,
                     "source_isolation": "reuse prior exact-hash/family flags;full symmetry isolation still required before future admission",
                     "new_DFT_budget_allocated": 0, "new_admission": False})
    return gaps


def load_reference_frames():
    labels_path = BASE / "force_diagnosis536_20261114_v1/qualified_reference_labels.json"
    labels = load_json_object(labels_path)["records"]
    manifest_path = PACKAGE / "training_manifest.json"
    manifest = load_json_object(manifest_path)
    original = {r["sample_id"]: r for split in ("train", "development") for r in manifest["splits"][split]}
    if len(labels) != 614 or set(original) != {r["sample_id"] for r in labels}:
        raise ValueError("not the614 train/development scope")
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["connectivity"]
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    slab = read_poscar(slab_path)
    operations = surface_pose_symmetries(slab)
    maps = iron_maps(slab, operations)
    records, poses, bound = [], {}, {labels_path, manifest_path, rules_path, slab_path, Path(__file__)}
    for row in labels:
        name, path = row["sample_id"], Path(row["structure_path"])
        if row["partition"] not in {"train", "development"} or sha256_file(path) != row["structure_sha256"]:
            raise ValueError("partition or exact structure hash mismatch")
        metadata = original[name]
        label_path = PACKAGE / metadata["label_source"]["path"]
        if sha256_file(label_path) != metadata["label_source"]["sha256"]:
            raise ValueError("source label metadata changed")
        pose = read_poscar(path)
        symbols = expanded_symbols(pose)
        if symbols != row["symbols"] or [i for i, flags in enumerate(pose.flags) if all(f.upper() == "F" for f in flags)] != row["fixed_atom_indices_0based"]:
            raise ValueError("atom order or Selective Dynamics mismatch")
        if not np.allclose(pose.cell, slab.cell, atol=1e-6, rtol=0):
            raise ValueError("different slab cell branch")
        atoms = Atoms(symbols, scaled_positions=pose.frac, cell=pose.cell, pbc=[True, True, False])
        env = chemical_environment(atoms, rules)
        scales = {str(s): chemical_environment(atoms, rules, scale=s) for s in SCALES}
        force, maximum = force_stats(row)
        fmax = force["all_movable"]["fmax_eV_A"]
        if abs(fmax - row["DFT_movable_fmax_eV_A"]) > 1e-12:
            raise ValueError("DFT force norm mismatch")
        root, root_basis = source_root(metadata)
        components = component_sizes(symbols[45:], env["adsorbate_edges_local_0based"])
        records.append({"sample_id": name, "partition": row["partition"], "composition": row["composition"],
                        "qualification_scope": row["qualification_scope"], "original_magnetic_grade": row["original_magnetic_grade"],
                        "source_root": root, "source_root_basis": root_basis, "source_job_id": str(row["source_job_id"]) if row["source_job_id"] else None,
                        "physical_label_key": row["physical_label_key"], "DFT_ionic_step": metadata["ionic_step"],
                        "source_collection": metadata.get("source_collection"), "structure_path": str(path),
                        "structure_sha256": row["structure_sha256"], "label_path": str(label_path),
                        "DFT_fmax_eV_A": fmax, "force_bin": force_stage(fmax), "role_DFT_force_magnitudes": force,
                        "max_force_atom": maximum, **env, "component_formulas": component_formulas(symbols[45:], env["adsorbate_edges_local_0based"]),
                        "carbon_backbone_connected": components["total_C"] > 0 and components["largest_C_C_connected_component"] == components["total_C"],
                        "carbon_graph": components, "joint_by_scale": {s: e["joint_signature"] for s, e in scales.items()},
                        "graph_by_scale": {s: e["graph_signature"] for s, e in scales.items()},
                        "graph_cutoff_sensitive": len({e["graph_signature"] for e in scales.values()}) > 1,
                        "joint_cutoff_sensitive": len({e["joint_signature"] for e in scales.values()}) > 1,
                        "new_admission": False, "ML_error": None})
        poses[name] = {**packed_pose(pose, operations, maps), "first_fe": canonical_iron(pose, maps["clean_frac"])}
        bound.update([path, label_path])
    return records, poses, bound, rules, len(operations)


def deduplicate(records, poses):
    cache = {}

    def separation(first, second):
        key = tuple(sorted((first, second)))
        if key not in cache:
            cache[key] = distance_metrics(poses[first]["pose"], poses[second], poses[first]["first_fe"])
        return cache[key]["full_RMSD_A"]

    radius = load_json_object(ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json")["geometry_duplicate_A"]
    sensitivity = {}
    for threshold in (.05, radius, .20):
        assignment = radius_clusters(records, separation, threshold)
        sensitivity[str(threshold)] = {split: len({assignment[r["sample_id"]]["representative_id"] for r in records if r["partition"] == split}) for split in ("train", "development")}
        if threshold == radius:
            for row in records:
                row["near_duplicate"] = assignment[row["sample_id"]]
                row["category"] = REUSE if row["sample_id"] == row["near_duplicate"]["representative_id"] else REPEAT
    cross_split = []
    training, development = [r for r in records if r["partition"] == "train"], [r for r in records if r["partition"] == "development"]
    for first in training:
        for second in development:
            if first["composition"] != second["composition"]:
                continue
            distance = separation(first["sample_id"], second["sample_id"])
            if distance <= .20:
                cross_split.append({"train_id": first["sample_id"], "development_id": second["sample_id"], "full_RMSD_A": distance})
    return radius, sensitivity, cross_split


def run():
    records, poses, bound, rules, symmetry_count = load_reference_frames()
    radius, sensitivity, cross_split = deduplicate(records, poses)
    by_id = {r["sample_id"]: r for r in records}
    source_members = defaultdict(list)
    for row in records:
        source_members[row["source_root"]].append(row)
    shared_roots = [name for name, rows in source_members.items() if len({r["partition"] for r in rows}) > 1]
    exact = {}
    for field in ("structure_sha256", "physical_label_key"):
        groups = defaultdict(list)
        for row in records:
            groups[row[field]].append(row["sample_id"])
        exact[field] = [ids for ids in groups.values() if len(ids) > 1]
    summaries = []
    for split in ("train", "development"):
        for scope in sorted({r["qualification_scope"] for r in records}):
            for composition in sorted({r["composition"] for r in records}):
                rows = [r for r in records if (r["partition"], r["qualification_scope"], r["composition"]) == (split, scope, composition)]
                if rows:
                    summaries.append({"partition": split, "qualification_scope": scope, "composition": composition, **summarize(rows)})
    gaps = gap_inventory([r for r in records if r["partition"] == "train"])
    backups_path = PRIOR / "compatible_backup_reuse.json"
    backups = load_json_object(backups_path)
    bound.update([ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json", PRIOR / "reico536_coverage_v3.json", PRIOR / "reico_pool_label_bindings_v3.json", backups_path])
    bound.update(Path(r["structure_path"]) for r in backups["records"])
    clusters = []
    for name in sorted({r["near_duplicate"]["representative_id"] for r in records}):
        rows = [r for r in records if r["near_duplicate"]["representative_id"] == name]
        clusters.append({"representative_id": name, "partition": by_id[name]["partition"], "frames": len(rows),
                         "source_roots": sorted({r["source_root"] for r in rows}), "sample_ids": [r["sample_id"] for r in rows],
                         "maximum_radius_A": max(r["near_duplicate"]["representative_radius_A"] for r in rows)})
    result = {"status": "CPU_DFT_LABEL_COVERAGE_COMPLETE_NO_MODEL_ERROR_OR_DFT_SELECTION", "records": records,
              "summary_by_scope_composition": summaries, "partition_summaries": {s: summarize([r for r in records if r["partition"] == s]) for s in ("train", "development")},
              "source_roots": [{"source_root": key, "sample_ids": [r["sample_id"] for r in rows], "DFT_jobs": sorted({r["source_job_id"] for r in rows if r["source_job_id"]}),
                                "partitions": sorted({r["partition"] for r in rows})} for key, rows in sorted(source_members.items())],
              "dedup_clusters": clusters, "radius_sensitivity_representative_counts": sensitivity,
              "exact_duplicate_groups": exact, "train_development_shared_source_roots": shared_roots, "cross_split_geometries_within0p20A": cross_split,
              "gap_groups_outside_training_coverage": gaps, "compatible_backup_reuse_references": backups["records"],
              "category_counts_614_only": dict(Counter(r["category"] for r in records)),
              "gap_category_counts_separate_universe": dict(Counter(r["category"] for r in gaps)),
              "geometric_rules": rules, "radius_scales": SCALES, "near_duplicate_radius_A": radius, "surface_symmetries": symmetry_count,
              "force_units": "eV/Angstrom;DFT magnitude,never ML error", "coordinate_units": "Angstrom",
              "scope_limits": ["source roots are provenance units,not statistical independence proof", "representative-radius groups are not new training splits or deletions",
                               "missing labels means no same-coordinate record in the bound catalog;not a global absence claim", "geometry contacts are not electronic bond orders or TS identities",
                               "all actual ML errors,DFT choices and budgets remain pending", "53heldout/16quarantine labels not read into force or environment analysis"],
              "source_files": source_file_manifest(sorted(bound))}
    write_json_exclusive(OUT / "joint_inventory.json", result)
    write_tables(result)
    print({"frames": len(records), "partitions": result["partition_summaries"], "categories": result["category_counts_614_only"],
           "gap_categories": result["gap_category_counts_separate_universe"], "shared_roots": shared_roots, "cross_split_near_pairs": len(cross_split)}, flush=True)


def write_tables(result, suffix=""):
    columns = ["结构ID", "分区", "标签资格", "组成", "来源根", "DFT作业", "DFT步", "最大DFT力_eV每A", "力区间", "最大力元素", "C最大力", "O最大力", "H最大力", "可动Fe最大力", "连接组分", "C骨架连通", "连接图", "Fe配位", "截断敏感", "近重复代表", "代表距离_A", "清单类别"]
    with (OUT / f"614帧联合清单{suffix}.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for r in result["records"]:
            writer.writerow([r["sample_id"], r["partition"], r["qualification_scope"], r["composition"], r["source_root"], r["source_job_id"], r["DFT_ionic_step"], r["DFT_fmax_eV_A"], r["force_bin"], r["max_force_atom"]["element"],
                             *[r["role_DFT_force_magnitudes"].get(role, {}).get("fmax_eV_A") for role in ("adsorbate_C", "adsorbate_O", "adsorbate_H", "movable_Fe")],
                             "+".join(r["component_formulas"]), r["carbon_backbone_connected"], r["graph_signature"], r["coordination_signature"], r["joint_cutoff_sensitive"], r["near_duplicate"]["representative_id"], r["near_duplicate"]["representative_radius_A"], r["category"]])
    with (OUT / f"缺口分类清单{suffix}.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["缺口ID", "组成", "类别", "复用或阻塞状态", "池中帧数", "池中来源家族数", "已有标签成员数", "无标签成员数", "几何代表", "连接配位环境", "DFT力区间", "新单点预算"])
        for r in result["gap_groups_outside_training_coverage"]:
            writer.writerow([r["gap_id"], r["composition"], r["category"], r["reuse_substatus"], r["pool_frames"], r["pool_families"], len(r["existing_labeled_members"]), len(r["unlabeled_sample_ids"]), r["representative_id_from_geometry_audit"], r["joint_signature"], "未知（无标签成员）", 0])


if __name__ == "__main__":
    run()
