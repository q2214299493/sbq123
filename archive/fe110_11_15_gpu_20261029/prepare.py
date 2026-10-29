"""Freeze the already-reviewed v5 geometries and latest selected FT snapshot."""
from pathlib import Path
import shutil

import yaml

from archive.fe110_pair2_20261027.runtime import verify
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020"
OUTPUT = BASE / "ft512_gpu_20261029_v1"
PACKAGE = OUTPUT / "package"
REMOTE = "/home/sbq/sbq/fe110_c2_11_15_ft512_20261029_v1"
POLICY = ROOT / "configs/execution_backends.yaml"
EXCEPTION = "fe110_c2_11_15_ft512_20261029"
QUOTE = "利用新微调的AQCat25 gpu加速 然后提交dft"


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(source.read_bytes())


def prepare():
    if OUTPUT.exists():
        raise FileExistsError("preserve this batch; inspect receipts instead of overwriting")
    source = BASE / "candidates_v5"
    manifest = load_json_object(source / "candidate_review.json")
    if len(manifest["candidates"]) != 15 or load_json_object(source / "independent_readback.json")["checked"] != 15:
        raise ValueError("fifteen reviewed v5 seeds required")
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    previous = policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"]["fe110_scratch512_speed2_20261028"]
    scope = {key: previous["scope"][key] for key in ["gpu_index", "gpu_uuid", "max_wall_seconds", "CPU_count", "memory_GB", "allocator_limit_MiB", "limits"]}
    scope.update(remote_root=REMOTE, models={"finetune": previous["scope"]["models"]["finetune"]}, cases=[])
    OUTPUT.mkdir(parents=True)
    for row in manifest["candidates"]:
        path = source / row["structure"]
        if sha256_file(path) != row["structure_sha256"] or row["geometry"]["plausibility_status"] != "PASS":
            raise ValueError("v5 geometry review changed")
        relative = "geometry/" + row["name"] + "/POSCAR"
        copy(path, PACKAGE / relative)
        scope["cases"].append({"name": row["name"], "composition": row["formula"], "seed_path": relative, "seed_sha256": sha256_file(path)})
    old_package = ROOT / "calculations/fe110_reico_pilot300_20261022/scratch512_speed2_20261028_v2/authorized_package_v1"
    shutil.copytree(old_package / "runtime", PACKAGE / "runtime")
    # Only the common scope dispatch changed; the previous deployment is immutable.
    for relative in ["archive/fe110_pair2_20261027/runtime.py", "archive/fe110_11_15_gpu_20261029/adapter.py"]:
        target = PACKAGE / "runtime" / relative
        if target.exists():
            target.write_bytes((ROOT / relative).read_bytes())
        else:
            copy(ROOT / relative, target)
    copy(source / "candidate_review.json", PACKAGE / "evidence/source_geometry_review.json")
    copy(source / "independent_readback.json", PACKAGE / "evidence/source_readback.json")
    write_json_exclusive(PACKAGE / "evidence/frozen_force_comparison.json", {"model_checkpoint_sha256": {"finetune": scope["models"]["finetune"]["sha256"]},
        "role": "newest development-selected partial snapshot; not production promotion or independently validated error bound"})
    copy(POLICY, OUTPUT / "previous_execution_backends.yaml")
    raw = POLICY.read_bytes()
    text = raw.decode("utf-8")
    marker = "    direct_execution_exceptions:\n"
    if text.count(marker) != 1 or EXCEPTION in previous:
        raise ValueError("ambiguous exception insertion")
    if EXCEPTION in policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("exception already exists")
    exception = {"scope": scope, "authorizing_user_request": QUOTE,
        "canonical_remote_boundary": previous["canonical_remote_boundary"], "automatic_retries": 0, "VASP_submission_authority": False,
        "authorization_interpretation": "Explicit current user requests these fifteen GPU starts followed by work-reviewed DFT. Conservative 600s GPU cap selected by agent; not a claimed user-specified budget."}
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    updated = text.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1)
    POLICY.write_bytes(updated.encode("utf-8"))
    copy(POLICY, PACKAGE / "execution_backends.yaml")
    request = {"document_kind": "fe110_c2_11_15_ft512_relaxation", "scope": scope,
        "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "exception_id": EXCEPTION, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}}
    request["artifacts"] = [{"path": path.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(path)} for path in sorted(PACKAGE.rglob("*")) if path.is_file()]
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_PAIRED_ML_RELAXATION", "user_authorized": True,
        "user_request": QUOTE, "request_sha256": sha256_file(PACKAGE / "request.json")})
    verify(PACKAGE / "request.json")
    write_json_exclusive(OUTPUT / "preparation_receipt.json", {"status": "LOCAL_PASS_15_SEEDS", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "model_sha256": scope["models"]["finetune"]["sha256"], "GPU_seconds_cap": 600, "max_total_ML_steps": 1200,
        "DFT_stage": "authorized by current user; requires post-ML work review and separate canonical execution gates"})
    print({"prepared": 15, "model_sha256": scope["models"]["finetune"]["sha256"], "request_sha256": sha256_file(PACKAGE / "request.json")})


if __name__ == "__main__":
    prepare()
