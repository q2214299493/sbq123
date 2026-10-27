"""Prepare one force-only512-frame trial and validation plan;never deploy or run."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil

import yaml

from scripts.adsorption.force_training_preflight import verify_training_package
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
SOURCE = BASE / "combined_force_package_20261027_v3"
OUTPUT = BASE / "training512_20261027_v1"
PACKAGE = OUTPUT / "package"
ARM = PACKAGE / "control"
REMOTE = "/home/sbq/sbq/fe110_force_training512_20261027_v1"
CONFIG = ROOT / "configs/fe110_reico_pilot/training512_20261027_v1.json"
TEMPLATE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v2/package/control/config.yml"
MANIFEST_SHA = "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee"
BASE_MODEL = {"path": "/home/sbq/sbq/aqcat25/demo_single/model.pt",
              "sha256": "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"}
RUNTIME = ["scripts/__init__.py", "scripts/adsorption/__init__.py", "scripts/artifact_io.py",
    "scripts/adsorption/force_finetune.py", "scripts/adsorption/force_role_data.py",
    "scripts/adsorption/force_role_runtime.py", "scripts/adsorption/role_force_trainer.py",
    "scripts/adsorption/force_training_preflight.py", "scripts/adsorption/direct_gpu_batch.py",
    "scripts/adsorption/direct_force_training.py", "scripts/adsorption/direct_training_arm.py"]


def make_config(template):
    config = copy.deepcopy(template)
    config.pop("checkpoint", None)
    config["optim"].update(max_epochs=2, eval_every=512, checkpoint_every=512)
    config["optim"]["scheduler_params"]["epochs"] = 2
    for split, key in [("train", "train"), ("development", "val")]:
        config["dataset"][key]["src"] = REMOTE + "/control/" + split + ".db"
        config["dataset"][key]["metadata_path"] = REMOTE + "/control/" + split + "_metadata.npz"
    return config


def validation_plan(manifest):
    development = manifest["splits"]["development"]
    heldout = manifest["splits"]["heldout"]
    historical = [r["sample_id"] for r in heldout if r["source_collection"] == "legacy_control_20261019"]
    if len(historical) != 46:
        raise ValueError("historically evaluated heldout membership changed")
    return {"status": "PREPARED_NO_MODEL_EVALUATION", "selection_split": "development",
        "selection_metric": "forces_role_vector_mae", "development_frames": len(development),
        "heldout_frames": len(heldout), "heldout_ids": [r["sample_id"] for r in heldout],
        "historically_evaluated_heldout_ids": historical,
        "historical_heldout_membership_source_verified": True,
        "heldout_is_new_blind_test": False, "heldout_consumed_for_candidate_selection": False,
        "observed_heldout16_quarantined": True,
        "checkpoint_rule": "one development-selected best checkpoint;freeze its SHA before any heldout inference",
        "comparison_checkpoints": [BASE_MODEL, {"name": "existing_control",
            "sha256": "cfcac123cd56b866a1ea36cc780a3aee634f3aeec979bda4ae8bee2cc831e523"},
            {"name": "new512_candidate", "sha256": None}],
        "report_groups": ["C2HO", "C2H2O", "C2H3", "C3H2O", "replay", "whole_calculation_group"],
        "report_atom_roles": ["adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe"],
        "report_force_edges_eV_A": [0., .05, .1, .5, 1., 2., 5., 10.],
        "requested_metrics": ["force component MAE", "force vector RMSE", "angle/direction diagnostics with small-force guard", "large-error sample list"],
        "uncovered_force_ranges_reported_as": "no_test_coverage;never_imputed",
        "limitations": ["C3H2O train has0frames<=0.05eV/A;late-stage generalization unproven",
            "53reserved frames include46historically evaluated frames;not a new blind test",
            "two epochs and one seed are an initial trial,not converged training or significance evidence",
            "more optimizer iterations than old248frame control confounds data-only causal attribution",
            "force-only training cannot establish adsorption-energy accuracy or measured VASP acceleration"],
        "new_DFT_or_optimizer_runs_authorized": False, "GPU_evaluation_authorized": False}


def run():
    scope = load_json_object(CONFIG)
    if scope["training_limits"] != {"epochs": 2, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
            "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "walltime_minutes": 30,
            "max_optimizer_steps": 1024, "baseline_optimizer_and_epoch_restored": False, "unattended_retries": 0}:
        raise ValueError("review scope differs from bounded one-model trial")
    if PACKAGE.exists():
        raise FileExistsError("preserve existing or partial package;never overwrite")
    if sha256_file(SOURCE / "training_manifest.json") != MANIFEST_SHA:
        raise ValueError("frozen512manifest changed")
    if not source_file_manifest_valid(load_json_object(SOURCE / "independent_verification.json")):
        raise ValueError("source data verification binding changed")
    inventory = load_json_object(SOURCE / "package_inventory.json")
    if len(inventory["files"]) != inventory["file_count"]:
        raise ValueError("source inventory count changed")
    for row in inventory["files"]:
        path = (SOURCE / row["path"]).resolve()
        if not path.is_relative_to(SOURCE.resolve()) or sha256_file(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise ValueError("source package inventory mismatch")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, ARM)
    for path in SOURCE.rglob("*"):
        if path.is_file() and sha256_file(path) != sha256_file(ARM / path.relative_to(SOURCE)):
            raise ValueError("execution dataset copy differs")
    for rel in RUNTIME:
        destination = ARM / "runtime" / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, destination)
    for source, target in [("scripts/adsorption/role_training_job.sh", "role_training_job.sh"),
                           ("scripts/aqcat25_mz73_env.sh", "aqcat25_mz73_env.sh")]:
        shutil.copy2(ROOT / source, ARM / "runtime" / target)
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    config = make_config(template)
    with (ARM / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=True)
    manifest = load_json_object(ARM / "training_manifest.json")
    if {s: len(v) for s, v in manifest["splits"].items()} != {"train": 512, "development": 78, "heldout": 53}:
        raise ValueError("dataset split count changed")
    request = {"schema_version": 1, "runtime_contract_version": 3,
        "document_kind": "aqcat25_adsorption_small_finetune_request", "status": "PREPARED_FOR_USER_REVIEW_NOT_SUBMITTED",
        "training_authorized": False, "manifest_path": "training_manifest.json", "config_path": "config.yml",
        "remote_package_root": REMOTE + "/control", "split_counts": {s: len(v) for s, v in manifest["splits"].items()},
        "base_checkpoint": BASE_MODEL, "training_limits": scope["training_limits"],
        "candidate_checks": ["development-only model selection", "fixed original and existing-control comparison after candidate freeze",
            "preserve magnetic levels and whole-family isolation", "no automatic promotion or VASP acceleration claim"],
        "remaining_before_submission": ["explicit user confirmation of exact request and budget",
            "fresh GPU1 idle check", "authorized deployment and on-disk native CLI/checkpoint preflight", "fresh direct execution authorization"],
        "artifacts": [{"path": p.relative_to(ARM).as_posix(), "sha256": sha256_file(p)} for p in sorted(ARM.rglob("*")) if p.is_file()]}
    write_json_exclusive(ARM / "training_request.json", request)
    verdict = verify_training_package(ARM / "training_request.json")
    write_json_exclusive(OUTPUT / "local_preflight.json", verdict)
    write_json_exclusive(OUTPUT / "validation_plan.json", validation_plan(manifest))
    proposal = {"status": "PROPOSED_NOT_AUTHORIZED", "arms": ["control"],
        "arm_request_sha256": {"control": sha256_file(ARM / "training_request.json")},
        "remote_root": REMOTE, "canonical_remote_boundary": "/home/ubuntu/hdd/sbq/sbq",
        "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da",
        "execution_mode": "direct_no_scheduler", "executor": "scripts/adsorption/direct_force_training.py",
        "max_wall_seconds": 1800, "per_arm_wall_seconds": 1800, "max_epochs": 2,
        "max_optimizer_steps_per_arm": 1024, "CPU_count": 4, "memory_GB": 32, "automatic_retries": 0,
        "model_promotion_or_vasp_execution": "forbidden", "root_backend_policy_modified": False,
        "authorization_created": False, "deployment_started": False, "training_started": False}
    write_json_exclusive(OUTPUT / "execution_policy_proposal.json", proposal)
    sources = [Path(__file__), CONFIG, TEMPLATE, SOURCE / "training_manifest.json", SOURCE / "package_inventory.json",
        OUTPUT / "local_preflight.json", OUTPUT / "validation_plan.json", OUTPUT / "execution_policy_proposal.json",
        ARM / "training_request.json", ROOT / "configs/execution_backends.yaml", *[ROOT / p for p in RUNTIME]]
    write_json_exclusive(OUTPUT / "preparation_receipt.json", {"status": "PREPARED_NOT_DEPLOYED_OR_TRAINED",
        "training_request_sha256": sha256_file(ARM / "training_request.json"), "source_manifest_sha256": MANIFEST_SHA,
        "data_copy_bytes_unchanged": True, "whole_family_isolation_and_magnetic_levels_unchanged": True,
        "root_backend_policy_modified": False, "execution_authorization_created": False,
        "training_started": False, "source_files": source_file_manifest(sources)})
    print({"status": "PREPARED_NOT_DEPLOYED_OR_TRAINED", "request_sha256": sha256_file(ARM / "training_request.json"),
        "split_counts": request["split_counts"], "max_training_iterations": 1024, "GPU_minutes_cap": 30}, flush=True)


if __name__ == "__main__":
    run()
