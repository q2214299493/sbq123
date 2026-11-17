"""Build a separate BUCT3 inference packet from frozen train/development inputs."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tarfile

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive,
)
from .runner import MODEL_SHA, verify

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "force_diagnosis536_gpu_20261117_v4"
REMOTE = "/home/sbq/sbq/force_diagnosis536_gpu_20261117_v4"


def copy_exclusive(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1048576)
    if sha256_file(source) != sha256_file(target):
        raise ValueError("byte copy mismatch")


def run():
    labels_path = BASE / "force_diagnosis536_20261114_v1/qualified_reference_labels.json"
    labels = load_json_object(labels_path)
    if not source_file_manifest_valid(labels):
        raise ValueError("qualified label source bindings changed")
    old = load_json_object(BASE / "force_diagnosis536_20261114_v1/request_context.json")
    model = Path(old["model_path"])
    if sha256_file(model) != MODEL_SHA:
        raise ValueError("frozen536 model changed")
    native_receipt = load_json_object(OUT / "native_source_hashes_receipt.json")
    if native_receipt["exit_code"]:
        raise ValueError("native source probe failed")
    native_files = json.loads(native_receipt["stdout"])["native_source_files"]
    context = {"user_request": "配置好了，你检查一下BUCT3的免密登录和三台服务器的GPU资源，预检通过后继续冻结536模型的614帧固定结构力预测，不训练、不提交DFT。",
               "frozen_hashes_before": frozen_hashes(), "model_path": str(model), "model_sha256": MODEL_SHA,
               "task_sha256": sha256_file(ROOT / "tasks/current_task.md"), "registry_sha256": sha256_file(ROOT / "data/project_registry.sqlite3"),
               "method_sha256": sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md"), "backend_policy_sha256": sha256_file(ROOT / "configs/execution_backends.yaml")}
    write_json_exclusive(OUT / "request_context.json", context)
    packet = OUT / "packet"
    packet.mkdir(exist_ok=False)
    for name in ("runner.py", "job.sh"):
        copy_exclusive(Path(__file__).with_name(name), packet / name)
    copy_exclusive(ROOT / "configs/execution_backends.yaml", packet / "execution_backends.yaml")
    copy_exclusive(model, packet / "models/frozen536.pt")
    samples = []
    for row in labels["records"]:
        name = row["sample_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or row["partition"] not in {"train", "development"}:
            raise ValueError("unsafe or protected input")
        path = Path(row["structure_path"])
        if sha256_file(path) != row["structure_sha256"]:
            raise ValueError("input geometry changed")
        relative = "structures/" + name + ".vasp"
        copy_exclusive(path, packet / relative)
        samples.append({"sample_id": name, "partition": row["partition"], "structure_path": relative,
                        "structure_sha256": row["structure_sha256"], "symbols": row["symbols"],
                        "fixed_atom_indices_0based": row["fixed_atom_indices_0based"]})
    artifacts = [{"path": p.relative_to(packet).as_posix(), "sha256": sha256_file(p)} for p in sorted(packet.rglob("*")) if p.is_file()]
    request = {"action": "FROZEN_TRAIN_DEVELOPMENT_FORCES_ONLY", "backend": "buct3_gpu", "hostname": "ubuntu-R5350-G6",
               "remote_root": REMOTE, "canonical_remote_boundary": "/home/sbq/sbq", "execution_mode": "Slurm", "partition": "compute",
               "model": {"path": REMOTE + "/models/frozen536.pt", "sha256": MODEL_SHA}, "max_GPU_count": 1, "max_GPU_seconds": 600,
               "producer_seconds": 500, "scheduler_seconds": 540, "watchdog_seconds": 520, "watchdog_kill_after_seconds": 10,
               "scheduler_killwait_allowance_seconds": 30, "forbidden_work": {"training": True, "optimization": True, "DFT": True, "heldout_or_quarantine": True, "model_reselection": True},
               "samples": samples, "artifacts": artifacts, "native_source_files": native_files,
               "qualified_reference_sha256": sha256_file(labels_path), "source_scope": "536train+78development;original qualification tiers preserved;not independent validation",
               "startup_correction": {"prior_job": "434", "prior_terminal_state": "FAILED", "prior_allocated_seconds": 2,
                                      "prior_prediction_frames": 0, "cumulative_allocated_GPU_seconds_with_killwait_cap": 572}}
    write_json_exclusive(packet / "request.json", request)
    request_sha = sha256_file(packet / "request.json")
    write_json_exclusive(packet / "authorization.json", {"request_sha256": request_sha, "user_authorized": True,
                         "action": request["action"], "user_request": context["user_request"], "scientific_acceptance": False})
    verify(packet / "request.json", request_sha)
    archive = OUT / "execution_control.tar"
    with archive.open("xb") as stream, tarfile.open(fileobj=stream, mode="w") as tar:
        for path in sorted(packet.rglob("*")):
            if path.is_file() and path.relative_to(packet).parts[0] not in {"models", "structures"}:
                tar.add(path, arcname=path.relative_to(packet).as_posix(), recursive=False)
    write_json_exclusive(OUT / "preparation_receipt.json", {"request_sha256": request_sha, "archive_sha256": sha256_file(archive),
                         "archive_bytes": archive.stat().st_size, "samples": len(samples), "model_sha256": MODEL_SHA, "backend": "buct3_gpu",
                         "max_allocated_GPU_seconds_with_killwait": 572, "training_DFT_or_optimization": False,
                         "source_files": source_file_manifest([Path(__file__), labels_path, model, OUT / "request_context.json", packet / "request.json", packet / "authorization.json"])})
    print({"request_sha256": request_sha, "archive_bytes": archive.stat().st_size, "samples": len(samples), "backend": "buct3_gpu"}, flush=True)


if __name__ == "__main__":
    run()
