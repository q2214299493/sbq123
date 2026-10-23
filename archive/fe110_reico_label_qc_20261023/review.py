"""Review existing static labels and training forces; no submissions or models."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml
from ase.io import read

from archive.fe110_reico_label_qc_20261023.collect import OUTPUT
from archive.fe110_reico_sampling93_20261022.submit import DEST
from scripts.adsorption.force_finetune import local_path, validate_label_row
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.adsorption.reico_force_coverage import force_coverage, nearby_force_pairs
from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import (
    load_json_object, sha256_file, sha256_json, source_file_manifest,
    source_file_manifest_valid, write_json,
)
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.vasp_result_gate import final_scf_status

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/force_qc_v1.json"
FILES = ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR", "KPOINTS")


def scheduler_evidence(snapshot: dict, job: dict) -> dict:
    return {"schema_version":1,"document_kind":"scheduler_job_evidence","stage":"vasp_force_label",
            "scheduler":"LSF","server_alias":"sunboquan-codex","job_id":job["job_id"],
            "status":job["status"],"checked_at":snapshot["checked_at"],"source_command":" ".join(snapshot["command"]),
            "query":{"argv":snapshot["command"],"returncode":snapshot["returncode"],"stdout":snapshot["stdout"],
                     "stderr":snapshot["stderr"],"stdout_sha256":snapshot["stdout_sha256"]}}


def review_case(source: dict, directory: Path, category: str, binding: str, job_id: str) -> dict:
    hashes = {n:sha256_file(directory/n) for n in FILES}
    path = OUTPUT / "case_qc" / (source["sample_id"]+".json")
    if path.exists():
        saved = load_json_object(path)
        if saved["input_output_hashes"] != hashes or saved["review_binding_sha256"] != binding or saved["source_job_id"] != job_id:
            raise ValueError("existing QC belongs to changed inputs or review code")
        return saved
    structure = read(directory/"POSCAR",format="vasp")
    if hashes["POSCAR"] != source["structure_sha256"]:
        raise ValueError("label geometry differs from frozen selected frame")
    result = {k:source[k] for k in ("sample_id","family_id","partition","composition","structure_sha256")}
    result.update(category=category,source_job_id=job_id,structure_path=str((directory/"POSCAR").resolve()),
                  input_output_hashes=hashes,review_binding_sha256=binding,
                  reportable_final_energy=False,training_authorized=False)
    try:
        label = validate_static(directory,structure.get_chemical_symbols())
        flags = [] if label["Fe_positive_moment_count"] == 45 else ["NONPOSITIVE_FE_LOCAL_MOMENT_REQUIRES_BRANCH_REVIEW"]
        result.update(**label,magnetic_review_flags=flags,
                      data_qc_status="MAGNETIC_REVIEW_REQUIRED" if flags else "PASS")
    except ValueError as error:
        result.update(data_qc_status="REJECTED_OR_INCOMPLETE",reason=str(error),
                      SCF_diagnostic=final_scf_status(directory/"OSZICAR",directory/"INCAR",directory/"OUTCAR"))
    write_json(path,result)
    return result


def review_new(selected: dict, binding: str) -> list:
    snapshot = load_json_object(OUTPUT/"scheduler_snapshot.json")
    collection = load_json_object(OUTPUT/"collection_summary.json")
    jobs = {r["sample_id"]:r for r in snapshot["jobs"]}
    result = []
    for item in collection["collected"]:
        name = item["sample_id"]
        evidence = scheduler_evidence(snapshot,jobs[name])
        validate_stored_lsf_evidence(evidence,required_status="DONE")
        directory = OUTPUT/"collection"/name
        receipt_path = directory/"collection.json"
        if sha256_file(receipt_path) != item["receipt_sha256"]:
            raise ValueError("collection receipt changed")
        receipt = load_json_object(receipt_path)
        for filename in FILES:
            if sha256_file(directory/filename) != receipt["remote"]["files"][filename]["sha256"]:
                raise ValueError("collected file no longer matches remote hash")
        expected = load_json_object(DEST/name/"label_request.json")
        for filename in ("INCAR","POSCAR","KPOINTS"):
            if sha256_file(directory/filename) != sha256_file(DEST/name/filename):
                raise ValueError("remote input differs from original prepared input")
        if expected["sample_id"] != name or receipt["job_id"] != jobs[name]["job_id"]:
            raise ValueError("label/job identity mismatch")
        row = review_case(selected[name],directory,"NEW_COMPLETED_STATIC",binding,jobs[name]["job_id"])
        result.append(row)
        if len(result)%20 == 0:
            print(f"QC {len(result)}/{len(collection['collected'])}",flush=True)
    return result


def review_existing12(selected: dict, binding: str) -> list:
    by_sha = {r["structure_sha256"]:r for r in selected.values()}
    probe = ROOT/"calculations/fe110_reico_pilot300_20261022/probe6_v1/checks/20261022T084625Z"
    second = ROOT/"calculations/fe110_reico_pilot300_20261022/sampling6_v1/dft_review6_v1/checks/20261022T143902Z"
    result = []
    metadata = json.loads((probe/"remote_metadata.stdout.json").read_bytes())
    probe_jobs = {r["sample_id"]:r["source_job_id"] for r in load_json_object(probe/"dataset_review.json")["samples"]}
    for item in metadata:
        directory = probe/"vasp"/item["sample_id"]
        for name,info in item["files"].items():
            if sha256_file(directory/name) != info["sha256"]:
                raise ValueError("original six-probe collection changed")
        source = by_sha[sha256_file(directory/"POSCAR")]
        result.append(review_case(source,directory,"REUSED_ORIGINAL_12",binding,probe_jobs[item["sample_id"]]))
    for item in load_json_object(second/"collection_manifest.json")["records"]:
        directory = second/"vasp"/item["sample_id"]
        for name,info in item["files"].items():
            if sha256_file(directory/name) != info["sha256"]:
                raise ValueError("original six sampled-static collection changed")
        source = by_sha[sha256_file(directory/"POSCAR")]
        result.append(review_case(source,directory,"REUSED_ORIGINAL_12",binding,item["job_id"]))
    if len(result) != 12 or len({r["sample_id"] for r in result}) != 12:
        raise ValueError("expected exactly twelve distinct reused labels")
    return result


def legacy_coverage(config: dict) -> tuple[dict,dict]:
    audit = ROOT/"calculations/fe110_reico_pilot300_20261022/coverage_audit_v1/audit_summary.json"
    old = load_json_object(audit)
    if not source_file_manifest_valid(old):
        raise ValueError("old training audit binding is stale")
    path = ROOT/old["config"]["prior_manifest"]
    manifest = load_json_object(path)
    rows,atoms,failures = [],{},[]
    for row in manifest["splits"]["train"]:
        try:
            validate_label_row(path.parent,row)
        except ValueError as error:
            failures.append({"sample_id":row["sample_id"],"error":str(error)})
            continue
        structure = read(local_path(path.parent,row["structure_path"]),format="vasp")
        name = "legacy::"+row["sample_id"]
        rows.append({"sample_id":name,"family_id":row["calculation_group"],"partition":"train",
                     "composition":structure[45:].get_chemical_formula(),"forces_eV_per_A":row["forces_eV_per_A"]})
        atoms[name] = structure
    return force_coverage(rows,atoms,config["force_bin_lower_edges_eV_A"]), {
        "training_rows_checked":len(manifest["splits"]["train"]),"binding_passed":len(rows),"failures":failures,
        "scope":"Canonical label/source/force binding recheck only;old raw SCF/local moments not all reparsed",
        "manifest_sha256":sha256_file(path)}


def main():
    if (OUTPUT/"review_summary.json").exists():
        raise ValueError("completed QC exists;choose a new checkpoint")
    config = load_json_object(CONFIG)
    selection_path = ROOT/"calculations/fe110_reico_pilot300_20261022/sampling93_v1/selection/selected_frames.json"
    selected = {r["sample_id"]:r for r in load_json_object(selection_path)["selected"]}
    sources = source_file_manifest([CONFIG,selection_path,OUTPUT/"scheduler_snapshot.json",Path(__file__),
                                   ROOT/"scripts/adsorption/reico_probe_review.py",ROOT/"scripts/neb_agent/utils_vasp.py",
                                   ROOT/"scripts/vasp_result_gate.py",ROOT/"scripts/aqcat25_calibration.py",
                                   ROOT/"scripts/adsorption/reico_force_coverage.py",
                                   ROOT/"scripts/adsorption/reico_chemical_environments.py",
                                   ROOT/"configs/adsmind_lite/analysis_rules.yaml"])
    binding = sha256_json(sources)
    rows = review_new(selected,binding)+review_existing12(selected,binding)
    write_json(OUTPUT/"all_label_qc_local_only.json",{"samples":rows,"source_files":sources})
    admitted = [r for r in rows if r["partition"] == "train" and r["data_qc_status"] == "PASS"]
    atoms = {r["sample_id"]:read(r["structure_path"],format="vasp") for r in admitted}
    for value in atoms.values():
        value.pbc=[True,True,False]
    analysis = yaml.safe_load((ROOT/"configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))["connectivity"]
    geometry = {name:chemical_environment(value,analysis) for name,value in atoms.items()}
    coverage = force_coverage(admitted,atoms,config["force_bin_lower_edges_eV_A"])
    pairs = nearby_force_pairs(admitted,atoms,geometry,config["near_pair_maximum_vector_RMSD_A"])
    legacy,legacy_review = legacy_coverage(config)
    write_json(OUTPUT/"training_force_coverage.json",coverage)
    write_json(OUTPUT/"nearby_training_pairs.json",{"pairs":pairs,"force_difference_is_not_label_error":True})
    write_json(OUTPUT/"legacy_training_force_coverage.json",{"coverage":legacy,"review":legacy_review})
    metadata = [{k:r.get(k) for k in ("sample_id","partition","composition","category","data_qc_status","reason","magnetic_review_flags")} for r in rows]
    write_json(OUTPUT/"qc_metadata.json",{"labels":metadata})
    result = {"status":"QC_CHECKPOINT_COMPLETE","source_files":sources,
              "scheduler_counts":load_json_object(OUTPUT/"scheduler_snapshot.json")["status_counts"],
              "labels_reviewed":len(rows),"new_labels_reviewed":sum(r["category"]=="NEW_COMPLETED_STATIC" for r in rows),
              "qc_counts":dict(Counter(r["data_qc_status"] for r in rows)),
              "qc_counts_by_partition":{p:dict(Counter(r["data_qc_status"] for r in rows if r["partition"]==p)) for p in ("train","development","final_test")},
              "training_labels_analyzed":len(admitted),"training_force_coverage":coverage,
              "near_pair_count":len(pairs),"near_pair_below_original_0p10A":sum(r["geometry_RMSD_A"]<.1 for r in pairs),
              "largest_training_pair_differences":pairs[:10],"legacy_review":legacy_review,
              "reserved_labels_used_for_adaptive_coverage_or_pair_analysis":False,
              "magnetic_ground_state_verified":False,"training_or_new_DFT_executed":False,
              "missing_geometry_frames_obtain_new_force_labels":False}
    write_json(OUTPUT/"review_summary.json",result)
    print(json.dumps({k:result[k] for k in ("status","labels_reviewed","qc_counts","training_labels_analyzed","near_pair_count")}))


if __name__ == "__main__":
    main()
