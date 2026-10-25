"""Verify source identity and replay the independent geometry parser;no DFT actions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from archive.fe110_reico_followup_20261024.collect import save_once
from .analyze import ROOT, geometry, pick_labelled, scope


def verify(evidence_root=ROOT, receipt_name="verification.json"):
    import yaml

    config_path, config, paths = scope(evidence_root)
    output = evidence_root / config["output"]
    result = load_json_object(output / "shortlist_local_only.json")
    assert source_file_manifest_valid(result)
    assert source_file_manifest_valid(load_json_object(output / "input_binding.json"))
    candidates = result["candidates"]
    assert len(candidates) == len({r["sample_id"] for r in candidates}) == 5
    isolation = load_json_object(output / "candidate_isolation.json")
    assert not isolation["geometry_conflicts"] and not isolation["quarantined_sample_ids"]
    assert isolation["threshold_A"] == .20 and isolation["reserved_geometries"] == 513
    assert not isolation["reserved_forces_or_energies_used"]
    assert set(result["geometry_isolation_passed_ids"]) == {r["sample_id"] for r in candidates}
    rules = yaml.safe_load(paths["rules"].read_text(encoding="utf-8"))["connectivity"]
    training = load_json_object(paths["training"])["frames"]
    by_id = {r["sample_id"]: r for r in training}
    detail = load_json_object(output / "geometry_details.json")["candidates"]
    script = Path.home() / ".codex/skills/surface-adsorption-builder/scripts/audit_poscar_geometry.py"
    replayed = []
    for row in candidates:
        sid = row["sample_id"]
        assert geometry(row, rules) == detail[sid]
        raw = subprocess.run([sys.executable, str(script), row["structure_path"]],
            capture_output=True, text=True, timeout=30, check=False)
        assert raw.returncode == 0
        independent = json.loads(raw.stdout)
        cached = load_json_object(output / "native_geometry_audits" / (sid + ".json"))
        assert sha256_file(Path(cached["path"])) == sha256_file(Path(independent["path"])) == row["structure_sha256"]
        assert {k: v for k, v in independent.items() if k != "path"} == {k: v for k, v in cached.items() if k != "path"}
        for element, key in (("C", "c_fe_distance"), ("O", "o_fe_distance")):
            contacts = [r["distance_A"] for r in detail[sid]["nearest_Fe_by_C_O"] if r["element"] == element]
            if contacts:
                assert abs(min(contacts) - independent[key]["distance_A"]) <= 5.1e-5
        if row["existing_label_in_training"]:
            source = by_id[sid]
            assert source["magnetic_review_level"] == row["source_magnetic_review_level"]
            assert source["movable_fmax_eV_A"] == row["existing_movable_fmax_eV_A"] > .05
            excluded_group = (by_id[config["C2_low_force_anchor"]]["source_group"]
                              if row["composition"] == "C2H3" else None)
            chosen = pick_labelled(training, row["composition"], source["graph_signature"], excluded_group)
            assert chosen["sample_id"] == sid
        assert not row["is_confirmed_low_force_candidate"] and not row["new_DFT_authorized"]
        replayed.append(sid)
    magnetic = load_json_object(paths["magnetic_case"])
    mag = next(r for r in candidates if r["purpose"] == "EXISTING_MAGNETIC_LABEL_REVIEW")
    assert mag["source_data_qc_status"] == magnetic["data_qc_status"] == "MAGNETIC_REVIEW_REQUIRED"
    assert mag["source_magnetic_review_level"] == "NEEDS_MAGNETIC_REVIEW"
    assert not result["new_DFT_started"] and not result["training_started"] and not result["paused_sources_resumed"]
    tests = {}
    for name in ("primary_tests.xml", "publication_tests.xml"):
        xml = ET.parse(output / name).getroot()
        assert not list(xml.iter("failure")) and not list(xml.iter("error")) and not list(xml.iter("skipped"))
        tests[name] = len(list(xml.iter("testcase")))
    record = {"status": "PASS", "candidate_geometry_replays": replayed, "isolation_comparisons": isolation["comparisons"],
        "magnetic_grades_preserved": True, "new_labels_created": 0, "tests": tests, "source_checkout": str(ROOT),
        "source_files": source_file_manifest([Path(__file__), config_path, script, script.with_name("poscar_utils.py"),
            output / "shortlist_local_only.json", output / "input_binding.json", output / "geometry_details.json",
            output / "primary_tests.xml", output / "publication_tests.xml"])}
    save_once(output / receipt_name, record)
    print({k: v for k, v in record.items() if k != "source_files"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT)
    parser.add_argument("--receipt", default="verification.json")
    args = parser.parse_args()
    verify(args.evidence_root, args.receipt)
