"""Prepare an isolated 536-frame two-epoch request; no deployment or training."""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

import yaml

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from archive.fe110_training512_20261027.prepare import BASE_MODEL, RUNTIME
from scripts.adsorption.force_training_preflight import verify_training_package
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
    write_json_exclusive,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
SOURCE = BASE / "combined_force_package_20261113_v1"
OUT = BASE / "training536_smoke_20261113_v1"
PACKAGE = OUT / "package"
ARM = PACKAGE / "control"
REMOTE = "/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1"
TEMPLATE = BASE / "training512_gpu0_20261027_v1/package/control/config.yml"
MANIFEST_SHA = "02ef3dcbf5306733856429b51406767d6e62f6fbc200c13b91a117a4a737bcd2"
CPU_MODULE = "scripts/adsorption/training536_cpu_preflight.py"


def config_for_536(template):
    config = copy.deepcopy(template)
    config.pop("checkpoint", None)
    config["optim"].update(max_epochs=2, eval_every=536, checkpoint_every=536)
    config["optim"]["scheduler_params"]["epochs"] = 2
    for split, key in (("train", "train"), ("development", "val")):
        config["dataset"][key]["src"] = REMOTE + "/control/" + split + ".db"
        config["dataset"][key]["metadata_path"] = REMOTE + "/control/" + split + "_metadata.npz"
    if set(config["dataset"]) != {"train", "val"}:
        raise ValueError("heldout/test loader forbidden")
    return config


def verify_frozen_source():
    context = load_json_object(OUT / "request_context.json")
    if frozen_hashes() != context["frozen_hashes_before"]:
        raise ValueError("source packages changed since request start")
    if sha256_file(SOURCE / "training_manifest.json") != MANIFEST_SHA:
        raise ValueError("frozen536 manifest changed")
    if not source_file_manifest_valid(load_json_object(SOURCE / "independent_verification.json")):
        raise ValueError("536 source verification binding changed")
    inventory = load_json_object(SOURCE / "package_inventory.json")
    if len(inventory["files"]) != inventory["file_count"]:
        raise ValueError("source inventory count changed")
    for item in inventory["files"]:
        path = (SOURCE / item["path"]).resolve()
        if (not path.is_relative_to(SOURCE.resolve()) or path.stat().st_size != item["bytes"]
                or sha256_file(path) != item["sha256"]):
            raise ValueError("source inventory file changed")
    return inventory


def run():
    if PACKAGE.exists():
        raise FileExistsError("preserve existing/partial execution package; inspect before retry")
    inventory = verify_frozen_source()
    manifest = load_json_object(SOURCE / "training_manifest.json")
    counts = {key: len(rows) for key, rows in manifest["splits"].items()}
    if counts != {"train": 536, "development": 78, "heldout": 53}:
        raise ValueError("frozen split counts changed")
    if len(manifest["quarantined_observed_heldout"]) != 16:
        raise ValueError("quarantine membership changed")
    if any(r["proposed_source_stage_sampling_probability"] != 1 / 536 for r in manifest["splits"]["train"]):
        raise ValueError("uniform536 sampling changed")
    shutil.copytree(SOURCE, ARM)
    source_files = [p for p in SOURCE.rglob("*") if p.is_file()]
    for path in source_files:
        if path.is_symlink() or sha256_file(path) != sha256_file(ARM / path.relative_to(SOURCE)):
            raise ValueError("frozen source copy changed")
    for relative in RUNTIME:
        target = ARM / "runtime" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for source, target in (("scripts/adsorption/role_training_job.sh", "role_training_job.sh"),
                           ("scripts/aqcat25_mz73_env.sh", "aqcat25_mz73_env.sh")):
        shutil.copyfile(ROOT / source, ARM / "runtime" / target)
    shutil.copyfile(Path(__file__).with_name("native_preflight.py"), ARM / "runtime" / CPU_MODULE)
    config = config_for_536(yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")))
    with (ARM / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=True)
    limits = {"epochs": 2, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
              "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "walltime_minutes": 30,
              "max_optimizer_steps": 1072, "baseline_optimizer_and_epoch_restored": False,
              "unattended_retries": 0}
    request = {"schema_version": 1, "runtime_contract_version": 3,
               "preparation_contract": "fe110_force536_uniform_twoepoch_preparation_v1",
               "document_kind": "aqcat25_adsorption_small_finetune_request",
               "status": "PREPARED_FOR_USER_REVIEW_NOT_SUBMITTED", "training_authorized": False,
               "manifest_path": "training_manifest.json", "config_path": "config.yml",
               "remote_package_root": REMOTE + "/control", "split_counts": counts,
               "base_checkpoint": copy.deepcopy(BASE_MODEL), "training_limits": limits,
               "candidate_checks": ["development-only forces_role_vector_mae best; freeze SHA",
                                    "no heldout/quarantine loader", "preserve magnetic tiers and families",
                                    "no automatic model promotion, inference, relaxation or VASP"],
               "remaining_before_submission": ["fresh complete GPU/Slurm/environment check and UUID binding",
                                               "reviewed new backend execution scope; do not reuse512 authority",
                                               "explicit authorization of exact execution request and budget"],
               "artifacts": [{"path": p.relative_to(ARM).as_posix(), "sha256": sha256_file(p)}
                             for p in sorted(ARM.rglob("*")) if p.is_file()]}
    write_json_exclusive(ARM / "training_request.json", request)
    verdict = verify_training_package(ARM / "training_request.json")
    write_json_exclusive(OUT / "local_preflight.json", verdict)
    write_json_exclusive(PACKAGE / "preflight_contract.json", {
        "document_kind": "CPU_ONLY_536_PACKAGE_PREFLIGHT_SCOPE", "user_request": "应直接准备536小试执行包并完成预检",
        "training_request_sha256": sha256_file(ARM / "training_request.json"),
        "hostname": "MZ73", "remote_root": REMOTE,
        "canonical_boundary_observed": load_json_object(OUT / "host_cpu_readonly.stdout")["canonical_root"],
        "CPU_count": 4, "memory_GB": 32, "max_seconds": 240,
        "allowed": ["new separate package staging", "source and DB/metadata validation", "native CLI parsing",
                    "existing original checkpoint read on CPU", "CPU model construction and parameter inventory"],
        "GPU_binding": None, "training_authorized": False, "forward_backward_optimizer_allowed": False,
        "model_weights_written": False, "scheduler_submission_allowed": False,
    })
    write_json_exclusive(OUT / "execution_policy_proposal.json", {
        "status": "PROPOSED_UNAUTHORIZED_GPU_VISIBILITY_BLOCKED", "arms": ["control"],
        "arm_request_sha256": {"control": sha256_file(ARM / "training_request.json")},
        "remote_root": REMOTE, "canonical_remote_boundary": load_json_object(OUT / "host_cpu_readonly.stdout")["canonical_root"],
        "execution_mode": "direct_no_scheduler", "executor": "scripts/adsorption/direct_force_training.py",
        "gpu_index": None, "gpu_uuid": None, "gpu_sharing": "not_authorized",
        "max_wall_seconds": 1800, "per_arm_wall_seconds": 1800,
        "runtime_stop_trigger_seconds_proposed": 1770, "exit_margin_seconds_proposed": 30,
        "strict_walltime_including_exit_validated": False, "max_epochs": 2,
        "max_native_iterations": 1072, "actual_optimizer_updates_recorded_separately": True,
        "CPU_count": 4, "memory_GB": 32, "automatic_retries": 0,
        "backend_policy_modified": False, "execution_authorization_created": False,
        "launch_controller_or_marker_created": False, "training_started": False,
    })
    copied = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size}
              for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    write_json_exclusive(OUT / "deployment_inventory.json", {"files": copied, "file_count": len(copied),
                                                               "total_bytes": sum(p["bytes"] for p in copied)})
    verify_frozen_source()
    sources = [Path(__file__), Path(__file__).with_name("native_preflight.py"), TEMPLATE,
               SOURCE / "training_manifest.json", SOURCE / "package_inventory.json",
               SOURCE / "independent_verification.json", ARM / "training_request.json",
               OUT / "local_preflight.json", OUT / "execution_policy_proposal.json",
               OUT / "deployment_inventory.json", ROOT / "configs/execution_backends.yaml",
               *[ROOT / relative for relative in RUNTIME]]
    write_json_exclusive(OUT / "preparation_receipt.json", {
        "status": "PREPARED_LOCAL_PASS_NOT_TRAINING_AUTHORIZED", "training_request_sha256": sha256_file(ARM / "training_request.json"),
        "frozen536_manifest_sha256": MANIFEST_SHA, "source_inventory_files_verified": inventory["file_count"],
        "source_files_copied_byte_identical": len(source_files), "frozen512_536_and_splits_unchanged": True,
        "native_iterations": 1072, "actual_optimizer_update_count_not_assumed": True,
        "model_loss_role_weights_and_normalizer_changed": False,
        "training_or_model_inference_started": False, "source_files": source_file_manifest(sources)})
    print({"status": verdict["status"], "request_sha256": sha256_file(ARM / "training_request.json"),
           "file_count": len(copied), "native_iterations": 1072, "training_authorized": False})


if __name__ == "__main__":
    run()
