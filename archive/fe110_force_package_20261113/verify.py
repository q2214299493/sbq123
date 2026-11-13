"""Read back every source row, raw candidate force table, and actual database."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ase.io import read

from archive.fe110_c3_lowforce_candidates_20261109.verify import force_slice
from archive.fe110_combined_force_package_20261023 import prepare as owner
from archive.fe110_combined_force_package_20261023.verify import verify_databases
from archive.fe110_force_package_20261027.verify import archive_chain, compare_source
from scripts.adsorption.force_finetune import load_manifest, local_path, validate_label_row
from scripts.artifact_io import sha256_bytes, sha256_file, source_file_manifest, source_file_manifest_valid
from .prepare import COLLECTION, COUNTS, all_rows, check_preserved, inventory_entries, load, scope


def verify_membership(manifest, old, additions):
    rows = all_rows(manifest)
    by_id = {r["sample_id"]: r for r in rows}
    if len(rows) != 683 or len(by_id) != 683 or {s: len(v) for s, v in manifest["splits"].items()} != COUNTS:
        raise ValueError("source count/membership changed")
    owner.assert_group_isolation(rows)
    old_rows = all_rows(old)
    for original in old_rows:
        check_preserved(by_id[original["sample_id"]], original)
    candidate_ids = [r["sample_id"] for r in additions]
    if ([r["sample_id"] for r in manifest["splits"]["train"]]
            != [r["sample_id"] for r in old["splits"]["train"]] + candidate_ids):
        raise ValueError("training order or approved additions changed")
    for split in ("development", "heldout"):
        if [r["sample_id"] for r in manifest["splits"][split]] != [r["sample_id"] for r in old["splits"][split]]:
            raise ValueError("protected partition order changed")
    if ([r["sample_id"] for r in manifest["quarantined_observed_heldout"]]
            != [r["sample_id"] for r in old["quarantined_observed_heldout"]]):
        raise ValueError("observed-heldout order changed")
    return rows, by_id


def verify_labels(output, rows, by_id, additions):
    archives = set()
    for row in rows:
        validate_label_row(output, row)
        label = load(local_path(output, row["label_source"]["path"]))
        archives.update(archive_chain(output, label))
        if read(output / row["structure_path"], format="vasp").get_chemical_symbols() != row["symbols"]:
            raise ValueError("materialized atom order changed")
    raw_source = (output / "provenance/c3_candidates/source/OUTCAR").read_bytes()
    for original in additions:
        row = by_id[original["sample_id"]]
        compare_source(row, original)
        table, _ = force_slice(raw_source, row)
        if (table != (output / row["raw_force_table_path"]).read_bytes()
                or sha256_bytes(table) != row["source_force_table_sha256"]):
            raise ValueError("raw candidate force binding changed")
        expected_stage = "early_lowforce_process" if row["ionic_step"] == 15 else "late_lowforce_process"
        if row["stage"] != expected_stage or row["source_collection"] != COLLECTION:
            raise ValueError("candidate phase/source annotation changed")
    return archives


def verify_snapshots(output, paths, inventories):
    # Check every copied raw/review file against the original inventory.
    for entry in inventories["candidates"]:
        if sha256_file(output / "provenance/c3_candidates" / entry["path"]) != entry["sha256"]:
            raise ValueError("candidate source snapshot changed")
    for key, path in paths.items():
        if sha256_file(output / "provenance/inputs" / (key + ".json")) != sha256_file(path):
            raise ValueError("input snapshot differs from original bytes")
    for name in ("development.db", "development_metadata.npz", "development_build_receipt.json"):
        if sha256_file(output / name) != sha256_file(paths["prior_manifest"].parent / name):
            raise ValueError("development bytes changed")


def verify_boundary(output, manifest):
    if (manifest["training_authorized"] is not False or manifest["training_target"] != "forces_only"
            or manifest["energy_loss_coefficient"] != 0 or manifest["reportable_final_energy"] is not False
            or manifest["new_VASP"] is not False or manifest["model_promoted"] is not False):
        raise ValueError("data-only scope changed")
    if any((output / name).exists() for name in ("heldout.db", "observed_heldout.db", "training_request.json")):
        raise ValueError("unexpected heldout loader or executable training request")


def run():
    _, paths, inventories, output = scope()
    for name in ("assembly_request.json", "isolation_review.json", "package_summary.json"):
        if not source_file_manifest_valid(load(output / name)):
            raise ValueError("assembled evidence binding changed: " + name)
    manifest = load_manifest(output / "training_manifest.json")
    old, additions = load(paths["prior_manifest"]), load(paths["candidate_manifest"])["samples"]
    rows, by_id = verify_membership(manifest, old, additions)
    archives = verify_labels(output, rows, by_id, additions)
    verify_snapshots(output, paths, inventories)
    databases = verify_databases(output, manifest)
    verify_boundary(output, manifest)
    result = {"status": "PASS_FORCE536_DATA_ONLY_SOURCE_BINDINGS", "source_rows_verified": len(rows),
              "split_counts": COUNTS, "observed_heldout_quarantined": 16, "raw_candidate_force_tables_verified": 24,
              "database_rows_verified": databases, "nested_source_archives_verified": len(archives),
              "original512_inventory_files_verified": len(inventories["prior"]) - 1,
              "original_candidate_inventory_files_verified": len(inventories["candidates"]) - 1,
              "original_packages_unchanged": True, "development_database_byte_identical": True,
              "protected_membership_order_labels_roles_magnetic_tiers_unchanged": True,
              "coordinate_precision_evidence": "24 byte-identical structures reuse admitted XDATCAR replay at <=1e-12 A",
              "magnetic_levels_train": dict(Counter(r["magnetic_review_level"] for r in manifest["splits"]["train"])),
              "manifest_sha256": sha256_file(output / "training_manifest.json"),
              "training_authorized": False, "training_executed": False, "new_DFT": False,
              "formal_adsorption_acceptance": False, "terminal_scheduler_status": None,
              "source_files": source_file_manifest([Path(__file__), output / "assembly_request.json",
                                                    output / "training_manifest.json", output / "package_summary.json"])}
    owner.save_once(output / "independent_verification.json", result)
    # Seal only after verification; the inventory itself is the sole excluded file.
    entries = [{"path": p.relative_to(output).as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size}
               for p in sorted(output.rglob("*")) if p.is_file() and p != output / "package_inventory.json"]
    owner.save_once(output / "package_inventory.json", {
        "document_kind": "force_data_package_inventory", "files": entries, "file_count": len(entries),
        "bytes": sum(e["bytes"] for e in entries), "inventory_self_excluded": True,
        "training_authorized": False})
    inventory_entries(output)
    return result


if __name__ == "__main__":
    result = run()
    print({k: result[k] for k in ("status", "source_rows_verified", "split_counts")})
