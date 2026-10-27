"""Review native success and frozen candidate provenance;not independent accuracy."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.adsorption.direct_force_training import verify as verify_execution
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .prepare import OLD, OUTPUT, PACKAGE, RUN_ID


def verify_producer(snapshot, digest):
    batch = snapshot["records"]["direct_batch_exit_record.json"]
    producer = snapshot["producer"]
    if batch["exit_code"] != 0 or batch["request_sha256"] != digest or batch["completed_arms"] != ["control"]:
        raise ValueError("native batch did not complete the authorized single arm")
    if producer["producer_exit_record.json"]["exit_code"] != 0 or producer["training_completed.json"]["optimizer_steps"] != 1024:
        raise ValueError("producer exit or native iteration count mismatch")
    device = producer["execution_device.json"]
    if device["physical_gpu_uuid"] != "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75" or not device["actual_model_parameters_cuda"]:
        raise ValueError("actual model CUDA binding was not proved")
    if producer["cuda_allocator_budget.json"]["max_training_memory_MiB"] != 16384:
        raise ValueError("shared GPU allocator budget changed")
    startup = producer["native_two_backward_check.json"]
    if startup["status"] != "PASS_NATIVE_CUDA_TWO_BACKWARDS" or startup["request_sha256"] != digest:
        raise ValueError("same-process native backward proof missing")
    elapsed = (datetime.fromisoformat(producer["producer_exit_record.json"]["finished_at"])
               - datetime.fromisoformat(producer["started.json"]["started_at"])).total_seconds()
    if not 0 < elapsed <= 1800:
        raise ValueError("authorized producer walltime exceeded")
    return elapsed


def verify():
    names = ["preparation_receipt.json", "input_changes_review.json", "retirement_receipt.json",
             "status_completion_check.json", "collection_receipt.json", "postrun_resource_review.json", "candidate_development_metrics.json"]
    for name in names:
        if not source_file_manifest_valid(load_json_object(OUTPUT / name)):
            raise ValueError("changed training,collection or resource evidence: " + name)
    digest = sha256_file(PACKAGE / "direct_request.json")
    verify_execution(PACKAGE / "direct_request.json", digest)
    snapshot = load_json_object(OUTPUT / "status_completion_check.json")
    elapsed = verify_producer(snapshot, digest)
    approved = {row["pid"] for row in load_json_object(PACKAGE / "direct_request.json")["gpu_sharing"]["allowed_processes"]}
    observed = {int(line.split(",")[1]) for line in snapshot["GPU_processes"].splitlines()
                if line.split(",")[0].strip() == "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75"}
    if not approved <= observed:
        raise ValueError("a reviewed resident service is absent from the completion snapshot")
    collection = load_json_object(OUTPUT / "collection_receipt.json")
    candidate = OUTPUT / "returned/control/output" / RUN_ID / "candidate.pt"
    if sha256_file(candidate) != collection["candidate_sha256"] or collection["files_verified"] != 13:
        raise ValueError("candidate or returned source files changed")
    if (OLD / "direct_authorization.json").exists() or not (OLD / "direct_authorization.retired_for_gpu0.json").is_file():
        raise ValueError("superseded GPU1 authorization remains launchable")
    resource = load_json_object(OUTPUT / "postrun_resource_review.json")
    if not resource["approved_resident_identities_still_match"] or not resource["old_gpu1_launch_marker_absent"]:
        raise ValueError("postrun shared service or single-run check failed")
    result = {"status": "TRAINING_SUCCEEDED_CANDIDATE_FROZEN_NOT_INDEPENDENTLY_VALIDATED",
        "direct_request_sha256": digest, "native_training_iterations": 1024, "epochs": 2,
        "producer_elapsed_seconds": elapsed, "producer_exit_code": 0,
        "candidate_sha256": collection["candidate_sha256"], "candidate_path": str(candidate), "returned_files_verified": 13,
        "actual_model_GPU0_and_two_native_updates_proved": True,
        "full_actual_optimizer_update_count_not_separately_reported": True,
        "approved_resident_process_identities_preserved": True, "service_response_performance_measured": False,
        "heldout_inference_run": False, "model_promoted": False, "DFT_acceleration_established": False,
        "source_files": source_file_manifest([Path(__file__), *[OUTPUT / name for name in names], candidate])}
    write_json_exclusive(OUTPUT / "independent_verification_v2.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    verify()
