"""Exact twelve-seed shared-GPU scope; no production-model or DFT authority."""
MODEL_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
NAMES = [f"{species}_{letter}" for species in range(16, 20) for letter in "ABC"]


def verify_handoffs(root, scope):
    try:
        from scripts.aqcat25_handoff import validate_handoff
    except ModuleNotFoundError:
        from aqcat25_handoff import validate_handoff
    for case in scope["cases"]:
        validate_handoff(root / "handoffs" / (case["name"] + ".json"),
                         root=root, schema_path=root / "handoff.schema.json")


def check_scope(request):
    scope = request["scope"]
    if (request.get("document_kind") != "fe110_c2_16_19_ft512_relaxation"
            or list(scope["models"]) != ["finetune"]
            or [r["name"] for r in scope["cases"]] != NAMES
            or scope["models"]["finetune"]["sha256"] != MODEL_SHA):
        raise ValueError("twelve frozen seeds/checkpoint changed")
    if (scope["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2}
            or scope["max_wall_seconds"] != 600 or scope["CPU_count"] != 4 or scope["memory_GB"] != 32
            or scope.get("allocator_limit_MiB") != 16384 or scope["gpu_index"] != 0
            or scope["gpu_uuid"] != "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75"):
        raise ValueError("shared GPU/optimizer resource budget changed")
    sharing = scope.get("gpu_sharing", {})
    if sharing.get("mode") != "resident_service_allowlist" or sharing.get("max_training_memory_MiB") != 16384:
        raise ValueError("explicit limited-sharing contract missing")
    if request["boundaries"] != {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}:
        raise ValueError("ML stage cannot train, promote or submit DFT")
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("scheduler identity must remain absent")
    if request["domain"] != {"status": "out_of_calibrated_domain", "adsorbate_atoms": [7, 8],
            "use": "candidate_pre_relaxation_only", "ranking_allowed": False}:
        raise ValueError("uncalibrated domain status or permitted use changed")
