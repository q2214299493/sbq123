"""Verify the prepared same-start pilot and CPU interfaces;never grant execution."""
from pathlib import Path

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .prepare_speed import EXCEPTION, OUTPUT, PACKAGE, ROOT
from .relaxation_adapter import MODEL_SHA, SEED_SHA, check_scope


def review():
    plan = load_json_object(OUTPUT / "plan.json")
    request = load_json_object(PACKAGE / "request.json")
    if not source_file_manifest_valid(plan) or plan["request_sha256"] != sha256_file(PACKAGE / "request.json"):
        raise ValueError("prepared evidence binding changed")
    check_scope(request)
    for row in request["artifacts"]:
        if sha256_file(PACKAGE / row["path"]) != row["sha256"]:
            raise ValueError("prepared artifact changed:" + row["path"])
    auth = load_json_object(PACKAGE / "authorization.json")
    if auth["user_authorized"] is not False or auth["request_sha256"] != plan["request_sha256"]:
        raise ValueError("preparation cannot manufacture execution approval")
    policy = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))
    if EXCEPTION in policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("proposal has already been activated;review its actual authorization")
    native_nequip = load_json_object(OUTPUT / "native_nequip_cpu_interface.json")
    native_ft = load_json_object(OUTPUT / "native_finetune_cpu_interface.json")
    for name, record in [("nequip", native_nequip), ("finetune", native_ft)]:
        if (record["model_sha256"] != MODEL_SHA[name] or record["model_device"] != "cpu"
                or record["CUDA_initialized"] is not False or record["optimizer_steps"] != 0):
            raise ValueError("CPU interface/model binding changed")
        for case in record["cases"]:
            forces = np.asarray(case["raw_forces_eV_A"])
            if (case["POSCAR_sha256"] != SEED_SHA[case["name"]] or not case["coordinates_unchanged"]
                    or not np.isfinite(forces).all() or list(forces.shape) != case["shape"]):
                raise ValueError("fixed-origin CPU force interface failed")
    if any(native_nequip["packages"][key] != native_ft["packages"][key] for key in ["torch", "ase", "e3nn"]):
        raise ValueError("native optimizer/framework versions differ")
    local_path = OUTPUT.parent / "scratch512_speed2_20261028_v1/cpu_nequip_interface.json"
    local = load_json_object(local_path)
    deltas = [float(np.max(abs(np.asarray(a["raw_forces_eV_A"])-np.asarray(b["raw_forces_eV_A"]))))
        for a, b in zip(local["cases"], native_nequip["cases"], strict=True)]
    result = {"status": "READY_FOR_EXACT_GPU_BUDGET_CONFIRMATION_NOT_STARTED", "request_sha256": plan["request_sha256"],
        "bound_artifacts_verified": len(request["artifacts"]), "native_CPU_interfaces": "both models/two unchanged origins/finite raw forces",
        "local_vs_native_NequIP_max_force_component_differences_eV_A": deltas,
        "native_common_versions": {key: native_nequip["packages"][key] for key in ["torch", "ase", "e3nn"]},
        "GPU_max_seconds": 600, "ML_relaxations": 4, "GPU_training_or_optimization_started": False,
        "new_DFT_submitted": False, "canonical_policy_changed": False, "execution_authorized": False,
        "note": "The first FT CPU adapter attempt failed before inference because config_yml flattens dataset;only the debug config copy was wrapped,weights unchanged",
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "plan.json", PACKAGE / "request.json", PACKAGE / "authorization.json",
            OUTPUT / "native_nequip_cpu_interface.json", OUTPUT / "native_finetune_cpu_interface.json", local_path, OUTPUT / "related_tests.xml"])}
    write_json_exclusive(OUTPUT / "readiness_review.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    review()
