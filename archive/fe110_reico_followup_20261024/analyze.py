"""Update a training-only audit view and prepare a few non-executable candidates."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil

import numpy as np
import yaml
from ase.io import read

from archive.fe110_combined_force_package_20261023.prepare import isolate
from archive.fe110_joint_coverage_20261023.prioritize import records
from archive.fe110_joint_coverage_20261023.run import enrich
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.adsorption.reico_joint_coverage import fixed_threshold_soap, joint_force_table, missing_environment_groups
from scripts.adsorption.reico_selection import frame_distance
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from .collect import CONFIG, ROOT, save_once, scope


def isolated_new_training(rows, output, reserved, slab, rules, scales):
    candidates = []
    for row in rows:
        if row["partition"] != "train" or row["data_qc_status"] != "PASS":
            continue
        atoms = read(row["structure_path"], format="vasp")
        atoms.pbc = [True, True, False]
        candidates.append(enrich({**row, "split":"train", "source_group":"reico_"+row["family_id"],
            "movable_fmax_eV_A":float(np.linalg.norm(np.array(row["forces_eV_per_A"])[18:], axis=1).max())}, atoms, rules, scales))
    admitted, result = isolate(candidates, output, reserved, slab, .20)
    save_once(output/"new_training_isolation.json", result)
    return admitted


def geometry_candidates(priorities, pool, training, output, reserved, slab):
    by_id = {r["sample_id"]:r for r in pool}
    proposals = []
    for composition in ("C2H3", "C3H2O"):
        eligible = [r for r in priorities["residual_diagnostic_groups"] if r["composition"] == composition
                    and r["robust_missing_frames_all_scales"] > 0]
        chosen = min(eligible, key=lambda r: (-r["pool_families"], -r["pool_frames"], r["representative_id"]))
        row = by_id[chosen["representative_id"]]
        target = output/"candidate_geometries"/(row["sample_id"]+".vasp")
        if target.exists():
            if sha256_file(target) != row["structure_sha256"]:
                raise ValueError("candidate geometry changed")
        else:
            target.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(row["structure_path"], target)
        atoms = read(target, format="vasp")
        distances = [(frame_distance(atoms, read(r["structure_path"], format="vasp")), r["sample_id"])
                     for r in training if r["composition"] == composition]
        nearest = min(distances)
        proposals.append({**row, "structure_path":str(target), "symbols":atoms.get_chemical_symbols(), "split":"train",
                          "diagnostic_group":chosen, "nearest_labeled_training_RMSD_A":nearest[0],
                          "nearest_labeled_training_id":nearest[1], "force_known":False,
                          "same_composition_DFT_force_not_inferred":True, "candidate_type":"GEOMETRY_GAP_BACKUP",
                          "new_DFT_recommended_now":False})
    kept, review = isolate(proposals, output, reserved, slab, .20)
    save_once(output/"candidate_geometry_isolation.json", review)
    return [{k:r[k] for k in ("sample_id", "composition", "structure_path", "structure_sha256", "diagnostic_group",
             "nearest_labeled_training_RMSD_A", "nearest_labeled_training_id", "force_known", "candidate_type",
             "new_DFT_recommended_now")} for r in kept]


def paused_c3_sources():
    directory = ROOT/"docs/reviews/fe110_c3_targeted_relaxation_20261023"
    inventory = load_json_object(directory/"input_inventory.json")
    source_root = Path(inventory["source_run_root"])
    for item in inventory["files"]:
        source = source_root/Path(item["path"]).relative_to("inputs")
        if sha256_file(source) != item["sha256"] or sha256_file(directory/item["path"]) != item["sha256"]:
            raise ValueError("paused C3 prepared source changed")
    plan = load_json_object(source_root/"plan.json")
    return [{"name":r["name"], "exact_smiles":r["exact_smiles"], "structure_path":str(source_root/r["name"]/"POSCAR"),
             "structure_sha256":sha256_file(source_root/r["name"]/"POSCAR"),
             "candidate_type":"EXISTING_PAUSED_C3_LOW_FORCE_SOURCE_PROPOSAL", "status":"PAUSED_NOT_SUBMITTED",
             "near_equilibrium_frame_exists":False, "requires_separate_execution_authority":True} for r in plan["cases"]]


def run():
    config, paths, needed, _ = scope()
    output = ROOT/config["output"]
    base_config = load_json_object(paths["prior_joint_config"])
    base_output = ROOT/base_config["output"]
    if not source_file_manifest_valid(load_json_object(paths["prior_joint_summary"])):
        raise ValueError("prior 366-frame audit source binding changed")
    new_path = output/"new_label_qc_local_only.json"
    new = load_json_object(new_path)
    if not source_file_manifest_valid(new):
        raise ValueError("new label QC binding changed")
    prior_cfg = load_json_object(ROOT/"configs/fe110_reico_pilot/coverage_audit_v1.json")
    prior_path = ROOT/prior_cfg["prior_manifest"]
    reserved = reserved_geometries(load_json_object(ROOT/prior_cfg["inventory"]), load_json_object(prior_path),
                                  prior_path.parent, prior_cfg["reserved_geometry_catalogs"])
    slab_path = ROOT/"calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    slab = read_poscar(slab_path)
    rules_path = ROOT/"configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["connectivity"]
    extra = isolated_new_training(new["samples"], output, reserved, slab, rules, base_config["radius_scales"])
    training = load_json_object(base_output/"training_environments.json")["frames"]+extra
    pool = load_json_object(base_output/"pool_environments.json")["frames"]
    cache_map = {r["sample_id"]:r for r in load_json_object(base_output/"descriptor_inventory.json")["files"]}
    soap, scores = fixed_threshold_soap(records(pool, cache_map), records(training, cache_map),
        load_json_object(ROOT/base_config["inputs"]["prior_soap"]["path"]))
    score_map = {r["sample_id"]:r for r in scores}
    pool = [{**r, **score_map[r["sample_id"]]} for r in pool]
    selected = {r["sample_id"] for r in load_json_object(paths["selection"])["selected"] if r["partition"] == "train"}
    coverage, missing = missing_environment_groups(pool, training, selected)
    forces = joint_force_table(training, base_config["force_edges_eV_A"])
    save_once(output/"audit_training_view_local_only.json", {"frames":training, "is_training_package":False})
    save_once(output/"training_joint_force.json", forces)
    save_once(output/"missing_environments.json", {"groups":missing})
    priorities = load_json_object(base_output/"gap_priorities.json")
    proposals = geometry_candidates(priorities, pool, training, output, reserved, slab)
    source_candidates = paused_c3_sources()
    save_once(output/"targeted_candidates.json", {"geometry_backups":proposals, "priority_low_force_sources":source_candidates,
        "new_DFT_or_training_authorized":False, "all_candidate_forces_unknown":True,
        "independent_C2H3_low_force_source":"NOT_IDENTIFIED;10_A remains heldout;10_B six frames remain same source"})
    old_labels = [r for key in ("initial_labels", "incremental_labels") for r in load_json_object(paths[key])["samples"]]
    old_ids = {r["sample_id"] for r in old_labels}
    if old_ids & {r["sample_id"] for r in new["samples"]}:
        raise ValueError("new labels duplicate already reviewed labels")
    save_once(output/"all_selected_label_qc_local_only.json", {"samples":old_labels+new["samples"],
        "source_files":source_file_manifest([paths["initial_labels"], paths["incremental_labels"], new_path])})
    snapshot = load_json_object(output/"scheduler_snapshot.json")
    result = {"status":"EXISTING_LABEL_CHECKPOINT_COMPLETE", "checked_at":snapshot["checked_at"],
        "queried_outstanding_receipt_jobs":len(snapshot["jobs"]), "scheduler_counts":snapshot["status_counts"],
        "new_labels_reviewed":len(new["samples"]), "new_QC_counts":dict(Counter(r["data_qc_status"] for r in new["samples"])),
        "new_partition_counts":dict(Counter(r["partition"] for r in new["samples"])),
        "all_selected_labels_reviewed":len(old_labels)+len(new["samples"]),
        "eligible_new_training_labels":len(extra), "audit_view_training_frames":len(training), "frozen_package_training_frames":366,
        "remaining_selected_train_not_in_audit_view":len(selected-{r["sample_id"] for r in training}),
        "train_without_success_receipts":sum(r["partition"] == "train" and r["sample_id"] in
            {v["sample_id"] for v in load_json_object(output/"collection_summary.json")["without_success_receipts"]} for r in needed),
        "chemical_coverage":coverage, "missing_joint_types":len(missing), "SOAP_fixed_threshold":soap,
        "force_by_composition":{c:{k:v for k,v in item.items() if k not in ("strata", "sample_ids")} for c,item in forces.items()},
        "conditional_residual_joint_types_after_all_selected_pass":len(priorities["residual_diagnostic_groups"]),
        "new_DFT_GPU_training_or_submission":False, "existing366package_changed":False,
        "reserved_labels_used_for_coverage_or_ranking":False,
        "recommendation":"Review existing outstanding submitted training jobs first;no new random high-energy DFT now;retain paused C3 low-force sources as first targeted options",
        "source_files":source_file_manifest([CONFIG, *paths.values(), new_path, Path(__file__), output/"new_training_isolation.json",
            output/"candidate_geometry_isolation.json", base_output/"gap_priorities.json", rules_path, slab_path,
            ROOT/"scripts/adsorption/reico_joint_coverage.py", ROOT/"archive/fe110_joint_coverage_20261023/prioritize.py",
            ROOT/"archive/fe110_combined_force_package_20261023/prepare.py"])}
    save_once(output/"summary.json", result)
    print({k:result[k] for k in ("status", "new_labels_reviewed", "eligible_new_training_labels", "audit_view_training_frames", "missing_joint_types")})


if __name__ == "__main__":
    run()
