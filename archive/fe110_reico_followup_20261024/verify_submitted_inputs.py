"""Bind collected inputs to the original immutable 280-input batch, not only copies."""
from __future__ import annotations

from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest
from .collect import ROOT, save_once, scope


def verify():
    config, paths, _, _ = scope()
    output = ROOT/config["output"]
    checkpoint = load_json_object(paths["checkpoint"])
    batch_path = paths["checkpoint"].parent/"batch_request.json"
    if sha256_file(batch_path) != checkpoint["batch_sha256"]:
        raise ValueError("original frozen batch changed")
    expected = {r["sample_id"]:r for r in load_json_object(batch_path)["samples"]}
    labels = load_json_object(output/"new_label_qc_local_only.json")["samples"]
    for row in labels:
        directory = Path(row["structure_path"]).parent
        receipt = load_json_object(directory/"collection.json")
        for name in ("INCAR", "POSCAR", "KPOINTS"):
            digest = expected[row["sample_id"]]["input_hashes"][name]
            if sha256_file(directory/name) != digest or receipt["remote"]["files"][name]["sha256"] != digest:
                raise ValueError("collected input differs from immutable submitted batch")
    result = {"status":"PASS", "labels":len(labels), "immutable_input_hashes_checked":3*len(labels),
              "batch_sha256":sha256_file(batch_path), "source_files":source_file_manifest([
                  Path(__file__), paths["checkpoint"], batch_path, output/"new_label_qc_local_only.json"])}
    save_once(output/"immutable_input_verification.json", result)
    print({k:v for k,v in result.items() if k != "source_files"})


if __name__ == "__main__":
    verify()
