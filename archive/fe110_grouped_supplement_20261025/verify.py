"""Independent geometry and cluster-disposition checks, without calculations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
    write_json_exclusive,
)


def verify(output: Path, native_script: Path):
    summary = load_json_object(output / "summary.json")
    if not source_file_manifest_valid(summary):
        raise ValueError("source binding changed")
    proposals = load_json_object(output / "proposals.json")
    clusters = load_json_object(output / "clusters.json")["clusters"]
    dispositions = load_json_object(output / "all189_dispositions.json")["types"]
    pairs = {tuple(sorted((r["a"], r["b"]))): r["ratio"]
             for r in load_json_object(output / "pair_distances.json")["pairs"]}
    if len(dispositions) != 189 or len({(r["composition"], r["joint_signature"])
                                       for r in dispositions}) != 189:
        raise ValueError("invalid disposition count")
    for cluster in clusters:
        members = cluster["member_type_representatives"]
        values = [pairs[tuple(sorted((a, b)))] for a in members for b in members if a != b]
        if max(values, default=0) > 1 + 1e-12:
            raise ValueError("complete-link diameter failed")
    if proposals["execution_authorized"] or summary["new_DFT_GPU_training_submission"]:
        raise ValueError("proposal gained execution authority")
    audit_dir = output / "native_geometry_audits"
    audit_dir.mkdir()
    for row in load_json_object(output / "geometry.json")["candidates"]:
        if sha256_file(Path(row["structure_path"])) != row["structure_sha256"]:
            raise ValueError("candidate geometry changed")
        process = subprocess.run([sys.executable, "-X", "utf8", str(native_script),
            row["structure_path"]], capture_output=True, text=True, encoding="utf-8", check=False)
        native = json.loads(process.stdout)
        write_json_exclusive(audit_dir / (row["sample_id"] + ".json"), native)
        if process.returncode or native["verdict"] != "pass" or native["fixed_atoms"] != 18:
            raise ValueError("native geometry failed: " + row["sample_id"])
        for element, key in (("C", "c_fe_distance"), ("O", "o_fe_distance")):
            nearest = [x for x in row["nearest_Fe_by_C_O"] if x["element"] == element]
            if nearest and abs(min(x["distance_A"] for x in nearest) -
                               native[key]["distance_A"]) > 5.1e-5:
                raise ValueError("independent Fe distance mismatch")
        if abs(native["nearest_contact"]["distance_A"] - row["minimum_contact_A"]) > 5.1e-5:
            raise ValueError("independent contact mismatch")
        if row["minimum_C_O_A"] is not None and abs(
                native["co_distance"]["distance_A"] - row["minimum_C_O_A"]) > 5.1e-5:
            raise ValueError("independent CO distance mismatch")
    if load_json_object(output / "isolation.json")["geometry_conflicts"]:
        raise ValueError("isolation conflict")
    result = {"status": "PASS", "all189_unique_dispositions": True,
        "clusters_complete_link_rechecked": len(clusters),
        "independent_native_geometries": len(list(audit_dir.glob("*.json"))),
        "geometry_is_label_or_stability_acceptance": False,
        "source_files": source_file_manifest([Path(__file__), native_script,
            native_script.with_name("poscar_utils.py"),
            *sorted(output.glob("*.json")), *sorted(audit_dir.glob("*.json"))])}
    write_json_exclusive(output / "verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-script", type=Path, required=True)
    args = parser.parse_args()
    verify(args.output.resolve(), args.native_script.resolve())
