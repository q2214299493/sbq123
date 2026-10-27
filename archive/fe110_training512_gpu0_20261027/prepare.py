"""Rebind the unstarted512-frame trial to one allowlisted sharedGPU0 run."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil

import yaml

from scripts.adsorption.direct_force_training import verify
from scripts.adsorption.force_training_preflight import verify_training_package
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OLD = BASE / "training512_20261027_v1/package"
OUTPUT = BASE / "training512_gpu0_20261027_v1"
PACKAGE = OUTPUT / "package"
ARM = PACKAGE / "control"
REMOTE = "/home/sbq/sbq/fe110_force_training512_gpu0_20261027_v1"
OLD_REMOTE = "/home/sbq/sbq/fe110_force_training512_20261027_v1"
RUN_ID = "direct-fe110-force512-gpu0-20261027-v1"
EXCEPTION = "fe110_force_training512_gpu0_20261027"
POLICY = ROOT / "configs/execution_backends.yaml"
AUTH = ROOT / "docs/reviews/fe110_training512_gpu0_20261027/user_authorization.md"
OLD_ARM_SHA = "fbc1fb2d7b8753e5429db2253559cff5a68669a0f620eebe515f01ad6c1c84e7"
CHANGED_RUNTIME = ["scripts/adsorption/direct_gpu_batch.py", "scripts/adsorption/direct_force_training.py",
                   "scripts/adsorption/direct_training_arm.py"]


def prepare():
    if PACKAGE.exists():
        raise FileExistsError("preserve existing GPU0 package;inspect receipt rather than rebuild")
    before = load_json_object(OUTPUT / "precheck.json")
    if before["new_root_exists"] or any(before["old_launch_markers"].values()) or "> 用吧" not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("old run may exist or GPU0 confirmation missing")
    old = load_json_object(OLD / "control/training_request.json")
    if sha256_file(OLD / "control/training_request.json") != OLD_ARM_SHA:
        raise ValueError("old approved arm changed")
    for row in old["artifacts"]:
        if sha256_file(OLD / "control" / row["path"]) != row["sha256"]:
            raise ValueError("old frozen package artifact changed")
    shutil.copytree(OLD / "control", ARM, ignore=shutil.ignore_patterns("training_request.json", "direct_arm_authorization.json", "config.yml"))
    for relative in CHANGED_RUNTIME:
        (ARM / "runtime" / relative).write_bytes((ROOT / relative).read_bytes())
    config = yaml.safe_load((OLD / "control/config.yml").read_text(encoding="utf-8"))
    for dataset in config["dataset"].values():
        for key in ["src", "metadata_path"]:
            dataset[key] = dataset[key].replace(OLD_REMOTE, REMOTE, 1)
    with (ARM / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=True)
    request = copy.deepcopy(old)
    request["previous_request_sha256"] = OLD_ARM_SHA
    request["remote_package_root"] = REMOTE + "/control"
    request["remaining_before_submission"] = ["authorized GPU0 native preflight and retired unstarted GPU1 authorization"]
    request["artifacts"] = [{"path": p.relative_to(ARM).as_posix(), "sha256": sha256_file(p)} for p in sorted(ARM.rglob("*")) if p.is_file()]
    write_json_exclusive(ARM / "training_request.json", request)
    verdict = verify_training_package(ARM / "training_request.json")
    write_json_exclusive(OUTPUT / "local_preflight.json", verdict)
    new_sha = sha256_file(ARM / "training_request.json")
    allowed = [{k: p[k] for k in ["pid", "uid", "start_ticks", "script"]} for p in before["allowed_processes"]]
    if len(allowed) != 8 or any(p["uid"] != 1007 or p["script"] != "wsgi_recommender.py" for p in allowed):
        raise ValueError("reviewed GPU0 resident identity changed")
    sharing = {"mode": "resident_service_allowlist", "allowed_processes": allowed, "max_training_memory_MiB": 16384}
    comparison = {"document_kind": "adsorption_bounded_single_training_review", "arms": {"control": {"sha256": new_sha}},
        "previous_arm_request_sha256": OLD_ARM_SHA, "total_GPU_walltime_minutes_cap": 30, "total_optimizer_steps_cap": 1024,
        "gpu_sharing": sharing, "physical_labels_splits_sampling_and_magnetic_levels_unchanged": True,
        "source_files": source_file_manifest([AUTH, OUTPUT / "precheck.json", OUTPUT / "local_preflight.json", OLD / "control/training_request.json"]) }
    write_json_exclusive(PACKAGE / "comparison_request.json", comparison)
    previous_policy = OUTPUT / "previous_execution_backends.yaml"
    previous_policy.write_bytes(POLICY.read_bytes())
    exception = {"authorized_by": "user_explicit_20261027_use_sharedGPU0_for_existing512_trial", "authorizing_user_request": "用吧",
        "scope": "one_uniform_force_only512_frame_candidate_on_allowlisted_sharedGPU0", "arms": ["control"],
        "remote_root": REMOTE, "canonical_remote_boundary": "/home/ubuntu/hdd/sbq/sbq", "gpu_index": 0,
        "gpu_uuid": "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75", "gpu_sharing": sharing,
        "execution_mode": "direct_no_scheduler", "executor": "scripts/adsorption/direct_force_training.py",
        "model_backend": "aqcat25_role_force_training", "original_comparison_sha256": sha256_file(PACKAGE / "comparison_request.json"),
        "arm_request_sha256": {"control": new_sha}, "max_wall_seconds": 1800, "per_arm_wall_seconds": 1800,
        "max_epochs": 2, "max_optimizer_steps_per_arm": 1024, "CPU_count": 4, "memory_GB": 32,
        "parallel_arms": 1, "automatic_retries": 0, "explicit_authorization_required": True,
        "producer_exit_record_required": True, "scheduler_job_id": None, "slurm_id_emulation": "forbidden",
        "model_promotion_or_vasp_execution": "forbidden", "alter_shared_services_or_other_users_jobs": "forbidden",
        "supersedes_unstarted_exception": "fe110_force_training512_20261027"}
    text = POLICY.read_text(encoding="utf-8")
    marker = "    direct_execution_exceptions:\n"
    if text.count(marker) != 1 or EXCEPTION in yaml.safe_load(text)["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("backend insertion is ambiguous or already exists")
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    POLICY.write_text(text.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1), encoding="utf-8", newline="\n")
    (PACKAGE / "execution_backends.yaml").write_bytes(POLICY.read_bytes())
    (PACKAGE / "scope.md").write_bytes(AUTH.read_bytes())
    write_json_exclusive(ARM / "direct_arm_authorization.json", {"user_authorized": True, "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE",
        "request_sha256": new_sha, "user_request": "用吧", "execution_mode": "direct_no_scheduler", "new_VASP_or_promotion_authorized": False})
    direct = {"document_kind": "adsorption_direct_force_training_trial", "run_id": RUN_ID, "exception_id": EXCEPTION,
        "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "remote_root": REMOTE, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 0, "gpu_uuid": exception["gpu_uuid"], "gpu_sharing": sharing, "max_wall_seconds": 1800,
        "per_arm_wall_seconds": 1800, "arms": ["control"], "original_comparison_sha256": exception["original_comparison_sha256"],
        "native_two_backward_check": True, "artifacts": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]}
    write_json_exclusive(PACKAGE / "direct_request.json", direct)
    digest = sha256_file(PACKAGE / "direct_request.json")
    write_json_exclusive(PACKAGE / "direct_authorization.json", {"user_authorized": True, "action": "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT",
        "user_request": "用吧", "request_sha256": digest, "source_scope_sha256": sha256_file(PACKAGE / "scope.md"), "checkpoint_promotion_authorized": False})
    verify(PACKAGE / "direct_request.json", digest)
    for relative in ["training_manifest.json", "train.db", "development.db", "train_metadata.npz", "development_metadata.npz"]:
        if sha256_file(ARM / relative) != sha256_file(OLD / "control" / relative):
            raise ValueError("physical dataset or sampling changed")
    write_json_exclusive(OUTPUT / "preparation_receipt.json", {"status": "AUTHORIZED_GPU0_BOUND_NOT_LAUNCHED",
        "previous_arm_request_sha256": OLD_ARM_SHA, "arm_request_sha256": new_sha, "direct_request_sha256": digest,
        "physical_dataset_and_budget_unchanged": True, "changed_runtime": CHANGED_RUNTIME, "training_started": False,
        "source_files": source_file_manifest([Path(__file__), AUTH, OUTPUT / "precheck.json", OUTPUT / "local_preflight.json",
            previous_policy, POLICY, PACKAGE / "direct_request.json", PACKAGE / "direct_authorization.json", ARM / "training_request.json"])})
    print({"status": "AUTHORIZED_GPU0_BOUND_NOT_LAUNCHED", "arm_request_sha256": new_sha, "direct_request_sha256": digest}, flush=True)


if __name__ == "__main__":
    prepare()
