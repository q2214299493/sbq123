"""Verify exact45 scope, raw label replays and gap contribution using local evidence."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.adsorption.collect_completed_batch import FILES
from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, source_file_manifest, source_file_manifest_valid
from .inspect import CONFIG, ROOT, save_once


def verify(evidence_root=ROOT, receipt_name="verification.json"):
    config_path = evidence_root / CONFIG.relative_to(ROOT)
    config = load_json_object(config_path)
    paths = {k: evidence_root / item["path"] for k, item in config["inputs"].items()}
    for key, path in paths.items():
        assert sha256_file(path) == config["inputs"][key]["sha256"]
    output = evidence_root / config["output"]
    summary = load_json_object(output / "summary.json")
    assert source_file_manifest_valid(summary)
    snapshot = load_json_object(output / "scheduler_snapshot.json")
    requested = set(load_json_object(paths["conditional"])["unreviewed_selected_ids"])
    assert len(requested) == 45 and {r["name"] for r in snapshot["jobs"]} == requested
    done = {r["name"] for r in snapshot["jobs"] if r["status"] == "DONE"}
    labels = load_json_object(output / "new_label_qc_local_only.json")["samples"]
    assert {r["sample_id"] for r in labels} | {r["sample_id"] for r in summary["collection_failures"]} == done
    original = {r["sample_id"]: r for r in load_json_object(paths["batch"])["samples"]}
    smoke_ids = {r["sample_id"] for r in load_json_object(output / "smoke_labels_local_only.json")["samples"]}
    smoke_binding = load_json_object(output / "collection_binding.json")
    main_binding = load_json_object(output / "main_collection_binding.json")
    assert source_file_manifest_valid(smoke_binding) and source_file_manifest_valid(main_binding)
    raw_hashes = 0
    for row in labels:
        assert row["partition"] == "train" and row["sample_id"] in requested
        binding = smoke_binding if row["sample_id"] in smoke_ids else main_binding
        assert row["review_binding_sha256"] == sha256_json(binding)
        directory = Path(row["structure_path"]).parent
        collection = load_json_object(directory / "collection.json")
        for name in FILES:
            digest = sha256_file(directory / name)
            assert digest == row["input_output_hashes"][name] == collection["remote"]["files"][name]["sha256"]
            raw_hashes += 1
        for name in ("INCAR", "POSCAR", "KPOINTS"):
            assert row["input_output_hashes"][name] == original[row["sample_id"]]["input_hashes"][name]
        if row["data_qc_status"] == "PASS":
            replay = validate_static(directory, row["symbols"])
            for key in ("forces_eV_per_A", "SCF", "local_magnetization_muB", "total_magnetization_muB", "toten_eV_force_label_only"):
                assert row[key] == replay[key]
    previous = load_json_object(paths["previous_labels"])["samples"]
    cumulative = load_json_object(output / "all_selected_label_qc_local_only.json")["samples"]
    assert cumulative[:len(previous)] == previous and len(cumulative) == len(previous) + len(labels)
    assert len({r["sample_id"] for r in cumulative}) == len(cumulative)
    assert Counter(r["data_qc_status"] for r in cumulative) == summary["all_selected_qc_counts"]
    eligible = load_json_object(output / "eligible_training_labels_local_only.json")["samples"]
    eligible_ids = {r["sample_id"] for r in eligible}
    assert all(r["partition"] == "train" and r["data_qc_status"] == "PASS" for r in eligible)
    groups = [g for g in load_json_object(paths["gaps"])["groups"] if g["unreviewed_selected_input_ids"]]
    covered = [g for g in groups if set(g["unreviewed_selected_input_ids"]) & eligible_ids]
    assert len(groups) == 40 and len(covered) == summary["covered_of_original40_gap_groups"]
    assert summary["joint_gaps_if_new_candidates_admitted"] == 229 - len(covered)
    assert source_file_manifest_valid(load_json_object(output / "isolation_binding.json"))
    tests = {}
    for name in ("primary_tests_main.xml", "publication_tests.xml"):
        doc = ET.parse(output / name).getroot()
        assert not list(doc.iter("failure")) and not list(doc.iter("error"))
        tests[name] = len(list(doc.iter("testcase")))
    result = {"status": "PASS", "new_label_replays": len(labels), "raw_local_remote_hashes": raw_hashes,
        "immutable_input_hashes": len(labels) * 3, "isolated_train_labels": len(eligible),
        "gap_types_covered_by_candidates": len(covered), "original240labels_unchanged": True,
        "original366package_and440audit_unchanged": True, "test_pass_counts": tests,
        "source_checkout": str(ROOT), "source_files": source_file_manifest([Path(__file__), config_path,
            output / "summary.json", output / "new_label_qc_local_only.json", output / "all_selected_label_qc_local_only.json",
            paths["frozen_manifest"], paths["previous_audit"]])}
    save_once(output / receipt_name, result)
    print({k: v for k, v in result.items() if k != "source_files"})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT)
    parser.add_argument("--receipt", default="verification.json")
    args = parser.parse_args()
    verify(args.evidence_root, args.receipt)
