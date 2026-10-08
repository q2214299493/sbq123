"""Freeze and submit exactly one adsorption force-inference batch."""

import argparse
import io
import json
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from archive.fe110_five_c2_adsorption_20261006 import supplement_gpu_remote as transport
from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
SOURCE = BASE / "c2_force_diagnostic_v1"
PACKAGE = BASE / "gpu_force_diagnostic_v1"
EVIDENCE = BASE / "gpu_force_diagnostic_submission_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_force_diagnostic_20261008_v1"
HERE = Path(__file__).resolve().parent


def freeze():
    assert not PACKAGE.exists(), "Preserve existing frozen package"
    plan = json.loads((SOURCE / "assessment_plan.json").read_text())
    assert sha256_file(SOURCE / "labels.json") == plan["labels_sha256"]
    assert sha256_file(SOURCE / "evaluate_fe45_calibration.py") == plan["runner_sha256"]
    labels = json.loads((SOURCE / "labels.json").read_text())
    assert len(labels["samples"]) == 10
    for sample in labels["samples"]:
        path = SOURCE / "structures" / (sample["sample_id"] + ".vasp")
        assert sha256_file(path) == sample["structure_sha256"]
    PACKAGE.mkdir()
    for name in ["labels.json", "evaluate_fe45_calibration.py"]:
        shutil.copyfile(SOURCE / name, PACKAGE / name)
    shutil.copytree(SOURCE / "structures", PACKAGE / "structures")
    for name in ["force_prediction_preflight.py", "run_force_prediction.py"]:
        shutil.copyfile(HERE / name, PACKAGE / name)
    shutil.copyfile(HERE / "c2_force_prediction_job.sh", PACKAGE / "batch_job.sh")
    (PACKAGE / "runtime").mkdir()
    env = BASE / "gpu_repair_v1/runtime/aqcat25_mz73_env.sh"
    shutil.copyfile(env, PACKAGE / "runtime/aqcat25_mz73_env.sh")
    write_json(
        PACKAGE / "authorization.json",
        {
            "user_authorization": "2026-10-08: 进行; scoped to proposed ten frozen-structure AQCat25 force predictions",
            "assessment_plan_sha256": sha256_file(SOURCE / "assessment_plan.json"),
            "checkpoint_sha256": plan["checkpoint_sha256"],
            "geometry_optimization": False,
            "fine_tuning": False,
            "submit_vasp": False,
            "automatic_retry": False,
            "limits": {"GPU_count": 1, "cpus": 4, "memory_GiB": 32, "walltime_minutes": 30},
            "runtime_env_source_sha256": sha256_file(env),
        },
    )
    write_json(
        PACKAGE / "batch_manifest.json",
        {
            "remote_root": REMOTE,
            "checkpoint_sha256": plan["checkpoint_sha256"],
            "files": [
                {"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()
            ],
        },
    )
    print("FROZEN_10_EXACT_STRUCTURES")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "upload", "preflight", "submit"])
    action = parser.parse_args().action
    if action == "freeze":
        freeze()
        return
    EVIDENCE.mkdir(exist_ok=True)
    transport.EVIDENCE = EVIDENCE
    batch = json.loads((PACKAGE / "batch_manifest.json").read_text())
    assert batch["remote_root"] == REMOTE
    for item in batch["files"]:
        assert sha256_file(PACKAGE / item["path"]) == item["sha256"]
    digest = sha256_file(PACKAGE / "batch_manifest.json")
    if action == "upload":
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for rel in [i["path"] for i in batch["files"]] + ["batch_manifest.json"]:
                assert not Path(rel).is_absolute() and ".." not in Path(rel).parts
                archive.add(PACKAGE / rel, arcname=rel, recursive=False)
        transport.run(
            f'set -eu; test "$(hostname)" = MZ73; test ! -e {REMOTE}; mkdir {REMOTE}; tar -xf - -C {REMOTE}; echo UPLOAD_COMPLETE',
            "upload.txt",
            stream.getvalue(),
        )
        print("UPLOAD_COMPLETE")
    elif action == "preflight":
        result = transport.run(
            f'set -eu; cd {REMOTE}; printf "%s  batch_manifest.json\\n" {digest} | sha256sum -c -; '
            f"export AQCAT_PILOT_ROOT={REMOTE}/runtime TMPDIR={REMOTE}/tmp "
            f"XDG_CACHE_HOME={REMOTE}/cache/xdg TORCH_HOME={REMOTE}/cache/torch HF_HOME={REMOTE}/cache/huggingface; "
            '. "$AQCAT_PILOT_ROOT/aqcat25_mz73_env.sh"; aqcat25_require_mz73; aqcat25_setup_mz73_environment; '
            'bash -n batch_job.sh; "$AQCAT_PYTHON" force_prediction_preflight.py',
            "preflight.txt",
        )
        assert b"GPU_BEFORE_EXECUTION_PASS_NO_MODEL_RUN" in result
        write_json(
            EVIDENCE / "preflight_binding.json",
            {"status": "PASS_NO_MODEL_RUN", "batch_manifest_sha256": digest, "preflight_sha256": sha256_file(EVIDENCE / "preflight.txt")},
        )
        print(result.decode().strip())
    else:
        binding = json.loads((EVIDENCE / "preflight_binding.json").read_text())
        assert binding["batch_manifest_sha256"] == digest
        assert binding["preflight_sha256"] == sha256_file(EVIDENCE / "preflight.txt")
        with (EVIDENCE / "local_submission_reservation.json").open("x") as handle:
            json.dump({"manifest_sha256": digest, "state": "RESERVED_NO_AUTOMATIC_RETRY"}, handle)
        raw = transport.run(
            f'set -eu; cd {REMOTE}; printf "%s  batch_manifest.json\\n" {digest} | sha256sum -c - >&2; '
            "set -C; : > submission_attempt.lock; sbatch --parsable --output=slurm-%j.out batch_job.sh > submission_receipt.txt; "
            "cat submission_receipt.txt",
            "submit.txt",
        )
        receipt = raw.decode().strip()
        assert re.fullmatch(r"\d+(;[A-Za-z0-9_.-]+)?", receipt), "Reconcile unknown outcome; never resubmit"
        job = receipt.split(";")[0]
        status = transport.run(f"scontrol show job {job}", f"scheduler_{job}.txt").decode()
        state = re.search(r"\bJobState=(\S+)", status)
        assert state
        summary = {
            "job_id": job,
            "scheduler_state": state.group(1),
            "remote_root": REMOTE,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "structure_count": 10,
            "batch_manifest_sha256": digest,
            "submission_receipt_sha256": sha256_file(EVIDENCE / "submit.txt"),
            "scheduler_evidence_sha256": sha256_file(EVIDENCE / f"scheduler_{job}.txt"),
            "role": "fixed_geometry_force_prediction_not_relaxation_or_training",
        }
        write_json(EVIDENCE / "submission_summary.json", summary)
        print(json.dumps(summary))


if __name__ == "__main__":
    main()
