"""Fresh bounded request after a bootstrap-only repair; never submits."""

import json
import shutil
from pathlib import Path

import yaml

from scripts.artifact_io import sha256_file, write_json
from scripts.adsorption.force_finetune import verify_request

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v3"
NEW = OLD.with_name("adsorption_finetune_review_v4")
OLD_SHA = "2e1b517270395b414c8e7079cf95df93656014e24ce2db3f1e6b5e0ac3c40d16"


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
    remote = "/home/sbq/sbq/adsorption_c2_finetune_20261010_v4"
    config_path = NEW / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["checkpoint"] = remote + "/output/job_warmstart.pt"
    config["dataset"]["train"]["src"] = remote + "/train.db"
    config["dataset"]["val"]["src"] = remote + "/development.db"
    config_path.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8", newline="\n")
    request = {**original, "remote_package_root": remote,
               "supersedes_request_sha256": OLD_SHA,
               "retry_reason": "Slurm inherits TMPDIR=/tmp; explicitly bind per-job temporary storage; add early bootstrap logging and no-requeue. No scientific/training/data change.",
               "remaining_before_submission": ["Separate authorization of v4 request hash", "Fresh MZ73 package/runtime/GPU preflight"],
               "artifacts": [{"path": item["path"], "sha256": sha256_file(NEW / item["path"])} for item in original["artifacts"]]}
    path = NEW / "training_request.json"
    write_json(path, request)
    verdict = verify_request(path)
    changed = [item["path"] for item, old in zip(request["artifacts"], original["artifacts"]) if item["sha256"] != old["sha256"]]
    assert changed == ["config.yml", "runtime/adsorption_finetune_job.sh"]
    record = {"request_sha256": sha256_file(path), "previous_request_sha256": OLD_SHA,
              "changed_artifacts": changed, "unchanged_artifacts": 78,
              "training_limits_unchanged": request["training_limits"] == original["training_limits"],
              "validation": verdict, "submitted": False, "training_authorized": False}
    write_json(NEW / "retry_preparation.json", record)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
