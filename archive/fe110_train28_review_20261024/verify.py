"""Replay native QC and verify immutable evidence for a configured incremental checkpoint."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

from archive.fe110_reico_followup_20261024.collect import check_snapshot
from scripts.adsorption.collect_completed_batch import FILES
from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, source_file_manifest, source_file_manifest_valid
from .run import DEFAULT_CONFIG, ROOT, save_once


def verify(evidence_root=ROOT, receipt_name="verification.json", config_path=DEFAULT_CONFIG):
    config_path = evidence_root / config_path.relative_to(ROOT)
    config = load_json_object(config_path)
    paths = {k: evidence_root / item["path"] for k, item in config["inputs"].items()}
    for key, path in paths.items():
        assert sha256_file(path) == config["inputs"][key]["sha256"]
    output = evidence_root / config["output"]
    summary = load_json_object(output / "summary.json")
    assert source_file_manifest_valid(summary)
    current = check_snapshot(load_json_object(output / "scheduler_snapshot.json"))
    previous = load_json_object(paths["previous_labels"])["samples"]
    previous_ids = {r["sample_id"] for r in previous}
    requested = set(load_json_object(paths["conditional"])["unreviewed_selected_ids"]) - previous_ids
    assert len(requested) == config["expected_remaining"] and {r["name"] for r in current["jobs"]} == requested
    done = {r["name"] for r in current["jobs"] if r["status"] == "DONE"}
    labels = load_json_object(output / "new_label_qc_local_only.json")["samples"]
    reviewed_ids = {r["sample_id"] for r in labels}
    assert len(reviewed_ids) == len(labels) and not reviewed_ids & previous_ids
    assert reviewed_ids | {r["sample_id"] for r in summary["collection_failures"]} == done
    original = {r["sample_id"]: r for r in load_json_object(paths["batch"])["samples"]}
    binding = load_json_object(output / "main_collection_binding.json")
    assert source_file_manifest_valid(binding)
    assert source_file_manifest_valid(load_json_object(output / "scope_binding.json"))
    replays, raw_hashes = 0, 0
    for row in labels:
        assert row["partition"] == "train" and row["sample_id"] in requested
        assert row["review_binding_sha256"] == sha256_json(binding)
        directory = Path(row["structure_path"]).parent
        collection = load_json_object(directory / "collection.json")
        assert row["source_job_id"] == collection["job_id"]
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
            assert replay["Fe_positive_moment_count"] == 45
            assert row["magnetic_review_level"] == "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"
            replays += 1
    cumulative = load_json_object(output / "all_selected_label_qc_local_only.json")["samples"]
    assert cumulative == previous + labels and len({r["sample_id"] for r in cumulative}) == len(cumulative)
    assert Counter(r["data_qc_status"] for r in cumulative) == summary["all_selected_qc_counts"]
    eligible = load_json_object(output / "eligible_training_labels_local_only.json")["samples"]
    eligible_ids = {r["sample_id"] for r in eligible}
    assert all(r["partition"] == "train" and r["data_qc_status"] == "PASS" for r in eligible)
    groups = [g for g in load_json_object(paths["gaps"])["groups"] if g["unreviewed_selected_input_ids"]]
    prior_eligible = [r for key in ("previous_eligible16", "previous_eligible1")
                      for r in load_json_object(paths[key])["samples"]]
    prior_ids = {r["sample_id"] for r in prior_eligible}
    prior_covered = [g for g in groups if set(g["unreviewed_selected_input_ids"]) & prior_ids]
    covered = [g for g in groups if set(g["unreviewed_selected_input_ids"]) & eligible_ids
               and not set(g["unreviewed_selected_input_ids"]) & prior_ids]
    assert len(groups) == 40 and len(covered) == summary["additional_gap_groups"]
    assert summary["covered_of_original40_gap_groups"] == len(prior_covered) + len(covered)
    assert summary["joint_gaps_if_new_candidates_admitted"] == 229 - len(prior_covered) - len(covered)
    by_id = {r["sample_id"]: r for r in labels}
    for row in eligible:
        original_row = by_id[row["sample_id"]]
        assert {key: row[key] for key in original_row} == original_row
    assert source_file_manifest_valid(load_json_object(output / "isolation_binding.json"))
    tests = {}
    for name in ("primary_tests.xml", "publication_tests.xml"):
        doc = ET.parse(output / name).getroot()
        assert not list(doc.iter("failure")) and not list(doc.iter("error"))
        tests[name] = len(list(doc.iter("testcase")))
    result = {"status": "PASS", "new_label_replays": replays, "raw_local_remote_hashes": raw_hashes,
        "immutable_input_hashes": len(labels) * 3, "isolated_train_labels": len(eligible),
        "additional_gap_types_covered": len(covered), "original_reviewed_labels_unchanged": len(previous),
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
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    verify(args.evidence_root, args.receipt, args.config)
