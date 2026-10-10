"""Fresh bounded request after sampler/CLI repair; never submits."""

import json
import shutil
from pathlib import Path

import yaml

from scripts.artifact_io import sha256_file, write_json
from scripts.adsorption.force_finetune import build_database_metadata, verify_request

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v4"
NEW = OLD.with_name("adsorption_finetune_review_v6")
OLD_SHA = "9f634620c40a4da397853085f4cfcdf366548832115a641b35f34fb366bd5f2a"


def main():
    assert sha256_file(OLD / "training_request.json") == OLD_SHA
    original = json.loads((OLD / "training_request.json").read_text(encoding="utf-8"))
    for item in original["artifacts"]:
        assert sha256_file(OLD / item["path"]) == item["sha256"]
    NEW.mkdir(exist_ok=False)
    for item in original["artifacts"]:
        target = NEW / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OLD / item["path"], target)
    shutil.copyfile(ROOT / "scripts/adsorption/adsorption_finetune_job.sh", NEW / "runtime/adsorption_finetune_job.sh")
    shutil.copyfile(ROOT / "scripts/adsorption/force_finetune.py", NEW / "runtime/force_finetune.py")
    shutil.copyfile(Path(__file__).with_name("preflight_adsorption_finetune.py"), NEW / "runtime/preflight_adsorption_finetune.py")
    metadata = {split: build_database_metadata(NEW / f"{split}.db", NEW / f"{split}_metadata.npz")
                for split in ("train", "development")}
    remote = "/home/sbq/sbq/adsorption_c2_finetune_20261010_v6"
    config_path = NEW / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["checkpoint"] = remote + "/output/job_warmstart.pt"
    config["dataset"]["train"]["src"] = remote + "/train.db"
    config["dataset"]["val"]["src"] = remote + "/development.db"
    config["dataset"]["train"]["metadata_path"] = remote + "/train_metadata.npz"
    config["dataset"]["val"]["metadata_path"] = remote + "/development_metadata.npz"
    config_path.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8", newline="\n")
    paths = [item["path"] for item in original["artifacts"]] + ["train_metadata.npz", "development_metadata.npz", "runtime/preflight_adsorption_finetune.py"]
    request = {**original, "remote_package_root": remote, "runtime_contract_version": 2,
               "supersedes_request_sha256": OLD_SHA,
               "retry_reason": "2184 failed before training: add per-split natoms metadata and explicit reviewed CLI seed; test actual trainer dataset/sampler/loader and merged CLI config. v5 CPU preflight exposed a preflight reference-index error: resolve trainer Subset indices before comparison; metadata itself unchanged. No label/split/model/scientific change.",
               "remaining_before_submission": ["Bind current user conditional submission authorization to v6 hash", "Fresh MZ73 actual sampler/loader/CLI and GPU preflight"],
               "artifacts": [{"path": name, "sha256": sha256_file(NEW / name)} for name in sorted(paths)]}
    path = NEW / "training_request.json"
    write_json(path, request)
    verdict = verify_request(path)
    old_hashes = {item["path"]: item["sha256"] for item in original["artifacts"]}
    changed = [item["path"] for item in request["artifacts"] if item["path"] in old_hashes and item["sha256"] != old_hashes[item["path"]]]
    assert changed == ["config.yml", "runtime/adsorption_finetune_job.sh", "runtime/force_finetune.py"]
    record = {"request_sha256": sha256_file(path), "previous_request_sha256": OLD_SHA,
              "changed_artifacts": changed, "unchanged_artifacts": 77, "metadata": metadata,
              "added_artifacts": sorted(set(paths) - set(old_hashes)),
              "training_limits_unchanged": request["training_limits"] == original["training_limits"],
              "validation": verdict, "submitted": False, "training_authorized": False}
    write_json(NEW / "retry_preparation.json", record)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
