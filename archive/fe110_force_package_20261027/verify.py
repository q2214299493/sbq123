"""Verify source-preserving assembly and the actual ASE training databases."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ase.io import read

from archive.fe110_combined_force_package_20261023 import prepare as owner
from archive.fe110_combined_force_package_20261023.verify import verify_databases
from scripts.adsorption.force_finetune import load_manifest, local_path, validate_label_row
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from .prepare import CONFIG, PHYSICAL, ROOT, scope, source_rows


def compare_source(row, original):
    for key in PHYSICAL + ("source_OUTCAR_sha256", "source_XDATCAR_sha256", "source_force_table_sha256",
                            "magnetic_review_level", "family_id", "calculation_group", "energy_eV_force_label_only"):
        if key in original and row.get(key) != original[key]:
            raise ValueError("physical/source identity changed " + key)
    if row["split"] != original["split"]:
        raise ValueError("source partition changed")
    if row["split"] != "train":
        for key in ("proposed_per_atom_loss_weights", "proposed_source_stage_sampling_probability", "force_role_groups"):
            if row.get(key) != original.get(key):
                raise ValueError("protected validation/test metadata changed " + key)


def archive_chain(output, label):
    """Check old nested archive references after rebasing into the new package."""
    seen = set()
    while "source_archive" in label:
        archive = label["source_archive"]
        path = local_path(output, archive["path"])
        if path in seen:
            raise ValueError("source archive cycle")
        seen.add(path)
        if sha256_file(path) != archive["sha256"]:
            raise ValueError("archived source bytes changed")
        label = load_json_object(path)
    return seen


def run():
    config, paths, output = scope()
    request = load_json_object(output / "assembly_request.json")
    if not source_file_manifest_valid(request):
        raise ValueError("assembly source binding stale")
    old, original_rows, _ = source_rows(config, paths)
    originals = {r[0]["sample_id"]: r[0] for r in original_rows}
    manifest = load_manifest(output / "training_manifest.json")
    all_rows = [r for rows in manifest["splits"].values() for r in rows] + manifest["quarantined_observed_heldout"]
    if len(all_rows) != len(originals) or {r["sample_id"] for r in all_rows} != set(originals):
        raise ValueError("source sample identities lost or added")
    owner.assert_group_isolation(all_rows)
    archives = set()
    for row in all_rows:
        compare_source(row, originals[row["sample_id"]])
        validate_label_row(output, row)
        label = load_json_object(local_path(output, row["label_source"]["path"]))
        archives.update(archive_chain(output, label))
        atoms = read(output / row["structure_path"], format="vasp")
        if atoms.get_chemical_symbols() != row["symbols"]:
            raise ValueError("materialized atom order changed")
    databases = verify_databases(output, manifest)
    for split in ("development", "heldout"):
        if [r["sample_id"] for r in manifest["splits"][split]] != [r["sample_id"] for r in old["splits"][split]]:
            raise ValueError("protected partition membership/order changed")
    if [r["sample_id"] for r in manifest["quarantined_observed_heldout"]] != [r["sample_id"] for r in old["quarantined_observed_heldout"]]:
        raise ValueError("observed-heldout quarantine changed")
    train = manifest["splits"]["train"]
    if len(train) != 512 or len(manifest["quarantined_observed_heldout"]) != 16:
        raise ValueError("package counts changed")
    if {r["magnetic_review_level"] for r in train if r["source_collection"] == "10B_legacy_total_only6"} != {"LEGACY_TOTAL_MAGNETIZATION_ONLY"}:
        raise ValueError("legacy10B magnetic tier changed")
    if (manifest["training_authorized"] is not False or manifest["energy_loss_coefficient"] != 0
            or manifest["reportable_final_energy"] is not False):
        raise ValueError("force-only data preparation boundary changed")
    if (output / "heldout.db").exists() or (output / "training_request.json").exists():
        raise ValueError("unexpected executable training or heldout loader")
    result = {"status": "PASS_DATA_ONLY_NO_TRAINING", "source_rows_verified": len(all_rows),
        "split_counts": {s: len(v) for s, v in manifest["splits"].items()}, "observed_heldout_quarantined": 16,
        "database_rows_verified": databases, "nested_source_archives_verified": len(archives),
        "protected_development_heldout_membership_and_metadata_unchanged": True,
        "prior366manifest_sha256": sha256_file(paths["prior_manifest"]), "audit485sha256": sha256_file(paths["audit"]),
        "manifest_sha256": sha256_file(output / "training_manifest.json"),
        "magnetic_levels_train": dict(Counter(r["magnetic_review_level"] for r in train)),
        "new_compute_or_training": False, "source_files": source_file_manifest([
            CONFIG, Path(__file__), ROOT / "archive/fe110_combined_force_package_20261023/verify.py",
            output / "assembly_request.json", output / "package_summary.json", output / "training_manifest.json"])}
    owner.save_once(output / "independent_verification.json", result)
    print({k: result[k] for k in ("status", "source_rows_verified", "split_counts", "observed_heldout_quarantined")})
    return result


if __name__ == "__main__":
    run()
