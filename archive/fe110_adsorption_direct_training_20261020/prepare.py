"""Fresh execution-only package; frozen model,data,config and arm requests unchanged."""
import json
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.adsorption.direct_force_training import verify
from archive.fe110_adsorption_training_comparison_20261019.execute import ARMS, EXPECTED, checked_request
from archive.fe110_adsorption_training_comparison_20261019.prepare import OUTPUT as ORIGINAL, copy_exact

from .transport import EVIDENCE, PACKAGE, REMOTE, ROOT

EXCEPTION = "fe110_adsorption_role_training_20261020"
RUN_ID = "direct-adsorption-role-ab-20261020-v1"


def main():
    checked_request()
    PACKAGE.mkdir(exist_ok=False)
    for arm, expected in ARMS.items():
        original = ORIGINAL / arm
        document = json.loads((original / "training_request.json").read_text(encoding="utf-8"))
        for item in document["artifacts"]:
            copy_exact(original / item["path"], PACKAGE / arm / item["path"])
        copy_exact(original / "training_request.json", PACKAGE / arm / "training_request.json")
        for source in ("scripts/artifact_io.py", "scripts/adsorption/direct_gpu_batch.py",
                       "scripts/adsorption/direct_force_training.py", "scripts/adsorption/direct_training_arm.py"):
            copy_exact(ROOT / source, PACKAGE / arm / "runtime" / source)
        write_json_exclusive(PACKAGE / arm / "direct_arm_authorization.json", {"user_authorized": True,
            "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE", "request_sha256": expected,
            "user_request": "跑", "execution_mode": "direct_no_scheduler", "new_VASP_or_promotion_authorized": False})
    copy_exact(ORIGINAL / "comparison_request.json", PACKAGE / "comparison_request.json")
    copy_exact(ROOT / "configs/execution_backends.yaml", PACKAGE / "execution_backends.yaml")
    copy_exact(Path(__file__).with_name("scope.md"), PACKAGE / "scope.md")
    artifacts = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)}
                 for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    request = {"document_kind": "adsorption_direct_force_training_comparison", "run_id": RUN_ID,
        "exception_id": EXCEPTION, "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "remote_root": REMOTE, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da", "max_wall_seconds": 3600,
        "per_arm_wall_seconds": 1800, "arms": ["control", "treatment"], "original_comparison_sha256": EXPECTED,
        "artifacts": artifacts}
    path = PACKAGE / "direct_request.json"
    write_json_exclusive(path, request)
    sha = sha256_file(path)
    write_json_exclusive(PACKAGE / "direct_authorization.json", {"user_authorized": True,
        "action": "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT", "user_request": "跑", "request_sha256": sha,
        "source_scope_sha256": sha256_file(PACKAGE / "scope.md"), "checkpoint_promotion_authorized": False})
    verify(path, sha)
    result = {"status": "READY_FOR_AUTHORIZED_DIRECT_PREFLIGHT", "request_sha256": sha,
        "original_comparison_sha256": EXPECTED, "original_arm_requests_unchanged": ARMS,
        "changed_original_artifacts": [], "added_runtime_only": True, "training_started": False}
    write_json_exclusive(EVIDENCE / "preparation_receipt.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
