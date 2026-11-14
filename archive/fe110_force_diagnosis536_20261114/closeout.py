"""Record a truthful partial diagnosis and frozen-input guards while GPU is offline."""
from __future__ import annotations

from pathlib import Path

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .prepare import BASE, OUT, ROOT


def run():
    context = load_json_object(OUT / "request_context.json")
    labels = load_json_object(OUT / "qualified_reference_labels.json")
    scope = load_json_object(OUT / "prediction_scope.json")
    cached = load_json_object(OUT / "cached_development_role_metrics.json")
    old_candidates_path = BASE / "c2_c4_joint_candidates_20261114_v1/single_point_candidates_and_budget_v2.json"
    old_candidates = load_json_object(old_candidates_path)["selected"]
    decisions = [{"candidate_id": r["candidate_id"], "structure_sha256": r["source_sha256"], "composition": r["composition"],
                  "decision": "DEFER_NEW_DFT_SELECTION_PENDING_ACTUAL_FIXED_STRUCTURE_ERROR_DIAGNOSIS",
                  "frozen536_same_coordinate_error": None, "reason": "cached development role means do not establish error at an unlabelled candidate",
                  "execution_or_budget_authorization": False} for r in old_candidates]
    write_json_exclusive(OUT / "new_DFT_selection_status.json", {"decisions": decisions,
        "status": "NO_NEW_DFT_SELECTED_OR_SUBMITTED", "existing_labels_should_be_used_first": True,
        "source_files": source_file_manifest([old_candidates_path, OUT / "cached_development_role_metrics.json", Path(__file__)])})
    request_ids = {r["sample_id"] for r in scope["samples"]}
    expected_ids = {r["sample_id"] for r in labels["records"]}
    checks = {"614_train_development_only_ids_bound": len(request_ids) == 614 and request_ids == expected_ids and all(r["partition"] in {"train", "development"} for r in labels["records"]),
              "303_strict_and311_original_scopes_preserved": sum(r["qualification_scope"] == "STRICT_RAW_E_F_LOCALMAG" for r in labels["records"]) == 303,
              "cached78_native_development_metrics_not_new_predictions": cached["frames"] == 78 and cached["new_predictions"] == 0,
              "native_checkpoint_matches_frozen_SHA": sha256_file(Path(context["model_path"])) == context["model_sha256"],
              "frozen512_536_twelve_input_hashes_unchanged": frozen_hashes() == context["frozen_hashes_before"],
              "current_task_unchanged": sha256_file(ROOT / "tasks/current_task.md") == context["current_task_sha256"],
              "registry_unchanged": sha256_file(ROOT / "data/project_registry.sqlite3") == context["registry_sha256"],
              "backend_policy_unchanged": sha256_file(ROOT / "configs/execution_backends.yaml") == context["backend_policy_sha256"],
              "method_protocol_unchanged": sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md") == context["method_protocol_sha256"],
              "no_full_diagnosis_fabricated_without_vectors": not (OUT / "full_fixed_structure_force_diagnosis.json").exists(),
              "new_DFT_selected_zero": all(not r["execution_or_budget_authorization"] for r in decisions)}
    names = ["qualified_reference_labels.json", "prediction_scope.json", "cached_development_role_metrics.json", "plot_binding.json", "new_DFT_selection_status.json"]
    bound_checks = {name: source_file_manifest_valid(load_json_object(OUT / name)) for name in names}
    checks["current_source_bindings_valid"] = all(bound_checks.values())
    result = {"status": "PARTIAL_CACHE_DIAGNOSIS_FIXED_VECTOR_PREDICTION_BLOCKED", "scientific_task_complete": False,
              "integrity_checks_passed": all(checks.values()), "checks": checks, "binding_checks": bound_checks,
              "fresh_prediction_frames": 0, "native_development_cache_frames": 78,
              "blocker": "both configured GPU SSH services close before authentication;resource and native environment check unavailable",
              "local_CPU_native_inference_environment": "Fairchem/e3nn/torch_scatter absent;metadata inspection only completed in existing care_fe110_ft",
              "remaining": ["fresh GPU/native-environment/checkpoint/geometry preflight", "reuse any compatible existing remote vector cache or predict614fixed frames",
                            "train/development and strict/legacy stage/element error analysis", "then assess new single-point value"],
              "no_training_DFT_relaxation_heldout_inference_or_model_promotion": True,
              "source_files": source_file_manifest([OUT / n for n in names] + [OUT / "request_context.json", OUT / "gpu_resource_receipt.json", OUT / "ssh_handshake_receipt.json", Path(__file__)])}
    write_json_exclusive(OUT / "final_state.json", result)
    print({"status": result["status"], "integrity_checks_passed": result["integrity_checks_passed"], "checks": checks}, flush=True)
    if not result["integrity_checks_passed"]:
        raise ValueError("input-integrity validation failed")


if __name__ == "__main__":
    run()
