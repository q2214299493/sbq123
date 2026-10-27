"""Verify authorized deployment and CPU preflight without claiming a GPU start."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from scripts.adsorption.direct_force_training import verify as native_verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .execute import ARM_SHA, BASE, OUTPUT, PACKAGE


def verify():
    for name in ["binding_receipt.json", "policy_addition_review.json", "status_after_cpu.json"]:
        if not source_file_manifest_valid(load_json_object(OUTPUT / name)):
            raise ValueError("deployment or status source binding changed")
    digest = sha256_file(PACKAGE / "direct_request.json")
    native_verify(PACKAGE / "direct_request.json", digest)
    if sha256_file(PACKAGE / "control/training_request.json") != ARM_SHA:
        raise ValueError("approved training request changed")
    status = load_json_object(OUTPUT / "status_after_cpu.json")
    cpu = status["records"]["preflight_control.json"]
    if (cpu["status"] != "PASS_NATIVE_PACKAGE_CPU" or cpu["request_sha256"] != digest
            or cpu["label_verdict"]["request_sha256"] != ARM_SHA or cpu["CUDA_initialized"]
            or cpu["model_instantiated"] or cpu["label_verdict"]["heldout_loader_created"]):
        raise ValueError("remote native CPU preflight does not match authorized scope")
    namespace = PurePosixPath(cpu["native_CLI"]["trainer_module"])
    if not namespace.is_relative_to(PurePosixPath("/home/ubuntu/hdd/sbq/sbq/fe110_force_training512_20261027_v1/control/runtime")):
        raise ValueError("native trainer namespace mismatch")
    if (status["producer"] or any(name != "preflight_control.json" for name in status["records"])
            or status["native_GPU_start_check"]["passed"] or (OUTPUT / "launch_reservation.json").exists()):
        raise ValueError("waiting-for-GPU checkpoint changed;review actual launch or resource state")
    manifest = BASE / "combined_force_package_20261027_v3/training_manifest.json"
    if sha256_file(manifest) != "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee":
        raise ValueError("source dataset changed")
    upload = json.loads((OUTPUT / "upload.stdout").read_text(encoding="utf-8"))
    if upload["status"] != "UPLOAD_COMPLETE" or upload["files"] != 1994:
        raise ValueError("unexpected upload receipt")
    result = {"status": "AUTHORIZED_DEPLOYED_CPU_PASS_WAITING_GPU", "uploaded_files": 1994,
        "arm_request_sha256": ARM_SHA, "direct_request_sha256": digest,
        "native_CPU_CLI_checkpoint_namespace_passed": True, "CUDA_initialized": False,
        "GPU_start_check": status["native_GPU_start_check"], "launch_attempted": False,
        "training_started": False, "training_pid": None, "scheduler_job_id": None,
        "dataset_splits_and_magnetic_levels_unchanged": True,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "binding_receipt.json", OUTPUT / "policy_addition_review.json",
            OUTPUT / "status_after_cpu.json", OUTPUT / "upload.stdout", OUTPUT / "upload.receipt.json",
            OUTPUT / "cpu_preflight.receipt.json", PACKAGE / "direct_request.json", manifest])}
    write_json_exclusive(OUTPUT / "submission_verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    verify()
