"""Prepare the requested159 fixed-geometry predictions,without fitting."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil

import yaml

from archive.fe110_training512_20261027.prepare import RUNTIME
from scripts.adsorption.fixed_force_comparison import verify
from scripts.adsorption.force_finetune import local_path
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
DATA = BASE / "combined_force_package_20261027_v3"
OUTPUT = BASE / "fixed53_comparison_20261027_v1"
PACKAGE = OUTPUT / "package"
REMOTE = "/home/sbq/sbq/fe110_fixed53_comparison_20261027_v1"
EXCEPTION = "fe110_fixed53_force_comparison_20261027"
POLICY = ROOT / "configs/execution_backends.yaml"
AUTH = ROOT / "docs/reviews/fe110_fixed53_comparison_20261027/user_authorization.md"
QUOTE = "固定结构上的新旧模型力误差对照。"
MANIFEST_SHA = "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee"
MODELS = {
    "baseline": {"path": "/home/sbq/sbq/aqcat25/demo_single/model.pt", "sha256": "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"},
    "control": {"path": "/home/sbq/sbq/adsorption_training_comparison_20261020_v2/control/output/direct-adsorption-role-ab-20261020-v2/candidate.pt", "sha256": "cfcac123cd56b866a1ea36cc780a3aee634f3aeec979bda4ae8bee2cc831e523"},
    "new512": {"path": "/home/sbq/sbq/fe110_force_training512_gpu0_20261027_v1/control/output/direct-fe110-force512-gpu0-20261027-v1/candidate.pt", "sha256": "513decf4ebd823cf8f87a79e787fdbd543b657fd582184f2ab23845d281d6aeb"},
}


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("xb") as target:
        shutil.copyfileobj(src, target)
    if sha256_file(source) != sha256_file(destination):
        raise ValueError("comparison input copy differs")


def prepare():
    if PACKAGE.exists():
        raise FileExistsError("preserve existing comparison package;never rebuild blindly")
    if sha256_file(DATA / "training_manifest.json") != MANIFEST_SHA or QUOTE not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("frozen data or human comparison scope changed")
    manifest = load_json_object(DATA / "training_manifest.json")
    rows = manifest["splits"]["heldout"]
    if len(rows) != 53 or sum(r["source_collection"] == "legacy_control_20261019" for r in rows) != 46:
        raise ValueError("reserved53 historical exposure changed")
    PACKAGE.mkdir(parents=True)
    copy_file(DATA / "training_manifest.json", PACKAGE / "data/training_manifest.json")
    paths = {r[key] for split in manifest["splits"].values() for r in split for key in ["structure_path"]}
    paths |= {r["label_source"]["path"] for split in manifest["splits"].values() for r in split}
    for relative in sorted(paths):
        copy_file(local_path(DATA, relative), PACKAGE / "data" / relative)
    for relative in [*RUNTIME, "scripts/adsorption/fixed_force_comparison.py"]:
        copy_file(ROOT / relative, PACKAGE / "runtime" / relative)
    for name in ["runtime.py", "validation_helpers.py"]:
        copy_file(ROOT / "archive/fe110_adsorption_validation_20261018" / name,
                  PACKAGE / "runtime/archive/fe110_adsorption_validation_20261018" / name)
    copy_file(ROOT / "docs/reviews/fe110_training512_gpu0_20261027/candidate_summary.json", PACKAGE / "evidence/candidate_summary.json")
    copy_file(AUTH, PACKAGE / "scope.md")
    sharing = copy.deepcopy(yaml.safe_load(POLICY.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"]["fe110_force_training512_gpu0_20261027"]["gpu_sharing"])
    request = {"document_kind": "frozen_three_model_force_comparison", "remote_root": REMOTE, "exception_id": EXCEPTION,
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 0, "gpu_uuid": "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75", "gpu_sharing": sharing,
        "max_wall_seconds": 600, "models": MODELS, "model_checkpoint_sha256": {k: v["sha256"] for k, v in MODELS.items()},
        "training_manifest_sha256": MANIFEST_SHA, "sample_ids": [r["sample_id"] for r in rows], "prediction_count": 159,
        "historically_observed_ids": [r["sample_id"] for r in rows if r["source_collection"] == "legacy_control_20261019"],
        "scientific_boundaries": {"training": False, "relaxation": False, "model_reselection": False, "model_promotion": False}}
    previous = OUTPUT / "previous_execution_backends.yaml"
    copy_file(POLICY, previous)
    exception = {k: request[k] for k in ["remote_root", "gpu_index", "gpu_uuid", "gpu_sharing", "max_wall_seconds", "sample_ids", "model_checkpoint_sha256"]}
    exception.update(authorizing_user_request=QUOTE, authorized_by="user_explicit_fixed_structure_force_comparison_20261027",
        canonical_remote_boundary="/home/ubuntu/hdd/sbq/sbq", executor="scripts/adsorption/fixed_force_comparison.py",
        prediction_count=159, CPU_count=4, memory_GB=32, automatic_retries=0, training_or_optimization="forbidden")
    text = POLICY.read_text(encoding="utf-8")
    marker = "    direct_execution_exceptions:\n"
    if text.count(marker) != 1 or EXCEPTION in yaml.safe_load(text)["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("comparison policy insertion ambiguous or already present")
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    POLICY.write_text(text.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1), encoding="utf-8", newline="\n")
    copy_file(POLICY, PACKAGE / "execution_backends.yaml")
    request["policy"] = {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")}
    request["artifacts"] = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_FROZEN_FORCE_COMPARISON", "user_authorized": True,
        "user_request": QUOTE, "request_sha256": sha256_file(PACKAGE / "request.json")})
    verify(PACKAGE / "request.json")
    write_json_exclusive(OUTPUT / "preparation_receipt.json", {"status": "FIXED53_THREE_MODEL_PACKAGE_BOUND",
        "request_sha256": sha256_file(PACKAGE / "request.json"), "samples": 53, "predictions": 159,
        "source_files": source_file_manifest([Path(__file__), AUTH, previous, POLICY, PACKAGE / "request.json", PACKAGE / "authorization.json"])})
    print({"status": "FIXED53_THREE_MODEL_PACKAGE_BOUND", "request_sha256": sha256_file(PACKAGE / "request.json")}, flush=True)


if __name__ == "__main__":
    prepare()
