"""One user-requested 15-seed AQCat25 batch, bounded and never a DFT executor."""
MODEL_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
NAMES = [f"{species}_{letter}" for species in range(11, 16) for letter in "ABC"]


def check_scope(request):
    scope = request["scope"]
    if (request.get("document_kind") != "fe110_c2_11_15_ft512_relaxation"
            or list(scope["models"]) != ["finetune"]
            or [row["name"] for row in scope["cases"]] != NAMES
            or scope["models"]["finetune"]["sha256"] != MODEL_SHA):
        raise ValueError("frozen fifteen-seed/checkpoint scope changed")
    if (scope["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2}
            or scope["max_wall_seconds"] != 600 or scope["CPU_count"] != 4
            or scope["memory_GB"] != 32 or scope.get("allocator_limit_MiB") != 16384
            or scope["gpu_index"] != 1 or scope["gpu_uuid"] != "GPU-450609b3-d1fd-ac33-d03a-79891be402da"
            or "gpu_sharing" in scope):
        raise ValueError("fifteen-seed exclusive GPU/optimizer budget changed")
    if request["boundaries"] != {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}:
        raise ValueError("ML stage cannot train, promote or submit VASP")
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("no fabricated scheduler identity")
