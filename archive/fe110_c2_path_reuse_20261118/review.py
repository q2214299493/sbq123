"""Normalize historical scheduler evidence and assess path-label redundancy."""
from pathlib import Path

from archive.fe110_c2_c4_joint_candidates_20261114.geometry import distance_metrics, iron_maps, packed_pose
from archive.fe110_joint_priority_20261117.analyze import SLAB, guard_hashes, load, save, sha, table
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from .audit import RUN


def scheduler_summary(evidence):
    """Retain distinct native record schemas; controller success is not a queue state."""
    if evidence["document_kind"] == "slurm_native_controller_exit_events":
        return {"recorded_scheduler_state": evidence.get("scheduler_terminal_state"),
                "recorded_exit_code": None, "controller_exit_status": evidence.get("controller_exit_status"),
                "scope": "controller_process_record_not_COMPLETED_state"}
    if evidence["document_kind"] == "slurm_force_label_scheduler_evidence":
        return {"recorded_scheduler_state": evidence["job_state"], "recorded_exit_code": evidence["exit_code"],
                "controller_exit_status": None, "scope": "historical_native_scheduler_record_not_live_query"}
    if evidence["document_kind"] == "scheduler_job_evidence":
        return {"recorded_scheduler_state": evidence["status"], "recorded_exit_code": evidence.get("exit_code"),
                "controller_exit_status": None, "scope": "historical_LSF_record_not_live_query"}
    raise ValueError("unsupported scheduler evidence schema")


def run():
    source_path = RUN / "results/audit.json"
    source = load(source_path)
    bad = [p for p, digest in source["source_hashes"].items() if sha(p) != digest]
    if bad or guard_hashes() != source["frozen_after"]:
        raise ValueError("source or frozen binding changed: " + str(bad[:2]))
    rows = source["records"]
    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    maps = iron_maps(slab, operations)
    poses = {r["id"]: read_poscar(Path(r["structure_path"])) for r in rows}
    packed = {sid: packed_pose(pose, operations, maps) for sid, pose in poses.items()}
    pairs = []
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            metric = distance_metrics(poses[first["id"]], packed[second["id"]])
            pairs.append({"first": first["id"], "second": second["id"], **metric,
                          "near_duplicate_at_0p10_A": metric["full_RMSD_A"] <= .10,
                          "force_label_equivalence_proven": False})
    representatives = []
    for row in rows:
        metrics = [(distance_metrics(poses[row["id"]], packed[sid])["full_RMSD_A"], sid) for sid in representatives]
        matching = sorted((distance, sid) for distance, sid in metrics if distance <= .10)
        row["geometry_representative_0p10_A"] = matching[0][1] if matching else row["id"]
        row["geometry_representative_distance_A"] = matching[0][0] if matching else 0.
        if not matching:
            representatives.append(row["id"])
        evidence = load(row["scheduler_evidence"]["source_path"])
        if str(evidence["job_id"]) != str(row["scheduler_evidence"]["job_id"]):
            raise ValueError("scheduler job ID mismatch")
        row["normalized_historical_scheduler"] = scheduler_summary(evidence)
        row["training_reuse_blockers"] = (["NO_FRAME_LOCAL_MOMENTS", "NEB_NOT_NEW_STATIC_TRAINING_ADMISSION"]
                                           if row["kind"] != "additional_paper_physical_labels" else
                                           ["NEW_PACKAGE_REVIEW_REQUIRED", "CROSS_BACKEND_REUSE_NOT_AUTOMATIC"])
        row["new_DFT_for_training"] = "NOT_NEEDED_FOR_EXISTING_FORCE_ONLY_REUSE_REVIEW" if row["kind"] == "additional_paper_physical_labels" else "CONDITIONAL_IF_SELECTED_AND_LOCAL_MOMENT_EVIDENCE_CANNOT_BE_RECOVERED"
    paper = rows[12:]
    checks = {
        "22_records_22_physical_keys": len(rows) == len({r["physical_key"] for r in rows}) == 22,
        "all22_coordinates_electronic_numeric_compatibility": all(r["coordinate_force_match"] and r["electronic_pass"] and r["compatibility_pass"] for r in rows),
        "12_NEB_no_local_moment_tables": all(r["magnetic"]["local_moment_table_count"] == 0 for r in rows[:12]),
        "10_static_complete49_positive45Fe": all(len(r["magnetic"]["local_magnetization_muB"]) == 49 and r["magnetic"]["Fe_moment_range_muB"][0] > 0 for r in paper),
        "all10_original_force_only_eligibility_preserved": all(r["original_force_only_scope_preserved"] for r in paper),
        "9_Slurm_COMPLETED_0colon0": all(r["normalized_historical_scheduler"]["recorded_scheduler_state"] == "COMPLETED" and r["normalized_historical_scheduler"]["recorded_exit_code"] == "0:0" for r in paper[1:]),
        "r000_controller0_never_called_COMPLETED": paper[0]["normalized_historical_scheduler"]["recorded_scheduler_state"] is None and paper[0]["normalized_historical_scheduler"]["controller_exit_status"] == 0,
        "all_outcar_hashes_match": all(source["source_hashes"][r["OUTCAR_path"]] == r["OUTCAR_sha256"] for r in rows),
        "all_potcar_same_frozen_reference": len({r["compatibility"]["POTCAR_sha256"] for r in rows}) == 1,
        "protected_geometries_not_overlapped": all(not r["protected_overlap"] for r in rows),
        "no_independent_validation_claim": all(not r["independent_validation_eligible"] for r in rows),
        "no_automatic_admission": all(not r["new_training_admission"] for r in rows),
        "231_pairs_deduplicated": len(pairs) == 231,
        "no_new_scientific_compute": source["summary"]["new_compute"] == 0,
        "frozen_model_packages_task_protocol_backend_unchanged": guard_hashes() == source["frozen_before"] == source["frozen_after"],
        "1314_source_hashes_match": not bad and len(source["source_hashes"]) == 1314,
    }
    destination = RUN / "reviewed_v2"
    destination.mkdir(exist_ok=False)
    save(destination / "audit_reviewed.json", {"summary": source["summary"], "records": rows, "pairs": pairs,
                                              "geometry_representatives_0p10_A": representatives,
                                              "criterion": "greedy coverage representatives;not independent sources or deletion;force vectors not transferred",
                                              "raw_audit": {"path": str(source_path), "sha256": sha(source_path)},
                                              "review_source_sha256": sha(Path(__file__)), "checks": checks})
    table(destination / "C2标签免补算及阻塞.csv", rows, [(k, label) for k, label in [
        ("id", "结构ID"), ("structure_path", "坐标来源"), ("physical_key", "物理标签键"), ("C_C_distance_A", "CC距离_A"),
        ("movable_fmax_eV_A", "DFT最大可动力_eV_A"), ("total_magnetization_muB", "总磁矩_muB"), ("magnetic", "局域磁矩证据"),
        ("disposition", "用途资格"), ("normalized_historical_scheduler", "历史调度及进程证据"),
        ("geometry_representative_0p10_A", "近重复代表"), ("geometry_representative_distance_A", "代表距离_A"),
        ("training_reuse_blockers", "训练准入阻塞"), ("new_DFT_for_training", "训练用途是否需新DFT"),
        ("same_coordinate_force_diagnostic_requires_new_DFT", "诊断用途是否需新DFT"), ("new_training_admission", "自动准入")]])
    save(destination / "verification.json", {"checks": checks, "all_pass": all(checks.values()),
                                            "reviewed_sha256": sha(destination / "audit_reviewed.json")})
    print({"checks": checks, "geometry_representatives": representatives})
    if not all(checks.values()):
        raise ValueError("review validation failed")


if __name__ == "__main__":
    run()
