"""Review returned terminal evidence and stored metrics without model inference."""
from datetime import datetime
import math
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect_results import RUN
from .prepare import MANIFEST_SHA
from .probe import OUTPUT


def require(condition, message):
    if not condition:
        raise ValueError(message)


def duration(record, start, finish):
    seconds = (datetime.fromisoformat(record[finish]) - datetime.fromisoformat(record[start])).total_seconds()
    require(seconds > 0, "nonpositive recorded duration")
    return seconds


def review():
    recovery = OUTPUT / "terminal_recovery_20261028_v3"
    returned, package = recovery / "returned", OUTPUT / "package"
    manifest = load_json_object(recovery / "manifest.json")
    require(manifest["CUDA_initialized"] is False and manifest["new_training_or_inference"] is False,
        "recovery must remain CPU-only metadata inspection")
    require(manifest["checkpoint_promotion"] is False and manifest["missing_FT_completed_marker"] is True,
        "partial FT must not become a completed or promoted model")
    for row in manifest["files"]:
        path = returned / row["path"]
        require(path.stat().st_size == row["bytes"] and sha256_file(path) == row["sha256"], "returned bytes changed")
    frozen = ["sequence_request.json", "sequence_authorization.json", "nequip_v2/training_request.json",
        "nequip_v2/config_reviewed.yaml", "finetune/direct_request.json", "finetune/control/training_request.json",
        "finetune/control/config.yml"]
    for name in frozen:
        require(sha256_file(returned / name) == sha256_file(package / name), "frozen input binding changed:" + name)
    sequence = load_json_object(returned / "sequence_exit.json")
    request = load_json_object(package / "sequence_request.json")
    nequip_request = load_json_object(package / "nequip_v2/training_request.json")
    finetune_request = load_json_object(package / "finetune/control/training_request.json")
    require(nequip_request["source_manifest_sha256"] == MANIFEST_SHA, "scratch source changed")
    require(nequip_request["counts"] == {"train": 512, "development": 78}
        and finetune_request["split_counts"] == {"train": 512, "development": 78, "heldout": 53}, "split changed")
    for directory, model_request, config in [("nequip_v2", nequip_request, "config_reviewed.yaml"),
                                           ("finetune/control", finetune_request, "config.yml")]:
        artifact = next(row for row in model_request["artifacts"] if row["path"] == config)
        require(sha256_file(returned / directory / config) == artifact["sha256"], "config/request binding changed")
    require(sequence["request_sha256"] == sha256_file(package / "sequence_request.json") == sha256_file(returned / "sequence_request.json"),
        "sequence terminal receipt mismatch")
    scratch = load_json_object(returned / "nequip_v2/producer_exit_record.json")
    finetune = load_json_object(returned / "finetune/direct_batch_exit_record.json")
    require(scratch["request_sha256"] == sha256_file(package / "nequip_v2/training_request.json")
        and scratch["exit_code"] == 0, "scratch producer did not exit normally")
    require(finetune["request_sha256"] == sha256_file(package / "finetune/direct_request.json")
        and finetune["exit_code"] == 1 and "walltime exhausted" in finetune["reason"], "FT terminal classification changed")
    require(sequence["exit_code"] == 1 and sequence["checkpoint_promoted"] is False, "sequence status changed")
    run = returned / "finetune/control/output" / RUN
    scratch_device = load_json_object(returned / "nequip_v2/output/model_device.json")
    ft_device = load_json_object(run / "execution_device.json")
    require(scratch_device["physical_gpu_uuid"] == ft_device["physical_gpu_uuid"] == request["gpu_uuid"], "physical GPU mismatch")
    require(scratch_device["device"] == ft_device["model_device"] == "cuda:0"
        and ft_device["actual_model_parameters_cuda"] is True, "actual CUDA model evidence missing")
    witness = load_json_object(run / "native_two_backward_check.json")
    require(witness["status"] == "PASS_NATIVE_CUDA_TWO_BACKWARDS"
        and witness["request_sha256"] == finetune["request_sha256"] and witness["same_training_process"] is True
        and witness["extra_training_steps"] == 0 and witness["optimizer_reset"] is False, "native FT training witness changed")
    models = manifest["models"]
    require(all(item["finite_model_tensors"] is True for item in models.values()), "nonfinite checkpoint state")
    nequip = models["nequip_best"]
    callbacks = [v for v in nequip["callbacks"].values() if isinstance(v, dict) and "best_model_score" in v]
    require(len(callbacks) == 1 and callbacks[0]["monitor"] == "val0_epoch/movable_force_vector_mae", "scratch development criterion changed")
    scratch_score = callbacks[0]["best_model_score"]
    ft_score = models["finetune_best"]["metadata"]["val_metrics"]["forces_role_vector_mae"]
    require(ft_score["numel"] == 78 and all(math.isfinite(x) and x >= 0 for x in [scratch_score, ft_score["metric"]]),
        "invalid development metric/count")
    seconds = {"nequip_producer": duration(scratch, "started_utc", "finished_utc"),
        "finetune_controller": duration(finetune, "started_at", "finished_at"),
        "sequence_wall": duration(sequence, "started_utc", "finished_utc")}
    require(seconds["sequence_wall"] < request["total_GPU_seconds"], "total sequence budget exceeded")
    candidates = {name: {"path": row["path"], "sha256": sha256_file(returned / row["path"]),
        "kind": row["kind"], "saved_metadata": row["metadata"]} for name, row in models.items() if name != "finetune_last_saved"}
    result = {"status": "REVIEWED_NEQUIP_NORMAL_EXIT_FT_BUDGET_STOP_NO_PROMOTION", "files_verified": len(manifest["files"]),
        "sequence_sha256": sequence["request_sha256"], "source_manifest_sha256": MANIFEST_SHA, "candidates": candidates,
        "development_role_weighted_force_vector_MAE_eV_A": {"nequip": scratch_score, "finetune_partial": ft_score["metric"]},
        "finetune_last_saved_metadata_not_final_iteration": models["finetune_last_saved"]["metadata"], "recorded_seconds": seconds,
        "finetune_elapsed_over_1800_seconds_including_teardown": seconds["finetune_controller"] - 1800,
        "nequip_final_epoch_and_stop_reason": "Not established by best/last snapshots or terminal log;do not equate normal exit with100epochs",
        "development_only_comparison": True, "independent_accuracy_or_acceleration_proved": False,
        "new_inference_or_training": False, "model_promotion": False,
        "source_files": source_file_manifest([recovery / "manifest.json", recovery / "collection.json", *[returned / name for name in frozen],
            returned / "sequence_exit.json", returned / "nequip_v2/producer_exit_record.json", returned / "finetune/direct_batch_exit_record.json", Path(__file__)])}
    write_json_exclusive(OUTPUT / "terminal_review_20261028.json", result)
    print({k: result[k] for k in ["status", "files_verified", "development_role_weighted_force_vector_MAE_eV_A", "recorded_seconds",
        "finetune_elapsed_over_1800_seconds_including_teardown"]}, flush=True)


if __name__ == "__main__":
    review()
