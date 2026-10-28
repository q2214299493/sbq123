"""Prepare a fresh bounded fine-tuning control from the frozen 512-frame arm."""
import copy
from pathlib import Path
import shutil

import yaml

from scripts.adsorption.force_training_preflight import verify_training_package
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import REMOTE
from .probe import OUTPUT, ROOT

OLD = ROOT / "calculations/fe110_reico_pilot300_20261022/training512_gpu0_20261027_v1/package/control"


def prepare():
    request = load_json_object(OLD / "training_request.json")
    for item in request["artifacts"]:
        if sha256_file(OLD / item["path"]) != item["sha256"]:
            raise ValueError("frozen source arm changed")
    target = OUTPUT / "package/finetune/control"
    shutil.copytree(OLD, target, ignore=shutil.ignore_patterns("training_request.json", "direct_arm_authorization.json", "config.yml"))
    config = yaml.safe_load((OLD / "config.yml").read_text(encoding="utf-8"))
    config["optim"]["max_epochs"] = 20
    config["optim"]["scheduler_params"]["epochs"] = 20
    for part in config["dataset"].values():
        for key in ["src", "metadata_path"]:
            part[key] = part[key].replace(request["remote_package_root"], REMOTE + "/finetune/control", 1)
    with (target / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=True)
    changed = "scripts/adsorption/force_training_preflight.py"
    shutil.copyfile(ROOT / changed, target / "runtime" / changed)
    fresh = copy.deepcopy(request)
    fresh["previous_request_sha256"] = sha256_file(OLD / "training_request.json")
    fresh["remote_package_root"] = REMOTE + "/finetune/control"
    fresh["preparation_contract"] = "fe110_scratch512_comparison_v1"
    fresh["training_limits"].update(epochs=20, max_optimizer_steps=10240)
    fresh["remaining_before_submission"] = ["human confirmation of concrete two-arm budget", "fresh canonical GPU1 gate and authorization",
        "native on-disk preflight;no automatic retry or continuation"]
    fresh["artifacts"] = [{"path": p.relative_to(target).as_posix(), "sha256": sha256_file(p)} for p in sorted(target.rglob("*")) if p.is_file()]
    write_json_exclusive(target / "training_request.json", fresh)
    result = verify_training_package(target / "training_request.json")
    write_json_exclusive(OUTPUT / "finetune_preflight.json", {**result,
        "source_files": source_file_manifest([Path(__file__), target / "training_request.json", ROOT / changed])})
    print(result)


if __name__ == "__main__":
    prepare()
