"""Independently verify the prepared512-frame trial without running a model."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .prepare import ARM, BASE_MODEL, MANIFEST_SHA, OUTPUT, PACKAGE, ROOT, SOURCE, TEMPLATE


def differences(left, right, prefix=""):
    if isinstance(left, dict) and isinstance(right, dict):
        result = set()
        for key in left.keys() | right.keys():
            name = prefix + "." + key if prefix else key
            if key not in left or key not in right:
                result.add(name)
            else:
                result |= differences(left[key], right[key], name)
        return result
    return set() if left == right else {prefix}


def check_execution_state(request_sha):
    for parent in [PACKAGE, ARM]:
        for name in ["direct_request.json", "direct_authorization.json", "direct_arm_authorization.json", "direct_launch_marker.json"]:
            if (parent / name).exists():
                raise ValueError("this preparation must remain unauthorized and unlaunched")
    cpu_raw = load_json_object(OUTPUT / "checkpoint_cpu_probe.json")
    if cpu_raw.get("returncode") != 0:
        raise ValueError("remote CPU architecture check incomplete")
    cpu = json.loads(cpu_raw["stdout"])
    if cpu["checkpoint_sha256"] != BASE_MODEL["sha256"] or not cpu["architecture_matches"] or cpu["CUDA_initialized"]:
        raise ValueError("remote base model architecture/hash/CUDA check failed")
    probe_raw = load_json_object(OUTPUT / "remote_probe.json")
    probe = json.loads(probe_raw["stdout"])
    if probe["host"] != "MZ73" or probe["target_exists"]:
        raise ValueError("remote host or target check failed")
    proposal = load_json_object(OUTPUT / "execution_policy_proposal.json")
    if proposal["arm_request_sha256"] != {"control": request_sha}:
        raise ValueError("one-model proposal changed")
    return proposal["gpu_uuid"] in probe["processes"]["stdout"]


def verify():
    receipt = load_json_object(OUTPUT / "preparation_receipt.json")
    if not source_file_manifest_valid(receipt):
        raise ValueError("prepared source bindings changed")
    request = load_json_object(ARM / "training_request.json")
    if sha256_file(ARM / "training_request.json") != receipt["training_request_sha256"]:
        raise ValueError("request changed")
    if request["base_checkpoint"] != BASE_MODEL or request["training_authorized"] is not False:
        raise ValueError("base model or authorization changed")
    for row in request["artifacts"]:
        path = (ARM / row["path"]).resolve()
        if not path.is_relative_to(ARM.resolve()) or sha256_file(path) != row["sha256"]:
            raise ValueError("bound package artifact changed")
    if sha256_file(SOURCE / "training_manifest.json") != MANIFEST_SHA or sha256_file(ARM / "training_manifest.json") != MANIFEST_SHA:
        raise ValueError("dataset manifest changed")
    inventory = load_json_object(SOURCE / "package_inventory.json")
    for row in inventory["files"]:
        if sha256_file(ARM / row["path"]) != row["sha256"]:
            raise ValueError("physical dataset copy changed")
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    config = yaml.safe_load((ARM / "config.yml").read_text(encoding="utf-8"))
    allowed = {"optim.eval_every", "optim.checkpoint_every", "dataset.train.src", "dataset.train.metadata_path",
               "dataset.val.src", "dataset.val.metadata_path"}
    if differences(template, config) != allowed:
        raise ValueError("unexpected config differences")
    local = load_json_object(OUTPUT / "local_preflight.json")
    if local["request_sha256"] != receipt["training_request_sha256"] or local["counts"] != request["split_counts"]:
        raise ValueError("native package preflight not bound to current request")
    if set(config["dataset"]) != {"train", "val"} or (ARM / "heldout.db").exists():
        raise ValueError("heldout loader created")
    gpu_busy = check_execution_state(receipt["training_request_sha256"])
    result = {"status": "PASS_PREPARED_NO_MODEL_RUN", "copied_source_inventory_files_verified": len(inventory["files"]),
        "bound_artifacts_verified": len(request["artifacts"]), "dataset_manifest_bytes_unchanged": True,
        "configuration_changes": sorted(allowed), "remote_original_checkpoint_CPU_architecture_verified": True,
        "GPU1_has_existing_process_at_probe": gpu_busy,
        "native_on_disk_new_package_CLI_check_done": False, "execution_authorization_created": False,
        "model_evaluation_run": False, "GPU_training_started": False,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "preparation_receipt.json", OUTPUT / "local_preflight.json",
            OUTPUT / "validation_plan.json", OUTPUT / "remote_probe.json", OUTPUT / "checkpoint_cpu_probe.json",
            ARM / "training_request.json", ROOT / "scripts/adsorption/direct_force_training.py"])}
    write_json_exclusive(OUTPUT / "independent_verification_v2.json", result)
    print({k: v for k, v in result.items() if k != "source_files"})


if __name__ == "__main__":
    verify()
