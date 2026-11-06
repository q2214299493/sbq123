"""Bind the identical twelve accepted seeds and frozen model to BUCT2 only."""
from pathlib import Path

from archive.fe110_c2_supplement_gpu_20261106.prepare import PACKAGE as PARENT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.aqcat25_handoff import validate_handoff
from .deploy import MODEL, MODEL_SHA, OUT, PYTHON_PKGS, REMOTE, SITE, VENDOR

PACKAGE = OUT / "package_v3"
PARENT_SHA = "b95896f6da62f52d504c97663b4a30e0b3121872463a73f95ea277f6edaf553d"
PYTHON = REMOTE + "/deps/usr/bin/python3.10"
PYTHONHOME = REMOTE + "/deps/usr"
PYTHONPATH = ":".join([REMOTE, REMOTE + "/runtime", *[REMOTE + "/deps/" + p for p in (PYTHON_PKGS, VENDOR, SITE)]])
ENV = {"PYTHONHOME": PYTHONHOME, "PYTHONPATH": PYTHONPATH, "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1", "MPLCONFIGDIR": REMOTE + "/cache/matplotlib",
    "XDG_CACHE_HOME": REMOTE + "/cache/xdg", "TMPDIR": REMOTE + "/tmp", "TORCH_HOME": REMOTE + "/cache/torch",
    "HF_HOME": REMOTE + "/cache/huggingface", "WANDB_MODE": "disabled", "OMP_NUM_THREADS": "4",
    "OPENBLAS_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "LD_LIBRARY_PATH": REMOTE + "/native_libs"}


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(source.read_bytes())


def main():
    if sha256_file(PARENT / "request.json") != PARENT_SHA:
        raise ValueError("MZ73 submitted request changed")
    parent = load_json_object(PARENT / "request.json")
    PACKAGE.mkdir(exist_ok=False)
    for item in parent["artifacts"]:
        source = PARENT / item["path"]
        if sha256_file(source) != item["sha256"]:
            raise ValueError("parent artifact changed")
        if item["path"] not in {"worker.py", "run.sbatch"}:
            copy(source, PACKAGE / item["path"])
    copy(Path(__file__).with_name("worker.py"), PACKAGE / "worker.py")
    deployment = load_json_object(OUT / "runtime_manifest.json")
    copy(OUT / "runtime_manifest.json", PACKAGE / "environment_deployment.json")
    supplement = load_json_object(OUT / "portable_mpdec_manifest.json")
    copy(OUT / "portable_mpdec_manifest.json", PACKAGE / "evidence/portable_mpdec.json")
    for case in parent["cases"]:
        validate_handoff(PACKAGE / case["handoff_path"], root=PACKAGE, schema_path=PACKAGE / "handoff.schema.json")
    exports = "\n".join("export " + key + "=" + value for key, value in ENV.items())
    script = f'''#!/bin/bash
#SBATCH --job-name=fe110-c2-buct2-12
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:10:00
#SBATCH --signal=B:TERM@15
#SBATCH --chdir={REMOTE}
#SBATCH --output={REMOTE}/slurm-%j.out
#SBATCH --error={REMOTE}/slurm-%j.err
set -euo pipefail
: "${{SLURM_JOB_ID:?real Slurm job required}}"
: "${{REQUEST_SHA256:?request binding required}}"
{exports}
mkdir -p "$MPLCONFIGDIR" "$XDG_CACHE_HOME" "$TMPDIR" "$TORCH_HOME" "$HF_HOME"
exec {PYTHON} {REMOTE}/worker.py run --request {REMOTE}/request.json --sha256 "$REQUEST_SHA256"
'''
    with (PACKAGE / "run.sbatch").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(script)
    peer_path = OUT / "peer_submission_binding.json"
    peer = load_json_object(peer_path) if peer_path.exists() else {"job_id": "11396", "request_sha256": PARENT_SHA,
        "remote_root": "/home/sbq/sbq/fe110_c2_supplement_gpu_20261106_v1"}
    request = {**parent, "document_kind": "fe110_c2_supplement_buct2_single_winner", "backend": "buct2_gpu",
        "remote_root": REMOTE, "parent_request_sha256": PARENT_SHA,
        "model": {"path": REMOTE + "/deps/" + MODEL, "sha256": MODEL_SHA},
        "environment_archive_sha256": deployment["archive_sha256"],
        "arbitration": {"required_before_model": True, "peer_job_id": peer["job_id"], "peer_request_sha256": peer["request_sha256"],
            "peer_remote_root": peer["remote_root"],
            "permit_wait_seconds": 120},
        "artifacts": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)}
                      for p in sorted(PACKAGE.rglob("*")) if p.is_file()] +
                     [{"path": "native_libs/libmpdec.so.3", "sha256": supplement["sha256"]}]}
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_SECOND_GPU_REPLICA_KEEP_FIRST",
        "user_authorized": True, "user_request": "那你把这个任务提交给另外一个gpu服务器  哪个先跑就用哪个",
        "request_sha256": sha256_file(PACKAGE / "request.json"), "parent_request_sha256": PARENT_SHA,
        "coordinator_source_sha256": sha256_file(Path(__file__).with_name("arbitrate.py")),
        "cancel_only_redundant_replica": True, "VASP_authorized": False, "training_authorized": False})
    write_json_exclusive(OUT / "preparation_receipt_v3.json", {"request_sha256": sha256_file(PACKAGE / "request.json"),
        "cases": len(request["cases"]), "same_original_seeds": True, "same_checkpoint": True,
        "same_optimizer_budget": True, "single_winner_permit_required": True, "VASP_submitted": False})
    print("PREPARED12 identical seeds/model/budget;BUCT2-only;single-winner guard", flush=True)


if __name__ == "__main__":
    main()
