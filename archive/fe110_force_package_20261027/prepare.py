"""Assemble already-reviewed force labels into a new local, non-executable package."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

from ase.io import read

from archive.fe110_combined_force_package_20261023 import prepare as owner
from scripts.adsorption.force_finetune import load_manifest, validate_label_row
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/combined_force_package_20261027_v3.json"
PHYSICAL = ("structure_sha256", "symbols", "forces_eV_per_A", "fixed_atom_indices_0based",
            "source_job_id", "local_magnetization_muB", "total_magnetization_muB", "toten_eV_force_label_only")


def scope():
    config = load_json_object(CONFIG)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed " + key)
    for key in ("prior_assembly", "audit_inventory", "audit_summary", "supplement_review", "supplement_verification"):
        if not source_file_manifest_valid(load_json_object(paths[key])):
            raise ValueError("source evidence binding changed " + key)
    return config, paths, ROOT / config["output"]


def verify_proof(path):
    proof = load_json_object(path)
    if (proof["geometry_conflicts"] or proof["quarantined_sample_ids"] or proof["threshold_A"] != .20
            or proof["reserved_geometries"] != 513 or proof["reserved_forces_or_energies_used"] is not False):
        raise ValueError("isolation evidence changed " + str(path))
    return proof


def additional_statics(audit, prior_ids, selected):
    extra = [row for row in audit if row["sample_id"] not in prior_ids]
    result, evidence = [], set()
    for row in extra:
        directory = Path(row["structure_path"]).parent
        source_root = directory.parents[1]
        qc = source_root / "case_qc" / (row["sample_id"] + ".json")
        original = load_json_object(qc)
        if original["partition"] != "train" or original["data_qc_status"] != "PASS":
            raise ValueError("additional static is not an audited training label")
        for key in PHYSICAL:
            if key in original and original[key] != row.get(key):
                raise ValueError("audit differs from original physical label " + key)
        for filename, digest in original["input_output_hashes"].items():
            if sha256_file(directory / filename) != digest:
                raise ValueError("reviewed static source changed " + filename)
        proof_path = source_root / "new_training_isolation.json"
        verify_proof(proof_path)
        binding = source_root / "isolation_binding.json"
        if not binding.exists():
            binding = source_root / "summary.json"
        if not source_file_manifest_valid(load_json_object(binding)):
            raise ValueError("additional static isolation binding stale")
        normalized = owner.static_row(original, selected)
        normalized["source_collection"] = "reviewed_original_statics119_20261025"
        result.append((normalized, directory, None, qc))
        evidence.update((qc, proof_path, binding))
    return result, evidence


def source_rows(config, paths):
    old = load_manifest(paths["prior_manifest"])
    rows = []
    for split, samples in [*old["splits"].items(), ("observed_heldout", old["quarantined_observed_heldout"])]:
        for original in samples:
            row = copy.deepcopy(original)
            row["split"] = split
            rows.append((row, paths["prior_manifest"].parent, original["label_source"], None))
    train_ids = {r["sample_id"] for r in old["splits"]["train"]}
    audit = load_json_object(paths["audit"])["frames"]
    if len(train_ids) != 366 or len(audit) != 485 or not train_ids <= {r["sample_id"] for r in audit}:
        raise ValueError("prior366/audit485 identity mismatch")
    selected = {r["sample_id"]: r for r in load_json_object(paths["frozen_selection"])["selected"]}
    extra, evidence = additional_statics(audit, train_ids, selected)
    if len(extra) != 119:
        raise ValueError("119 additional reviewed statics required")
    if config["base_mode"] != "audited485":
        raise ValueError("this fixed package uses the complete485-frame audited base")
    rows.extend(extra)
    supplement = load_json_object(paths["supplement"])["samples"]
    if len(supplement) != 27:
        raise ValueError("exact27 recommended additions required")
    for original in supplement:
        validate_label_row(paths["supplement"].parent, original)
        if (original["partition"] != "train" or original["data_qc_status"] != "PASS"
                or original["magnetic_review_flags"] or original["magnetic_review_level"] != "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"):
            raise ValueError("supplement admission or magnetic tier changed")
        row = copy.deepcopy(original)
        row.update(stage="targeted_static" if row["origin"] == "new_static" else "targeted_trajectory",
                   source_collection="targeted_statics11_20261026" if row["origin"] == "new_static" else "targeted_trajectory16_20261026")
        rows.append((row, paths["supplement"].parent, original["label_source"], None))
    owner.assert_group_isolation([r[0] for r in rows])
    if len({r[0]["sample_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate sample identity across source collections")
    return old, rows, evidence


def run():
    config, paths, output = scope()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "package_summary.json").exists():
        summary = load_json_object(output / "package_summary.json")
        if not source_file_manifest_valid(load_json_object(output / "assembly_request.json")):
            raise ValueError("completed package source binding changed")
        if sha256_file(output / "training_manifest.json") != summary["manifest_sha256"]:
            raise ValueError("completed manifest changed")
        return summary
    old, sources, evidence = source_rows(config, paths)
    proof_paths = [paths["prior_isolation"], paths["supplement_isolation"],
                   *sorted({p for p in evidence if p.name == "new_training_isolation.json"})]
    proofs = [{"path": str(p), "sha256": sha256_file(p), "proof": verify_proof(p)} for p in proof_paths]
    dependencies = [CONFIG, *paths.values(), *sorted(evidence), Path(__file__),
        Path(__file__).with_name("verify.py"), ROOT / "archive/fe110_combined_force_package_20261023/prepare.py",
        ROOT / "archive/fe110_combined_force_package_20261023/role_helpers.py",
        ROOT / "scripts/adsorption/force_finetune.py", ROOT / "scripts/adsorption/force_role_data.py"]
    owner.save_once(output / "assembly_request.json", {"source_files": source_file_manifest(dependencies),
        "base": "366frozen package+119additional reviewed statics+27recommended frames",
        "training_authorized": False, "new_compute": False})
    # Preserve the source archives referenced inside the old per-row label wrappers.
    for path in sorted((paths["prior_manifest"].parent / "source_archives").glob("*.json")):
        owner.copy_checked(path, output / "source_archives" / path.name, sha256_file(path))
    # Native materializer copies structures and archives exact original source bytes.
    rows = owner.materialize(sources, output, [])
    owner.assert_group_isolation(rows)
    owner.save_once(output / "isolation_review.json", {"method": "reuse hash-bound source isolation proofs;all structure bytes unchanged",
        "proofs": proofs, "geometry_conflicts": [], "quarantined_sample_ids": [], "reserved_geometries": 513,
        "reserved_forces_or_energies_used": False, "new_geometry_comparisons": 0,
        "lineage_checks": "whole-job/family/calculation-group and exact structure-equivalence split guards"})
    splits = {s: [r for r in rows if r["split"] == s] for s in ("train", "development", "heldout")}
    if {s: len(r) for s, r in splits.items()} != config["expected_split_counts"]:
        raise ValueError("expected512/78/53 partition counts")
    owner.set_uniform_sampling(splits["train"])
    manifest = {key: copy.deepcopy(value) for key, value in old.items()
                if key not in {"splits", "quarantined_observed_heldout", "source_files"}}
    manifest.update(splits=splits, quarantined_observed_heldout=[r for r in rows if r["split"] == "observed_heldout"],
        source_files=source_file_manifest(dependencies), prior_manifest_sha256=sha256_file(paths["prior_manifest"]),
        package_version="20261027_v3", training_authorized=False, new_VASP=False, model_promoted=False,
        sampling_policy="uniform_frames_like_existing_control;renormalized over512training rows")
    owner.save_once(output / "training_manifest.json", manifest)
    load_manifest(output / "training_manifest.json")
    if (output / "heldout.db").exists() or (output / "training_request.json").exists():
        raise ValueError("unexpected heldout loader or executable training request")
    receipts = {s: owner.database(s, output, splits[s]) for s in ("train", "development")}
    atoms = {r["sample_id"]: read(output / r["structure_path"], format="vasp") for r in splits["train"]}
    coverage = owner.force_coverage(owner.coverage_groups(splits["train"]), atoms, [0, .05, .10, .50, 1, 2, 5, 10])
    summary = {"status": "LOCAL_FORCE_PACKAGE_PREPARED_NO_TRAINING", "split_counts": {s: len(v) for s, v in splits.items()},
        "old_observed_heldout_quarantined": len(manifest["quarantined_observed_heldout"]),
        "training_source_counts": dict(Counter(r["source_collection"] for r in splits["train"])),
        "magnetic_levels_by_split": {s: dict(Counter(r["magnetic_review_level"] for r in v)) for s, v in splits.items()},
        "training_force_coverage": coverage, "database_receipts": receipts,
        "manifest_sha256": sha256_file(output / "training_manifest.json"),
        "original_package_and_audit_unchanged": True, "new_DFT_GPU_training_or_continuation": False,
        "source_files": source_file_manifest([output / "assembly_request.json", output / "training_manifest.json",
                                             output / "isolation_review.json"])}
    owner.save_once(output / "package_summary.json", summary)
    return summary


if __name__ == "__main__":
    try:
        result = run()
        print({k: result[k] for k in ("status", "split_counts", "training_source_counts")})
    except Exception as exc:
        from datetime import datetime, timezone
        from scripts.artifact_io import write_json_exclusive
        config = load_json_object(CONFIG)
        output = ROOT / config["output"]
        output.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(output / ("failure_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"),
                             {"error": str(exc), "training_started": False})
        raise
