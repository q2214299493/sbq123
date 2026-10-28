"""Bind the human-approved unchanged two-arm requests and concrete one-hour cap."""
import copy
from pathlib import Path
import shutil

import yaml

from scripts.adsorption.direct_force_training import verify
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .prepare import REMOTE
from .probe import OUTPUT, ROOT

USER_REQUEST = "启动两项训练，总计≤1 GPU小时（推荐）"
RUN_ID = "direct-fe110-scratch512-finetune20-20261028-v1"
FT_EXCEPTION = "fe110_force_training512_comparison20_20261028"


def authorize():
    package = OUTPUT / "package"
    proposals = load_json_object(OUTPUT / "execution_exception_proposals_v2.json")
    ft = package / "finetune"
    nequip = package / "nequip_v2"
    ft_sha = sha256_file(ft / "control/training_request.json")
    neq_sha = sha256_file(nequip / "training_request.json")
    review = load_json_object(OUTPUT / "reviewed_requests_v2.json")
    if ft_sha != review["finetune_request_sha256"] or neq_sha != review["nequip_request_sha256"]:
        raise ValueError("human-reviewed model requests changed")
    auth_doc = ROOT / "docs/reviews/fe110_scratch512_20261028/user_authorization.md"
    if USER_REQUEST not in auth_doc.read_text(encoding="utf-8"):
        raise ValueError("explicit concrete budget confirmation missing")
    comparison = {"document_kind": "adsorption_bounded_single_training_review", "arms": {"control": {"sha256": ft_sha}},
        "total_GPU_walltime_minutes_cap": 30, "total_optimizer_steps_cap": 10240, "human_budget": USER_REQUEST}
    write_json_exclusive(ft / "comparison_request.json", comparison)
    exceptions = {}
    for key in [FT_EXCEPTION, "fe110_nequip_scratch512_20261028"]:
        entry = copy.deepcopy(proposals[key])
        entry.update(authorized_by="user_explicit_20261028_two_arm_oneGPUhour", authorizing_user_request=USER_REQUEST)
        exceptions[key] = entry
    exceptions[FT_EXCEPTION]["original_comparison_sha256"] = sha256_file(ft / "comparison_request.json")
    policy = ROOT / "configs/execution_backends.yaml"
    text = policy.read_text(encoding="utf-8")
    before = yaml.safe_load(text)
    if any(key in before["backends"]["aqcat_gpu"]["direct_execution_exceptions"] for key in exceptions):
        raise ValueError("preserve existing authorization;inspect receipt before rerun")
    (OUTPUT / "policy_before_authorization.yaml").write_bytes(policy.read_bytes())
    marker = "    direct_execution_exceptions:\n"
    if text.count(marker) != 1:
        raise ValueError("canonical exception insertion ambiguous")
    snippet = yaml.safe_dump(exceptions, sort_keys=False, allow_unicode=True)
    policy.write_text(text.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1), encoding="utf-8", newline="\n")
    for target in [ft, nequip]:
        shutil.copyfile(policy, target / "execution_backends.yaml")
        shutil.copyfile(auth_doc, target / "scope.md")
    write_json_exclusive(nequip / "authorization.json", {"user_authorized": True, "action": "RUN_GPU_FE110_NEQUIP_SCRATCH",
        "request_sha256": neq_sha, "policy_sha256": sha256_file(policy), "user_request": USER_REQUEST})
    write_json_exclusive(ft / "control/direct_arm_authorization.json", {"user_authorized": True, "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE",
        "request_sha256": ft_sha, "user_request": USER_REQUEST, "execution_mode": "direct_no_scheduler", "new_VASP_or_promotion_authorized": False})
    direct = {"document_kind": "adsorption_direct_force_training_trial", "run_id": RUN_ID, "exception_id": FT_EXCEPTION,
        "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(policy)}, "remote_root": REMOTE + "/finetune",
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None, "gpu_index": 1, "gpu_uuid": review_gpu_uuid(),
        "gpu_sharing": None, "max_wall_seconds": 1800, "per_arm_wall_seconds": 1800, "arms": ["control"],
        "original_comparison_sha256": sha256_file(ft / "comparison_request.json"), "native_two_backward_check": True,
        "artifacts": [{"path": p.relative_to(ft).as_posix(), "sha256": sha256_file(p)} for p in sorted(ft.rglob("*")) if p.is_file()]}
    write_json_exclusive(ft / "direct_request.json", direct)
    ft_direct_sha = sha256_file(ft / "direct_request.json")
    write_json_exclusive(ft / "direct_authorization.json", {"user_authorized": True, "action": "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT",
        "user_request": USER_REQUEST, "request_sha256": ft_direct_sha, "source_scope_sha256": sha256_file(ft / "scope.md"), "checkpoint_promotion_authorized": False})
    verify(ft / "direct_request.json", ft_direct_sha)
    shutil.copyfile(Path(__file__).with_name("sequence_driver.py"), package / "sequence_driver.py")
    paths = sorted([p for d in [ft, nequip] for p in d.rglob("*") if p.is_file()]) + [package / "sequence_driver.py"]
    # Exclude superseded,unbound NequIP configuration drafts from transport.
    paths = [p for p in paths if p.name not in ["config.yaml", "config_v2.yaml"]]
    sequence = {"document_kind": "fe110_scratch512_authorized_two_arm_sequence", "remote_root": REMOTE,
        "arms": ["nequip_scratch", "aqcat25_finetune"], "gpu_index": 1, "gpu_uuid": review_gpu_uuid(),
        "per_arm_seconds": 1800, "total_GPU_seconds": 3600, "automatic_retries": 0,
        "nequip_request_sha256": neq_sha, "finetune_direct_request_sha256": ft_direct_sha,
        "artifacts": [{"path": p.relative_to(package).as_posix(), "sha256": sha256_file(p)} for p in paths]}
    write_json_exclusive(package / "sequence_request.json", sequence)
    digest = sha256_file(package / "sequence_request.json")
    write_json_exclusive(package / "sequence_authorization.json", {"user_authorized": True, "action": "RUN_FE110_SCRATCH512_TWO_ARM_SEQUENCE",
        "request_sha256": digest, "user_request": USER_REQUEST, "source_scope_sha256": sha256_file(auth_doc)})
    write_json_exclusive(OUTPUT / "authorization_receipt.json", {"status": "HUMAN_AUTHORIZED_BOUND_NOT_LAUNCHED", "sequence_request_sha256": digest,
        "nequip_request_sha256": neq_sha, "finetune_direct_request_sha256": ft_direct_sha, "canonical_policy_sha256": sha256_file(policy)})
    print({"sequence_request_sha256": digest, "formal_training_started": False})


def review_gpu_uuid():
    return "GPU-450609b3-d1fd-ac33-d03a-79891be402da"


if __name__ == "__main__":
    authorize()
