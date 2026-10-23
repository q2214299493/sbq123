"""QC newly collected fixed-geometry labels without altering frozen datasets."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from ase.io import read

from archive.fe110_reico_label_qc_20261023.review import scheduler_evidence
from scripts.adsorption.collect_completed_batch import FILES
from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, source_file_manifest
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.vasp_result_gate import final_scf_status
from .collect import CONFIG, ROOT, check_snapshot, save_once, scope


def review_case(source, receipt, directory, binding):
    hashes = {name: sha256_file(directory/name) for name in FILES}
    if any(hashes[n] != receipt["remote"]["files"][n]["sha256"] for n in FILES):
        raise ValueError("collection source file changed")
    if hashes["POSCAR"] != source["structure_sha256"]:
        raise ValueError("static geometry differs from original selection")
    result = {k:source[k] for k in ("sample_id", "family_id", "partition", "composition", "structure_sha256")}
    result.update(source_job_id=receipt["job_id"], structure_path=str((directory/"POSCAR").resolve()),
                  input_output_hashes=hashes, review_binding_sha256=binding,
                  category="NEW_COMPLETED_STATIC_20261024", reportable_final_energy=False,
                  training_authorized=False, accepted_endpoint=False)
    try:
        label = validate_static(directory, read(directory/"POSCAR", format="vasp").get_chemical_symbols())
        flags = [] if label["Fe_positive_moment_count"] == 45 else ["NONPOSITIVE_FE_LOCAL_MOMENT_REQUIRES_BRANCH_REVIEW"]
        result.update(**label, magnetic_review_flags=flags,
                      data_qc_status="MAGNETIC_REVIEW_REQUIRED" if flags else "PASS",
                      magnetic_review_level="LOCAL_MOMENTS_REVIEWED_POSITIVE_FE" if not flags else "NEEDS_MAGNETIC_REVIEW")
    except ValueError as error:
        result.update(data_qc_status="REJECTED_OR_INCOMPLETE", reason=str(error),
                      SCF_diagnostic=final_scf_status(directory/"OSZICAR", directory/"INCAR", directory/"OUTCAR"))
    return result


def run(smoke=False):
    config, paths, _, requested = scope()
    output = ROOT/config["output"]
    snapshot = check_snapshot(load_json_object(output/"scheduler_snapshot.json"))
    collection = load_json_object(output/("collection_smoke.json" if smoke else "collection_summary.json"))
    selected = {r["sample_id"]:r for r in load_json_object(paths["selection"])["selected"]}
    jobs = {r["name"]:r for r in snapshot["jobs"]}
    expected = {r["name"]:r for r in requested}
    sources = source_file_manifest([CONFIG, *paths.values(), output/"scheduler_snapshot.json", Path(__file__),
        ROOT/"scripts/adsorption/reico_probe_review.py", ROOT/"scripts/aqcat25_calibration.py",
        ROOT/"scripts/neb_agent/utils_vasp.py", ROOT/"scripts/vasp_result_gate.py"])
    binding = sha256_json(sources)
    rows, receipts = [], []
    for item in collection["collected"]:
        sid = item["sample_id"]
        evidence = scheduler_evidence(snapshot, {**jobs[sid], "sample_id":sid})
        validate_stored_lsf_evidence(evidence, required_status="DONE")
        directory = output/"collection"/sid
        receipt_path = directory/"collection.json"
        if sha256_file(receipt_path) != item["receipt_sha256"]:
            raise ValueError("collection receipt changed")
        receipt = load_json_object(receipt_path)
        if receipt["submission"] != expected[sid] or item["job_id"] != jobs[sid]["job_id"]:
            raise ValueError("collection differs from exact submitted job")
        row = review_case(selected[sid], receipt, directory, binding)
        save_once(output/"case_qc"/(sid+".json"), row)
        rows.append(row)
        receipts.extend([receipt_path, *[directory/n for n in FILES]])
    suffix = "smoke" if smoke else "new_label_qc_local_only"
    save_once(output/(suffix+".json"), {"samples":rows, "source_files":sources+source_file_manifest(receipts)})
    result = {"status":"LABEL_QC_COMPLETE" if not collection["failures"] else "PARTIAL_COLLECTION_QC",
              "reviewed":len(rows), "qc_counts":dict(Counter(r["data_qc_status"] for r in rows)),
              "partition_counts":dict(Counter(r["partition"] for r in rows)),
              "training_pass":sum(r["partition"] == "train" and r["data_qc_status"] == "PASS" for r in rows),
              "magnetic_ground_state_verified":False, "new_DFT_or_model_execution":False,
              "source_files":sources+source_file_manifest([output/(suffix+".json")])}
    save_once(output/("qc_smoke_summary.json" if smoke else "qc_summary.json"), result)
    print(json.dumps({k:v for k,v in result.items() if k != "source_files"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.smoke)
