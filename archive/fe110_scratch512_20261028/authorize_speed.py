"""Bind the human's exact four-relaxation approval;preserve the draft package."""
from pathlib import Path
import shutil

import yaml

from archive.fe110_pair2_20261027.runtime import verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .prepare_speed import EXCEPTION, OUTPUT, PACKAGE as PROPOSAL, QUOTE, REMOTE as REMOTE, ROOT
from .relaxation_adapter import check_scope

PACKAGE = OUTPUT / "authorized_package_v1"
POLICY = ROOT / "configs/execution_backends.yaml"
AUTH = ROOT / "docs/reviews/fe110_scratch512_speed2_20261028/user_authorization.md"
ANSWER = "启动4次ML优化，合计≤10 GPU分钟（推荐）"


def activate():
    ready = load_json_object(OUTPUT / "readiness_review.json")
    if not source_file_manifest_valid(ready) or ready["request_sha256"] != sha256_file(PROPOSAL / "request.json"):
        raise ValueError("prepared input/CPU interface review changed")
    request = load_json_object(PROPOSAL / "request.json")
    check_scope(request)
    for row in request["artifacts"]:
        if sha256_file(PROPOSAL / row["path"]) != row["sha256"]:
            raise ValueError("reviewed proposal bytes changed")
    if ANSWER not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("current exact human budget evidence required")
    original = POLICY.read_text(encoding="utf-8")
    current = yaml.safe_load(original)["backends"]["aqcat_gpu"]["direct_execution_exceptions"]
    if EXCEPTION in current:
        raise FileExistsError("canonical scope already exists;inspect its activation receipt instead of reauthorizing")
    proposed = yaml.safe_load((PROPOSAL / "execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][EXCEPTION]
    if proposed["scope"] != request["scope"]:
        raise ValueError("proposed policy differs from reviewed request")
    proposed.update(budget_confirmation="CONFIRMED_HUMAN_FOUR_ML_TEN_GPU_MINUTES", authorized_by="explicit_user_20261028_four_ML_tenGPUminutes",
        budget_authorization=ANSWER, authorization_evidence_sha256=sha256_file(AUTH))
    marker = "    direct_execution_exceptions:\n"
    if original.count(marker) != 1:
        raise ValueError("ambiguous canonical policy insertion")
    snippet = yaml.safe_dump({EXCEPTION: proposed}, sort_keys=False, allow_unicode=True)
    active = original.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1)
    PACKAGE.mkdir(exist_ok=False)
    shutil.copyfile(POLICY, OUTPUT / "policy_before_speed_activation.yaml")
    for row in request["artifacts"]:
        if row["path"] == "execution_backends.yaml":
            continue
        target = PACKAGE / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROPOSAL / row["path"], target)
    (PACKAGE / "execution_backends.yaml").write_text(active, encoding="utf-8", newline="\n")
    shutil.copyfile(AUTH, PACKAGE / "evidence/budget_authorization.md")
    request["preparation_request_sha256"] = ready["request_sha256"]
    request["policy"]["sha256"] = sha256_file(PACKAGE / "execution_backends.yaml")
    request["artifacts"] = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_PAIRED_ML_RELAXATION", "user_authorized": True,
        "request_sha256": sha256_file(PACKAGE / "request.json"), "user_request": QUOTE, "budget_response": ANSWER,
        "human_evidence_sha256": sha256_file(AUTH), "new_training_or_DFT_authorized": False})
    verify(PACKAGE / "request.json")
    POLICY.write_text(active, encoding="utf-8", newline="\n")
    if sha256_file(POLICY) != request["policy"]["sha256"]:
        raise ValueError("canonical policy write did not match reviewed binding")
    result = {"status": "HUMAN_AUTHORIZED_SPEED_PACKAGE_BOUND_NOT_STARTED", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "preparation_request_sha256": ready["request_sha256"], "input_artifacts": len(request["artifacts"]), "canonical_scope": EXCEPTION,
        "max_GPU_seconds": 600, "ML_relaxations": 4, "training_authorized": False, "VASP_authorized": False,
        "source_files": source_file_manifest([Path(__file__), AUTH, POLICY, PACKAGE / "request.json", PACKAGE / "authorization.json", OUTPUT / "readiness_review.json"])}
    write_json_exclusive(OUTPUT / "activation_receipt.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    activate()
