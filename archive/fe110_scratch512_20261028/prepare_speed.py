"""Prepare frozen same-start speed comparison;no policy activation or execution."""
import base64
import io
from pathlib import Path
import shutil

import numpy as np
from ase.io import read
import yaml

from archive.fe110_pair2_20261027.prepare import PACKAGE as PREVIOUS
from archive.fe110_pair2_20261027.prepare_dft import cost_reference
from archive.fe110_pair2_20261027.runtime import check_scope as execution_scope
from archive.fe110_training512_20261027.prepare import RUNTIME
from scripts.artifact_io import load_json_object, sha256_bytes, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .environment import ENV_ROOT
from .prepare import MANIFEST_SHA, REMOTE as TRAINING_REMOTE
from .probe import OUTPUT as TRAINING_OUTPUT, ROOT
from .relaxation_adapter import KIND, MODEL_SHA, PYTHONS, SEED_SHA, check_scope

OUTPUT = TRAINING_OUTPUT.parent / "scratch512_speed2_20261028_v2"
PACKAGE = OUTPUT / "package"
REMOTE = "/home/sbq/sbq/fe110_scratch512_speed2_20261028_v2"
EXCEPTION = "fe110_scratch512_speed2_20261028"
QUOTE = "从完全相同的C₂/C₃起点出发，各自进行ML优化，再交给相同设置的VASP，比较达到同一终态和0.02 eV/Å标准所需的离子步、SCF次数及核时。"


def baseline_audit(seed):
    source = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_pool_rebuild_20261019_v1/raw/10_A/attempt_v2/source.json"
    previous = load_json_object(source)
    raw = base64.b64decode(previous["files"]["POSCAR"], validate=True)
    historical = read(io.StringIO(raw.decode()), format="vasp")
    current = read(seed, format="vasp")
    exact = (historical.get_chemical_symbols() == current.get_chemical_symbols()
        and np.allclose(historical.cell, current.cell, rtol=0, atol=1e-12)
        and np.allclose(historical.positions, current.positions, rtol=0, atol=1e-12))
    return {"historical_C2_job_id": previous["record"]["job_id"], "historical_steps": previous["total_steps"],
        "historical_POSCAR_sha256": sha256_bytes(raw), "common_seed_sha256": sha256_file(seed),
        "exact_same_coordinates": bool(exact), "eligible_as_exact_pure_DFT_baseline": bool(exact),
        "maximum_unaligned_cartesian_difference_A": float(abs(historical.positions-current.positions).max()),
        "C3_pure_DFT_same_start_reference": "Not identified in the frozen paired source evidence;previous ML-fragment endpoints are not a direct baseline",
        "source_files": source_file_manifest([source, seed])}


def prepare():
    if OUTPUT.exists():
        raise FileExistsError("preserve previous speed pilot preparation")
    reviewed_path = TRAINING_OUTPUT / "terminal_review_20261028.json"
    reviewed = load_json_object(reviewed_path)
    if not source_file_manifest_valid(reviewed) or reviewed["source_manifest_sha256"] != MANIFEST_SHA:
        raise ValueError("frozen training review source changed")
    selection_path = PREVIOUS / "evidence/selection.json"
    selection = load_json_object(selection_path)
    if not source_file_manifest_valid(selection):
        raise ValueError("previous seed/split review source changed")
    models = {}
    for name, key in [("nequip", "nequip_best"), ("finetune", "finetune_best")]:
        candidate = reviewed["candidates"][key]
        if candidate["sha256"] != MODEL_SHA[name]:
            raise ValueError("candidate was reselected")
        models[name] = {"path": TRAINING_REMOTE + "/" + candidate["path"], "sha256": candidate["sha256"],
            "backend": "nequip" if name == "nequip" else "aqcat25", "status": candidate["kind"]}
    PACKAGE.mkdir(parents=True)
    cases = []
    for case in selection["cases"]:
        if case["seed_sha256"] != SEED_SHA[case["name"]] or sha256_file(ROOT / case["seed_source_path"]) != case["seed_sha256"]:
            raise ValueError("preselected common origin changed")
        target = PACKAGE / case["seed_path"]
        target.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / case["seed_source_path"], target)
        cases.append({k: case[k] for k in ["name", "composition", "seed_path", "seed_sha256"]})
    evidence = PACKAGE / "evidence"
    evidence.mkdir()
    shutil.copyfile(selection_path, evidence / "selection.json")
    shutil.copyfile(reviewed_path, evidence / "training_terminal_review.json")
    write_json_exclusive(evidence / "frozen_force_comparison.json", {"model_checkpoint_sha256": MODEL_SHA,
        "training_review_sha256": sha256_file(reviewed_path), "selection_not_based_on_future_optimization": True})
    write_json_exclusive(evidence / "direct_DFT_baseline_audit.json", baseline_audit(PACKAGE / "geometry/10_A/POSCAR"))
    runtime = [*RUNTIME, "archive/fe110_pair2_20261027/runtime.py", "archive/fe110_scratch512_20261028/relaxation_adapter.py",
        "archive/fe110_adsorption_validation_20261018/runtime.py", "archive/fe110_adsorption_validation_20261018/validation_helpers.py",
        "scripts/adsorption/nequip_force_runtime.py"]
    for name in dict.fromkeys(runtime):
        target = PACKAGE / "runtime" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    scope = {"remote_root": REMOTE, "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da",
        "max_wall_seconds": 600, "CPU_count": 4, "memory_GB": 32, "allocator_limit_MiB": 16384,
        "models": models, "model_pythons": PYTHONS, "cases": cases,
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.2}}
    exception = {"scope": scope, "authorizing_user_request": QUOTE, "canonical_remote_boundary": "/home/ubuntu/hdd/sbq/sbq",
        "automatic_retries": 0, "VASP_submission_authority": False, "budget_confirmation": "PENDING_EXACT_10_GPU_MINUTE_APPROVAL"}
    original = (ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8")
    marker = "    direct_execution_exceptions:\n"
    if original.count(marker) != 1 or EXCEPTION in yaml.safe_load(original)["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("ambiguous or already activated speed pilot policy")
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    proposed_policy = original.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1)
    (PACKAGE / "execution_backends.yaml").write_text(proposed_policy, encoding="utf-8", newline="\n")
    request = {"document_kind": KIND, "scope": scope, "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "exception_id": EXCEPTION, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}}
    check_scope(request)
    request["artifacts"] = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    write_json_exclusive(PACKAGE / "request.json", request)
    authorization = {"action": "RUN_PAIRED_ML_RELAXATION", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "user_authorized": False, "user_request": QUOTE, "reason": "Concrete10GPUminute budget not yet confirmed"}
    write_json_exclusive(PACKAGE / "authorization.json", authorization)
    try:
        execution_scope(request, authorization, exception, sha256_file(PACKAGE / "request.json"))
    except ValueError as exc:
        if "human authorization" not in str(exc):
            raise
    else:
        raise ValueError("unapproved GPU proposal unexpectedly executable")
    cost = cost_reference()
    plan = {"status": "PREPARED_PENDING_CPU_INTERFACE_CHECK_AND_EXACT_GPU_BUDGET", "models": models, "cases": cases,
        "GPU_proposal": scope, "GPU_python": ENV_ROOT + "/venv/bin/python", "ML_relaxations": 4,
        "comparison_arms_per_seed": ["direct_DFT_from_common_seed", "nequip_ML_then_DFT", "finetune_ML_then_DFT"],
        "DFT_future_scope": {"maximum_jobs": 6, "cores_each": 32, "maximum_steps_each": 300,
            "fmax_eV_A": 0.02, "settings_source": "configs/true_fe110_production.yaml",
            "core_hour_historical_linear_reference_range": [x * 6/4 * 300/80 for x in cost["four_job_core_hour_reference_range"]],
            "is_cost_cap_or_convergence_guarantee": False, "inputs_prepared": False, "execution_authorized": False},
        "acceptance": ["same reviewed chemical fragments/connectivity,adsorption basin and magnetic branch",
            "normal termination and SCF QC plus movable DFTfmax<=0.02eV/A",
            "only matched successful endpoints get step/SCF/corehour speedup ratios;failures remain failures"],
        "data_isolation": "512/78/53+16 unchanged;do not train on benchmark trajectories or use them to reselect checkpoints",
        "C3_caveat": "Prior models fragmented this origin toCO+C2H2;classify outcome rather than claiming intactC3 success",
        "canonical_policy_changed": False, "GPU_started": False, "new_DFT_submitted": False,
        "request_sha256": sha256_file(PACKAGE / "request.json"), "unapproved_execution_rejected": True,
        "source_files": source_file_manifest([Path(__file__), ROOT / "configs/execution_backends.yaml", selection_path, reviewed_path, PACKAGE / "request.json"])}
    write_json_exclusive(OUTPUT / "plan.json", plan)
    print({k: plan[k] for k in ["status", "ML_relaxations", "request_sha256", "canonical_policy_changed", "unapproved_execution_rejected"]}, flush=True)


if __name__ == "__main__":
    prepare()
