"""Build two local,unauthorized training arms from the frozen pool; never connects remotely."""
import copy
import json
import shutil
from pathlib import Path

import numpy as np
import yaml
from ase.db import connect

from scripts.adsorption.force_finetune import build_database_metadata, local_path
from scripts.adsorption.force_training_preflight import verify_training_package
from scripts.artifact_io import sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
CALC = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
POOL = CALC / "adsorption_pool_rebuild_20261019_v1/prepared_v2"
DBS = CALC / "adsorption_runtime_test_20261019_v1"
OUTPUT = CALC / "adsorption_training_comparison_20261019_v1"
MANIFEST_SHA = "6deb86d4fcb2bfbde29f7d2d6faf3f2663afa2ac04c9d8a79659c876e6234330"
REMOTE = "/home/sbq/sbq/adsorption_training_comparison_20261019_v1"
DB_HASHES = {"train.db": "ed69021a5e0d2af008d10c3b68c7e070114816758bb75e3f82351c0e1ffdc3f2",
    "train_metadata.npz": "8c8d6aa1682d27bc30e19746dbcc4d920175b7eee2a73692edb54e1f3f789211",
    "development.db": "4ef0f967ca3a8fea3adcf49a89ed21e2cf520a839a01cab543116c3933d6f196",
    "development_metadata.npz": "37e0f40cfe27dd2f216d3bdc53383615e8307361dd943c478037f01a4dbb1d4f"}
BASE = {"path": "/home/sbq/sbq/aqcat25/demo_single/model.pt",
        "sha256": "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"}
RUNTIME_FILES = ["scripts/__init__.py", "scripts/adsorption/__init__.py", "scripts/adsorption/force_finetune.py",
    "scripts/adsorption/force_role_data.py", "scripts/adsorption/force_role_runtime.py",
    "scripts/adsorption/role_force_trainer.py", "scripts/adsorption/force_training_preflight.py"]


def copy_exact(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, target.open("xb") as dest:
        shutil.copyfileobj(src, dest)
    if sha256_file(source) != sha256_file(target):
        raise ValueError("copy differs from frozen source")


def make_config(remote, template):
    config = copy.deepcopy(template)
    config.pop("checkpoint", None)  # the explicit CLI warm start owns this value
    config["trainer"] = "scripts.adsorption.role_force_trainer.RoleForceTrainer"
    config["optim"].update(max_epochs=2, eval_every=248, checkpoint_every=248, grouped_force_objective=True)
    config["optim"]["scheduler_params"]["epochs"] = 2
    config["evaluation_metrics"]["primary_metric"] = "forces_role_vector_mae"
    for split, key in (("train", "train"), ("development", "val")):
        dataset = config["dataset"][key]
        dataset["src"] = remote + f"/{split}.db"
        dataset["metadata_path"] = remote + f"/{split}_metadata.npz"
        dataset["a2g_args"]["r_data_keys"] = ["is_spin_off", "is_low_fi", "adsorption_energy",
            "adsorption_force_weights", "adsorption_force_roles", "adsorption_replay"]
    return config


def make_arm(name, original, template):
    arm = OUTPUT / name
    arm.mkdir(exist_ok=False)
    payload = copy.deepcopy(original)
    changed = []
    if name == "control":
        for row in payload["splits"]["train"]:
            count = len(row["symbols"])
            free = sorted(set(range(count)) - set(row["fixed_atom_indices_0based"]))
            weights = np.zeros(count)
            weights[free] = 1. / len(free)
            row["proposed_per_atom_loss_weights"] = weights.tolist()
            row["proposed_source_stage_sampling_probability"] = 1. / len(payload["splits"]["train"])
            changed.append(row["sample_id"])
        payload["comparison_derivation"] = {"source_manifest_sha256": MANIFEST_SHA,
            "changed_train_fields_only": ["proposed_per_atom_loss_weights", "proposed_source_stage_sampling_probability"],
            "development_and_heldout_unchanged": True}
        write_json_exclusive(arm / "training_manifest.json", payload)
    else:
        copy_exact(POOL / "training_manifest.json", arm / "training_manifest.json")
    inputs = {row["structure_path"] for rows in original["splits"].values() for row in rows}
    inputs |= {row["label_source"]["path"] for rows in original["splits"].values() for row in rows}
    for path in sorted(inputs):
        copy_exact(local_path(POOL, path), local_path(arm, path))
    for filename in DB_HASHES:
        if name == "control" and filename == "train_metadata.npz":
            continue
        copy_exact(DBS / filename, arm / filename)
    if name == "control":
        database = connect(arm / "train.db")
        with database:
            for dbrow, row in zip(database.select(), payload["splits"]["train"], strict=True):
                data = dict(dbrow.data)
                data.update(adsorption_force_weights=row["proposed_per_atom_loss_weights"],
                            adsorption_sampling_probability=row["proposed_source_stage_sampling_probability"])
                database.update(dbrow.id, data=data)
        build_database_metadata(arm / "train.db", arm / "train_metadata.npz")
    for path in RUNTIME_FILES:
        copy_exact(ROOT / path, arm / "runtime" / path)
    for source, target in (("scripts/adsorption/role_training_job.sh", "role_training_job.sh"),
                           ("scripts/aqcat25_mz73_env.sh", "aqcat25_mz73_env.sh")):
        copy_exact(ROOT / source, arm / "runtime" / target)
    config = make_config(REMOTE + "/" + name, template)
    with (arm / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=True)
    write_json_exclusive(arm / "comparison_design.json", {"arm": name, "changed_train_sample_ids": changed,
        "source_manifest_sha256": MANIFEST_SHA, "sampling": "with_replacement_248_draws_per_epoch",
        "initializer_selection": "original AQCat25 fixed for both arms,not chosen on heldout",
        "heldout_integrity_records_only": True, "heldout_loader_or_predictions": False,
        "observed_old_heldout_16_fit_or_epoch_selection": False,
        "scope": "combined recipe comparison,not attribution of weighting versus sampling separately"})
    artifacts = [{"path": path.relative_to(arm).as_posix(), "sha256": sha256_file(path)}
                 for path in sorted(arm.rglob("*")) if path.is_file()]
    request = {"schema_version": 1, "runtime_contract_version": 3,
        "document_kind": "aqcat25_adsorption_small_finetune_request", "status": "PREPARED_FOR_USER_REVIEW_NOT_SUBMITTED",
        "training_authorized": False, "manifest_path": "training_manifest.json", "config_path": "config.yml",
        "remote_package_root": REMOTE + "/" + name, "split_counts": {s: len(rows) for s, rows in payload["splits"].items()},
        "base_checkpoint": BASE, "training_limits": {"epochs": 2, "learning_rate": 1e-5, "seed": 42,
            "batch_size": 1, "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "walltime_minutes": 30,
            "max_optimizer_steps": 496, "baseline_optimizer_and_epoch_restored": False, "unattended_retries": 0},
        "candidate_checks": ["common role-aware development metric;C/O/H/nearFe/otherFe/replay and whole-job review",
            "O/H/replay regressions are review warnings,not zero-tolerance automatic rejection",
            "no heldout use until one candidate frozen;no automatic promotion or acceleration claim"],
        "remaining_before_submission": ["explicit user authorization of exact arm request hash",
            "authorized deployment and on-disk native CLI/checkpoint/runtime/GPU/scheduler preflight"],
        "promotion": "none automatic", "speedup_claim": "not established", "artifacts": artifacts}
    write_json_exclusive(arm / "training_request.json", request)
    return {"path": name + "/training_request.json", "sha256": sha256_file(arm / "training_request.json"),
            "validation": verify_training_package(arm / "training_request.json")}


def main():
    if (OUTPUT / "comparison_request.json").exists() or (OUTPUT / "control").exists() or (OUTPUT / "treatment").exists():
        raise FileExistsError("preserve prepared or partial package; do not overwrite/retry blindly")
    if sha256_file(POOL / "training_manifest.json") != MANIFEST_SHA:
        raise ValueError("frozen pool changed")
    for name, value in DB_HASHES.items():
        if sha256_file(DBS / name) != value:
            raise ValueError("tested database changed: " + name)
    original = json.loads((POOL / "training_manifest.json").read_text(encoding="utf-8"))
    template = yaml.safe_load((ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6/config.yml").read_text())
    arms = {name: make_arm(name, original, template) for name in ("control", "treatment")}
    request = {"document_kind": "adsorption_bounded_training_comparison_review", "status": "PREPARED_NOT_AUTHORIZED",
        "training_authorized": False, "GPU_submitted": False, "arms": arms, "original_pool_sha256": MANIFEST_SHA,
        "base_checkpoint": BASE, "max_GPU_count_concurrent": 1, "arms_run_sequentially_only": True,
        "total_GPU_walltime_minutes_cap": 60, "total_optimizer_steps_cap": 992,
        "new_VASP_jobs": 0, "heldout_model_evaluations": 0, "automatic_retries": 0,
        "automatic_promotion": False, "heldout_46_reserved": True, "observed_heldout_16_quarantined": True,
        "initializer_proposal_adjustment": "freeze common original AQCat25 rather than add a separate initializer search;needs user review",
        "limitations": ["single seed;small two-epoch budget;not a converged-training or statistical significance claim",
            "combined weight+sampling change cannot isolate each component",
            "C2H3 remains test-only;no training coverage claim",
            "GPU AMP/full-model backward and actual VASP speedup remain unverified"],
        "source_files": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)} for path in
            [Path(__file__), ROOT / "scripts/adsorption/force_training_preflight.py", ROOT / "scripts/adsorption/role_training_job.sh"]]}
    write_json_exclusive(OUTPUT / "comparison_request.json", request)
    print(json.dumps({"status": request["status"], "request_sha256": sha256_file(OUTPUT / "comparison_request.json"),
        "arms": {key: value["sha256"] for key, value in arms.items()}, "GPU_submitted": False}))


if __name__ == "__main__":
    main()
