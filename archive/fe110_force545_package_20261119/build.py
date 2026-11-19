"""Materialize the standalone 545 data package and run the database preflight."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import chain
from pathlib import Path

import yaml

from archive.fe110_combined_force_package_20261023 import prepare as owner
from archive.fe110_force545_increment_20261119.prepare import BATCH, FROZEN, MODEL, OUT as INCREMENT, TEMPLATE, bind
from archive.fe110_force_package_20261113.prepare import inventory_entries
from archive.fe110_joint_priority_20261117.analyze import BASE, ROOT, guard_hashes
from scripts.adsorption.force_finetune import load_manifest, local_path, validate_database_metadata, verify_request
from scripts.adsorption.force_training_preflight import check_budget, check_database_labels
from scripts.artifact_io import load_json_object as load, sha256_file as sha, source_file_manifest, source_file_manifest_valid, write_json_exclusive

OUT = BASE / "force545_training_package_20261119_v1"
NATIVE = BASE / "force545_cpu_mapping_check_20261119_v1"
COUNT = 545
SPLITS = {"train": COUNT, "development": 78, "heldout": 53}
SEED = 42
PROBABILITY = 1 / COUNT


def reviewed_native_positions() -> tuple[dict, list[int]]:
    receipt = load(NATIVE / "receipt.json")
    source = Path(__file__).with_name("native_cpu_probe.py")
    record_path = NATIVE / "native_cpu.stdout.json"
    assert receipt["exit_code"] == 0 and receipt["stdout_sha256"] == sha(record_path)
    assert receipt["producer_sha256"] == sha(source)
    probe = load(record_path)
    assert probe["training_row_count"] == COUNT and probe["seed"] == SEED
    assert probe["training_authorized"] is False and probe["cuda_initialized"] is False and probe["strict_cpu_model_load"]
    assert probe["reference_config_sha256"] == sha(TEMPLATE) and probe["checkpoint_sha256"] == sha(MODEL)
    assert probe["sampler_sha256"] == sha(ROOT / "scripts/adsorption/force_role_runtime.py")
    draws = probe["epoch_draws_db_positions_0based"]
    assert len(draws) == 2 and all(len(epoch) == COUNT and set(epoch) <= set(range(COUNT)) for epoch in draws)
    counts = probe["epoch_counts_by_db_position"]
    for epoch, stored in zip(draws, counts, strict=True):
        tally = Counter(epoch)
        assert stored == [tally[i] for i in range(COUNT)]
    choices = [i for i, (a, b) in enumerate(zip(*counts, strict=True)) if a == b == 1][:9]
    if len(choices) != 9:
        raise ValueError("Need nine distinct DB positions visited once in both native CPU epochs")
    return probe, choices


def copy_sources():
    for entry in inventory_entries(FROZEN):
        relative = Path(entry["path"])
        if relative.parts[0] in ("labels", "structures", "provenance", "source_archives") or relative.name in (
            "development.db", "development_metadata.npz", "development_build_receipt.json"
        ):
            owner.copy_checked(local_path(FROZEN, entry["path"]), local_path(OUT, entry["path"]), entry["sha256"])
    target = OUT / "provenance" / "increment9"
    for name in ("increment_manifest.json", "isolation_review.json", "source_collection.json",
                 "local_verification.json", "force_label_source.json", "remote_terminal_and_potcar.stdout"):
        owner.copy_checked(INCREMENT / name, target / name, sha(INCREMENT / name))
    source = load(INCREMENT / "source_collection.json")
    for row in source["records"]:
        for name, digest in {**row["source_files"], "label_review.json": row["label_sha256"]}.items():
            relative = Path("source_evidence") / row["id"] / name
            owner.copy_checked(local_path(INCREMENT, relative.as_posix()), target / relative, digest)
    for name in ("receipt.json", "native_cpu.stdout.json"):
        owner.copy_checked(NATIVE / name, OUT / "provenance" / "cpu" / name, sha(NATIVE / name))


def assemble_manifest(prior: dict, added: dict, positions: list[int]) -> dict:
    source_rows = [(deepcopy(row), INCREMENT, row["label_source"], None) for row in added["samples"]]
    new_rows = owner.materialize(source_rows, OUT, [])
    if not (len(new_rows) == len({r["sample_id"] for r in new_rows}) == 9):
        raise ValueError("Wrong increment membership")
    for row in new_rows:
        raw_path = OUT / "provenance" / "increment9" / "source_evidence" / row["sample_id"] / "OUTCAR"
        assert sha(raw_path) == row["source_OUTCAR_sha256"]
        row["binding"]["outcar"]["copy_in_package"] = raw_path.relative_to(OUT).as_posix()
    new_by_pos = dict(zip(positions, new_rows, strict=True))
    old_rows = iter(deepcopy(prior["splits"]["train"]))
    ordered = []
    for index in range(COUNT):
        row = new_by_pos[index] if index in new_by_pos else next(old_rows)
        row["proposed_source_stage_sampling_probability"] = PROBABILITY
        ordered.append(row)
    assert next(old_rows, None) is None
    result = deepcopy(prior)
    result.update(
        package_version="20261119_545_v1",
        prior_manifest_sha256=sha(FROZEN / "training_manifest.json"),
        parent_admission_decision_sha256=prior["admission_decision_sha256"],
        increment_manifest_sha256=sha(INCREMENT / "increment_manifest.json"),
        sampling_policy="uniform_with_replacement; seed42 and DB order reviewed for one visit per new frame per epoch",
        source_files=source_file_manifest([
            FROZEN / "training_manifest.json", FROZEN / "package_inventory.json",
            INCREMENT / "increment_manifest.json", INCREMENT / "local_verification.json",
            NATIVE / "native_cpu.stdout.json", Path(__file__), ROOT / "scripts" / "adsorption" / "force_finetune.py",
        ]),
    )
    result.pop("admission_decision_sha256")
    result["splits"]["train"] = ordered
    assert {name: len(items) for name, items in result["splits"].items()} == SPLITS
    observed = result["quarantined_observed_heldout"]
    assert len(observed) == 16
    all_rows = list(chain(*result["splits"].values(), observed))
    assert len({r["sample_id"] for r in all_rows}) == 692
    owner.assert_group_isolation(all_rows)
    return result


def verify_preserved(prior, result, new_ids):
    for split in ("development", "heldout"):
        assert prior["splits"][split] == result["splits"][split]
    assert prior["quarantined_observed_heldout"] == result["quarantined_observed_heldout"]
    ordered_old = [row for row in result["splits"]["train"] if row["sample_id"] not in new_ids]
    for row, old in zip(ordered_old, prior["splits"]["train"], strict=True):
        assert row == {**old, "proposed_source_stage_sampling_probability": PROBABILITY}


def training_review():
    config = yaml.safe_load((INCREMENT / "review_configs" / "increment545.yml").read_text(encoding="utf-8"))
    for group, name in (("train", "train"), ("val", "development")):
        config["dataset"][group].update(src=f"./{name}.db", metadata_path=f"./{name}_metadata.npz")
    with (OUT / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
    relpaths = ["training_manifest.json", "config.yml", "train.db", "train_metadata.npz",
                "development.db", "development_metadata.npz"]
    for name in ("force_role_data.py", "force_role_runtime.py", "role_force_trainer.py"):
        source = ROOT / "scripts" / "adsorption" / name
        relative = "runtime/scripts/adsorption/" + name
        owner.copy_checked(source, OUT / relative, sha(source))
        relpaths.append(relative)
    limits = load(INCREMENT / "comparison_preflight.json")["arms"]["increment545"]["limits"]
    request = {
        "document_kind": "aqcat25_adsorption_small_finetune_request",
        "runtime_contract_version": 3,
        "training_authorized": False,
        "split_counts": SPLITS,
        "manifest_path": "training_manifest.json",
        "config_path": "config.yml",
        "remote_package_root": ".",
        "training_limits": limits,
        "base_checkpoint": bind(MODEL),
        "artifacts": [{"path": name, "sha256": sha(OUT / name)} for name in relpaths],
    }
    request_path = OUT / "training_request.review.json"
    write_json_exclusive(request_path, request)
    check_budget(request, config)
    check_database_labels(OUT, request)
    assert verify_request(request_path)["training_authorized"] is False
    return request_path


def main():
    plan = load(BATCH / "final_submission_list.json")
    assert guard_hashes() == plan["frozen_hashes"]
    prior = load_manifest(FROZEN / "training_manifest.json")
    added = load(INCREMENT / "increment_manifest.json")
    assert source_file_manifest_valid(added) and added["sample_count"] == 9 and added["training_authorized"] is False
    verification = load(INCREMENT / "local_verification.json")
    assert verification["physical_label_rows_replayed"] == 9 and bind(INCREMENT / "increment_manifest.json") in verification["input_artifacts"]
    probe, positions = reviewed_native_positions()
    OUT.mkdir()
    copy_sources()
    manifest = assemble_manifest(prior, added, positions)
    new_ids = {item["sample_id"] for item in added["samples"]}
    verify_preserved(prior, manifest, new_ids)
    manifest_path = OUT / "training_manifest.json"
    write_json_exclusive(manifest_path, manifest)
    train_receipt = owner.database("train", OUT, manifest["splits"]["train"])
    dev_receipt = validate_database_metadata(OUT / "development.db", OUT / "development_metadata.npz")
    assert train_receipt["rows"] == COUNT and dev_receipt["rows"] == 78
    for name in ("development.db", "development_metadata.npz"):
        assert sha(OUT / name) == sha(FROZEN / name)
    request = training_review()
    assert guard_hashes() == plan["frozen_hashes"]
    assert not any(p.exists() for p in (OUT / "heldout.db", OUT / "observed_heldout.db"))
    selected = [
        {"id": manifest["splits"]["train"][i]["sample_id"], "db_position_0based": i,
         "native_draws_by_epoch": [counts[i] for counts in probe["epoch_counts_by_db_position"]]}
        for i in positions
    ]
    assert {r["id"] for r in selected} == new_ids
    write_json_exclusive(OUT / "cpu_data_preflight.json", {
        "status": "PASS_STANDALONE_545_PACKAGE_DB_AND_NATIVE_CPU_SAMPLING_PLAN",
        "request": bind(request), "manifest": bind(manifest_path), "train_database": train_receipt,
        "development_database": dev_receipt, "cpu_native_mapping": bind(OUT / "provenance" / "cpu" / "native_cpu.stdout.json"),
        "label_rows": 692, "database_rows_validated": 623, "new_frames": selected,
        "protected_members_unchanged": True, "frozen_file_hashes_unchanged": True,
        "training_authorized": False, "gpu_started": False, "optimizer_steps": 0, "dft_submissions": 0,
    })
    print("545 training + 78 development ASE rows checked; nine new labels each scheduled once per epoch.")


if __name__ == "__main__":
    main()
