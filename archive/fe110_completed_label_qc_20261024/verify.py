"""Verify exact source inventories and admission boundaries without repeating DFT."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.adsorption.collect_completed_batch import FILES
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from .run import CONFIG, ROOT, save_once, scope


def verify():
    config, paths, selected, previous, _ = scope()
    output = ROOT / config["output"]
    summary = load_json_object(output / "batch_processing_summary.json")
    new = load_json_object(output / "new_label_qc_local_only.json")["samples"]
    all_rows = load_json_object(output / "all_selected_label_qc_local_only.json")["samples"]
    eligible = load_json_object(output / "eligible_training_labels_local_only.json")["samples"]
    snapshot = load_json_object(output / "scheduler_snapshot.json")
    expected = {r["name"] for r in snapshot["jobs"] if r["status"] == "DONE"}
    failed = {r["sample_id"] for r in summary["collection_failures"]}
    if ({r["sample_id"] for r in new} | failed) != expected:
        raise ValueError("not every frozen DONE job has QC or an explicit failure record")
    if len(all_rows) != len(previous) + len(new) or len({r["sample_id"] for r in all_rows}) != len(all_rows):
        raise ValueError("cumulative label loss or duplication")
    selection = {r["sample_id"]: r for r in selected}
    batch = {r["sample_id"]: r for r in load_json_object(paths["batch"])["samples"]}
    hashes_checked = 0
    for row in new:
        if any(row[key] != selection[row["sample_id"]][key] for key in ("family_id", "partition", "composition", "structure_sha256")):
            raise ValueError("original family, partition or geometry changed")
        directory = Path(row["structure_path"]).parent
        receipt = load_json_object(directory / "collection.json")
        for name in FILES:
            if sha256_file(directory / name) != row["input_output_hashes"][name] or row["input_output_hashes"][name] != receipt["remote"]["files"][name]["sha256"]:
                raise ValueError("raw local/remote evidence hash mismatch")
            hashes_checked += 1
        for name in ("INCAR", "POSCAR", "KPOINTS"):
            if row["input_output_hashes"][name] != batch[row["sample_id"]]["input_hashes"][name]:
                raise ValueError("immutable original input mismatch")
    safe_ids = {r["sample_id"] for r in new if r["partition"] == "train" and r["data_qc_status"] == "PASS"}
    if not {r["sample_id"] for r in eligible} <= safe_ids:
        raise ValueError("reserved or unreviewed magnetic label admitted")
    if not source_file_manifest_valid(load_json_object(output / "isolation_binding.json")):
        raise ValueError("isolation source binding changed")
    if sha256_file(paths["frozen_manifest"]) != config["inputs"]["frozen_manifest"]["sha256"]:
        raise ValueError("frozen366 training manifest changed")
    tests = {}
    for label, filename in (("primary", "primary_tests_final.xml"), ("publication", "release_tests_final.xml")):
        root = ET.parse(output / filename).getroot()
        if list(root.iter("failure")) or list(root.iter("error")):
            raise ValueError("related tests failed")
        tests[label] = len(list(root.iter("testcase")))
    result = {"status": "PASS", "new_labels": len(new), "local_remote_raw_hashes_checked": hashes_checked,
        "immutable_input_hashes_checked": 3 * len(new), "isolated_training_eligible": len(eligible),
        "new_QC_counts": dict(Counter(r["data_qc_status"] for r in new)), "test_pass_counts": tests,
        "frozen366_training_manifest_unchanged": True, "reserved_partition_admission": 0,
        "source_files": source_file_manifest([CONFIG, Path(__file__), output / "batch_processing_summary.json",
            output / "new_label_qc_local_only.json", output / "all_selected_label_qc_local_only.json",
            output / "eligible_training_labels_local_only.json", output / "isolation_binding.json",
            output / "primary_tests_final.xml", output / "release_tests_final.xml"])}
    save_once(output / "verification.json", result)
    print({key: value for key, value in result.items() if key != "source_files"})


if __name__ == "__main__":
    verify()
