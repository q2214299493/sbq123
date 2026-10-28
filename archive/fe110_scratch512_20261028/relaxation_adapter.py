"""Pinned NequIP ASE adapter and exact scope for the frozen512 speed pilot."""
from importlib.metadata import version
from pathlib import Path

from scripts.artifact_io import sha256_file

KIND = "fe110_scratch512_paired_relaxation"
MODEL_SHA = {"nequip": "a444a7e3747296a06cdd6dfc953e510f08200d533948e2c50804b9556b53bb17",
    "finetune": "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"}
SEED_SHA = {"10_A": "04990eb8ae6dc84d9626dd0480220201664499f79c389d1c6070081325497d4b",
    "C3_05": "6ed0169ab43c93e3b53092ea2bc76a5179f833752e9f1ccb0eabc61b76a63868"}
PYTHONS = {"nequip": "/home/sbq/sbq/fe110_scratch512_env_20261028_v4/venv/bin/python",
    "finetune": "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"}


def check_scope(request):
    scope = request["scope"]
    if (request.get("document_kind") != KIND or set(scope["models"]) != set(MODEL_SHA)
            or [c["name"] for c in scope["cases"]] != list(SEED_SHA)):
        raise ValueError("frozen512 model/seed set changed")
    for name, model in scope["models"].items():
        if model["sha256"] != MODEL_SHA[name] or model["backend"] != ("nequip" if name == "nequip" else "aqcat25"):
            raise ValueError("frozen512 checkpoint/backend changed")
    for case in scope["cases"]:
        if case["seed_sha256"] != SEED_SHA[case["name"]]:
            raise ValueError("frozen common seed changed")
    if (scope["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.2}
            or scope["max_wall_seconds"] != 600 or scope["CPU_count"] != 4 or scope["memory_GB"] != 32
            or scope.get("allocator_limit_MiB") != 16384 or "gpu_sharing" in scope
            or scope.get("model_pythons") != PYTHONS
            or scope["gpu_index"] != 1 or scope["gpu_uuid"] != "GPU-450609b3-d1fd-ac33-d03a-79891be402da"):
        raise ValueError("frozen512 exclusive GPU/optimizer/budget changed")
    if request["boundaries"] != {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}:
        raise ValueError("ML comparison cannot train,promote or submitDFT")
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("direct execution cannot invent scheduler identity")


def nequip_calculator(path, expected_sha, device):
    if version("nequip") != "0.19.1" or sha256_file(path) != expected_sha:
        raise ValueError("pinned NequIP/checkpoint changed")
    from nequip.integrations.ase import NequIPCalculator
    calculator = NequIPCalculator._from_saved_model(str(path), device=device, compile_mode="eager",
        energy_units_to_eV=1.0, length_units_to_A=1.0)
    if sum(p.numel() for p in calculator.model.parameters()) != 216736:
        raise ValueError("unexpected NequIP model size")
    return calculator


def sequence(path):
    """Keep each model in its proven dependency environment under one600s guard."""
    from datetime import datetime, timezone
    import os
    import subprocess
    import time
    from archive.fe110_pair2_20261027.runtime import verify
    from scripts.artifact_io import write_json_exclusive
    _, root, scope = verify(path, remote=True)
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + scope["max_wall_seconds"]
    code, error = 1, None
    try:
        for name in scope["models"]:
            command = [scope["model_pythons"][name], "-m", "archive.fe110_scratch512_20261028.relaxation_adapter",
                "--request", str(path), "--model", name]
            with (root / "output" / (name + "_worker.log")).open("xb") as log:
                # Same process group as the existing guarded worker:timeout cleanup covers children.
                result = subprocess.run(command, cwd=root, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT,
                    timeout=max(.01, deadline-time.monotonic()), check=False)
            if result.returncode:
                raise RuntimeError(name + " model process failed;no retry")
        code = 0
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        write_json_exclusive(root / "output/producer_exit_record.json", {"exit_code": code, "error": error,
            "pid": os.getpid(), "request_sha256": sha256_file(path), "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(), "training_performed": False,
            "model_promoted": False, "VASP_submitted": False, "scheduler_job_id": None})


def model_worker(path, name):
    import gc
    import os
    import time
    import torch
    from archive.fe110_pair2_20261027.runtime import verify
    from archive.fe110_adsorption_validation_20261018.runtime import relax_case
    from scripts.adsorption.direct_gpu_batch import cuda_binding, gpu_available
    from scripts.artifact_io import write_json_exclusive
    _, root, scope = verify(path, remote=True)
    if name not in scope["models"] or os.environ.get("CUDA_VISIBLE_DEVICES") != scope["gpu_uuid"]:
        raise ValueError("model/physicalGPU scope mismatch")
    gpu_available(scope)
    torch.set_num_threads(4)
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(scope["allocator_limit_MiB"]*1024**2/total)
    model = scope["models"][name]
    if name == "nequip":
        calc = nequip_calculator(Path(model["path"]), model["sha256"], "cuda:0")
    else:
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        calc = patched_calc(checkpoint_path=model["path"], is_spin_off=False, is_low_fi=False, cpu=False)
    write_json_exclusive(root / "output" / (name + "_device.json"), cuda_binding(calc))
    deadline = time.monotonic() + scope["max_wall_seconds"]
    rows = [relax_case(root, root / "output" / name, case, "seed", calc, scope["limits"], deadline) for case in scope["cases"]]
    write_json_exclusive(root / "output" / (name + "_cases.json"), {"checkpoint_sha256": model["sha256"], "cases": rows})
    del calc
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--model", choices=list(MODEL_SHA), required=True)
    arguments = parser.parse_args()
    model_worker(arguments.request, arguments.model)
