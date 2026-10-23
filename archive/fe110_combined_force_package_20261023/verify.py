"""Independent source/database integrity checks; no model or heldout evaluation."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from ase.db import connect
from ase.io import read

from scripts.adsorption.force_finetune import load_manifest, validate_database_metadata, validate_label_row
from scripts.adsorption.force_role_data import role_metadata
from scripts.artifact_io import sha256_file, source_file_manifest_valid

from .prepare import CONFIG, ROOT, assert_group_isolation, save_once


def verify_originals(paths, all_rows):
    by_id = {r["sample_id"]: r for r in all_rows}
    legacy = json.loads(paths["legacy_manifest"].read_bytes())
    sources = [(split, row) for split, rows in legacy["splits"].items() for row in rows]
    sources += [("observed_heldout", row) for row in legacy["quarantined_observed_heldout"]]
    sources += [("train", row) for row in json.loads(paths["supplement"].read_bytes())["samples"]]
    physical = ("symbols", "fixed_atom_indices_0based", "forces_eV_per_A", "source_OUTCAR_sha256",
                "source_XDATCAR_sha256", "source_force_table_sha256", "total_magnetization_muB",
                "energy_eV_force_label_only", "toten_eV_force_label_only", "source_job_id", "magnetic_review_level")
    for split, original in sources:
        row = by_id[original["sample_id"]]
        if row["split"] != split or row["structure_sha256"] != original["structure_sha256"]:
            raise ValueError("legacy/supplement partition or structure changed")
        if any(row[key] != original[key] for key in physical if key in original):
            raise ValueError("original physical label or magnetic tier changed")
        if split != "train" and row["proposed_per_atom_loss_weights"] != original["proposed_per_atom_loss_weights"]:
            raise ValueError("protected metadata weights changed")
    static_count = 0
    for key in ("static_labels", "incremental_labels"):
        for original in json.loads(paths[key].read_bytes())["samples"]:
            row = by_id[original["sample_id"]]
            target = "heldout" if original["partition"] == "final_test" else original["partition"]
            if row["split"] != target or row["family_id"] != original["family_id"]:
                raise ValueError("frozen random-family partition changed")
            for field in ("forces_eV_per_A", "toten_eV_force_label_only", "structure_sha256",
                          "local_magnetization_muB", "total_magnetization_muB", "source_job_id"):
                if row[field] != original[field]:
                    raise ValueError("reviewed static data changed")
            static_count += 1
    return len(sources), static_count


def verify_databases(package, manifest):
    checked = {}
    for split in ("train", "development"):
        rows = manifest["splits"][split]
        database = package/(split+".db")
        metadata = validate_database_metadata(database, package/(split+"_metadata.npz"))
        items = list(connect(database).select())
        if len(items) != len(rows):
            raise ValueError("database count mismatch")
        for item, row in zip(items, rows, strict=True):
            atoms, exact = item.toatoms(), read(package/row["structure_path"], format="vasp")
            if (not np.array_equal(atoms.positions, exact.positions) or not np.array_equal(atoms.cell, exact.cell)
                    or not np.array_equal(atoms.get_forces(apply_constraint=False), row["forces_eV_per_A"])
                    or atoms.get_potential_energy() != row["energy_eV_force_label_only"]
                    or np.any(atoms.get_tags()) or item.data.sid != row["sample_id"]
                    or item.data.magnetic_review_level != row["magnetic_review_level"]):
                raise ValueError("database differs from manifest/source")
            fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
            if fixed != list(range(18)):
                raise ValueError("database fixed-atom mask changed")
            roles = role_metadata(row, split)
            if any(not np.array_equal(item.data[key], value) for key, value in roles.items()):
                raise ValueError("database sampler/role tensors changed")
        checked[split] = {"rows": len(rows), **metadata}
    return checked


def verify(package: Path, config_path: Path, source_root: Path):
    config = json.loads(config_path.read_bytes())
    paths = {k: source_root/v["path"] for k, v in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("original source modified")
    request = json.loads((package/"assembly_request.json").read_bytes())
    if not source_file_manifest_valid(request):
        raise ValueError("assembly source binding changed")
    manifest = load_manifest(package/"training_manifest.json")
    all_rows = [r for rows in manifest["splits"].values() for r in rows]+manifest["quarantined_observed_heldout"]
    assert_group_isolation(all_rows)
    for row in manifest["quarantined_observed_heldout"]:
        validate_label_row(package, row)
    original_count, static_count = verify_originals(paths, all_rows)
    checked = verify_databases(package, manifest)
    raw_archives = set()
    for row in all_rows:
        label = json.loads((package/row["label_source"]["path"]).read_bytes())
        archive = label["source_archive"]
        path = package/archive["path"]
        if str(path) not in raw_archives:
            if sha256_file(path) != archive["sha256"]:
                raise ValueError("archived original source bytes changed")
            raw_archives.add(str(path))
    train = manifest["splits"]["train"]
    if not np.isclose(sum(r["proposed_source_stage_sampling_probability"] for r in train), 1., atol=1e-12, rtol=0):
        raise ValueError("training probabilities not normalized")
    if (package/"heldout.db").exists() or (package/"training_request.json").exists():
        raise ValueError("unexpected evaluation loader or executable training request")
    if manifest["training_authorized"] is not False or manifest["energy_loss_coefficient"] != 0:
        raise ValueError("force-only preparation scope changed")
    result = {"status": "PASS_DATA_ONLY_NO_TRAINING", "split_counts": {s: len(v) for s, v in manifest["splits"].items()},
        "old_observed_heldout_quarantined": len(manifest["quarantined_observed_heldout"]),
        "original_legacy_rows_and_supplement_verified": original_count, "reviewed_statics_verified": static_count,
        "database_rows_verified": checked, "archived_original_sources_verified": len(raw_archives),
        "10B_retained_in_train": sum(r["source_collection"] == "10B_legacy_total_only6" for r in train),
        "legacy_replay_rows_without_explicit_job_id_preserve_source_groups": sum(not r.get("source_job_id") for r in all_rows),
        "training_magnetic_levels": dict(Counter(r["magnetic_review_level"] for r in train)),
        "verification_source_sha256": sha256_file(Path(__file__)),
        "manifest_sha256": sha256_file(package/"training_manifest.json"),
        "reserved_force_values_used_for_selection_or_statistics": False, "new_DFT_GPU_or_training": False}
    save_once(package/"independent_verification.json", result)
    return result


if __name__ == "__main__":
    config = json.loads(CONFIG.read_bytes())
    result = verify(ROOT/config["output"], CONFIG, ROOT)
    print(json.dumps({k: result[k] for k in ("status", "split_counts", "10B_retained_in_train")}))
