"""Rebind corrected runtime to unchanged physical data;never changes the v1 package."""
import argparse
import copy
import json
from pathlib import Path

import yaml

from archive.fe110_adsorption_training_comparison_20261019.execute import ARMS, EXPECTED, checked_request
from archive.fe110_adsorption_training_comparison_20261019.prepare import OUTPUT as ORIGINAL, copy_exact
from scripts.adsorption.direct_force_training import verify
from scripts.adsorption.force_training_preflight import verify_training_package
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

from .transport import EVIDENCE, EXCEPTION, PACKAGE, REMOTE, ROOT, RUN_ID

EXTRA_RUNTIME = ["scripts/artifact_io.py", "scripts/adsorption/direct_gpu_batch.py",
                 "scripts/adsorption/direct_force_training.py", "scripts/adsorption/direct_training_arm.py"]


def arms():
    checked_request()
    PACKAGE.mkdir(exist_ok=False)
    result = {}
    for name, expected in ARMS.items():
        original = ORIGINAL / name
        request = load_json_object(original / "training_request.json")
        changed, unchanged = [], []
        for item in request["artifacts"]:
            relative = item["path"]
            target = PACKAGE / name / relative
            if relative == "config.yml":
                config = yaml.safe_load((original / relative).read_text(encoding="utf-8"))
                for dataset in config["dataset"].values():
                    for key in ("src", "metadata_path"):
                        old = dataset[key]
                        if not old.startswith(request["remote_package_root"] + "/"):
                            raise ValueError("unexpected original dataset location")
                        dataset[key] = REMOTE + "/" + name + old[len(request["remote_package_root"]):]
                with target.open("x", encoding="utf-8", newline="\n") as handle:
                    yaml.safe_dump(config, handle, sort_keys=True)
            else:
                source = ROOT / relative.removeprefix("runtime/") if relative.startswith("runtime/scripts/") else original / relative
                copy_exact(source, target)
            if sha256_file(target) == item["sha256"]:
                unchanged.append(relative)
            else:
                if relative not in {"config.yml", "runtime/scripts/adsorption/role_force_trainer.py",
                                    "runtime/scripts/adsorption/force_training_preflight.py"}:
                    raise ValueError("unexpected changed original artifact: " + relative)
                changed.append(relative)
        for source in EXTRA_RUNTIME:
            copy_exact(ROOT / source, PACKAGE / name / "runtime" / source)
        fresh = copy.deepcopy(request)
        fresh["previous_request_sha256"] = expected
        fresh["remote_package_root"] = REMOTE + "/" + name
        fresh["artifacts"] = [{"path": p.relative_to(PACKAGE / name).as_posix(), "sha256": sha256_file(p)}
                              for p in sorted((PACKAGE / name).rglob("*")) if p.is_file()]
        path = PACKAGE / name / "training_request.json"
        write_json_exclusive(path, fresh)
        result[name] = {"path": name + "/training_request.json", "sha256": sha256_file(path),
            "validation": verify_training_package(path), "changed_original_artifacts": changed,
            "unchanged_original_artifact_count": len(unchanged)}
    comparison = load_json_object(ORIGINAL / "comparison_request.json")
    comparison["previous_comparison_sha256"] = EXPECTED
    comparison["arms"] = result
    comparison["source_files"] = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in
        [Path(__file__), ROOT / "scripts/adsorption/force_training_preflight.py", ROOT / "scripts/adsorption/direct_training_arm.py"]]
    write_json_exclusive(PACKAGE / "comparison_request.json", comparison)
    receipt = {"comparison_sha256": sha256_file(PACKAGE / "comparison_request.json"), "arms": result,
               "previous_comparison_sha256": EXPECTED, "data_and_sampling_unchanged": True, "GPU_started": False}
    write_json_exclusive(EVIDENCE / "arms_preparation_receipt.json", receipt)
    print(json.dumps({"comparison_sha256": receipt["comparison_sha256"], "arms": {k: v["sha256"] for k, v in result.items()}}))


def bind():
    source = load_json_object(EVIDENCE / "arms_preparation_receipt.json")
    policy_path = ROOT / "configs/execution_backends.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][EXCEPTION]
    if policy["original_comparison_sha256"] != source["comparison_sha256"] or policy["arm_request_sha256"] != {k: v["sha256"] for k, v in source["arms"].items()}:
        raise ValueError("backend retry policy is not bound to fresh corrected requests")
    for name, arm in source["arms"].items():
        write_json_exclusive(PACKAGE / name / "direct_arm_authorization.json", {"user_authorized": True,
            "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE", "request_sha256": arm["sha256"],
            "user_request": "修复好再跑一次", "execution_mode": "direct_no_scheduler", "new_VASP_or_promotion_authorized": False})
    copy_exact(policy_path, PACKAGE / "execution_backends.yaml")
    copy_exact(Path(__file__).with_name("scope.md"), PACKAGE / "scope.md")
    request = {"document_kind": "adsorption_direct_force_training_comparison", "run_id": RUN_ID,
        "exception_id": EXCEPTION, "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "remote_root": REMOTE, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 1, "gpu_uuid": policy["gpu_uuid"], "max_wall_seconds": 3600, "per_arm_wall_seconds": 1800,
        "arms": ["control", "treatment"], "original_comparison_sha256": source["comparison_sha256"],
        "previous_comparison_sha256": EXPECTED, "native_two_backward_check": True,
        "artifacts": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]}
    path = PACKAGE / "direct_request.json"
    write_json_exclusive(path, request)
    sha = sha256_file(path)
    write_json_exclusive(PACKAGE / "direct_authorization.json", {"user_authorized": True,
        "action": "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT", "user_request": "修复好再跑一次", "request_sha256": sha,
        "source_scope_sha256": sha256_file(PACKAGE / "scope.md"), "checkpoint_promotion_authorized": False})
    verify(path, sha)
    write_json_exclusive(EVIDENCE / "preparation_receipt.json", {"status": "BOUND_CORRECTED_RETRY_AUTHORIZED",
        "request_sha256": sha, "comparison_sha256": source["comparison_sha256"], "user_request": "修复好再跑一次",
        "GPU_started": False, "old_package_modified": False})
    print(json.dumps({"status": "BOUND_CORRECTED_RETRY_AUTHORIZED", "request_sha256": sha}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("arms", "bind"))
    args = parser.parse_args()
    (arms if args.action == "arms" else bind)()
