"""One authorized batch: exclusive upload, no-model preflight, single submission."""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_v1"
EVIDENCE = PACKAGE.parent / "gpu_supplement_submission_v1"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "IdentitiesOnly=yes",
       "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-p", "36039", "sbq@10sx4jr711576.vicp.fun"]


def run(command: str, evidence_name: str, payload: bytes | None = None):
    target = EVIDENCE / evidence_name
    if target.exists():
        raise FileExistsError("Inspect existing receipt before any retry: " + str(target))
    result = subprocess.run(SSH + [command], input=payload, capture_output=True, timeout=180)
    target.write_bytes(result.stdout + result.stderr)
    write_json(target.with_suffix(".command.json"), {"command": command, "exit_code": result.returncode,
               "observed_at": datetime.now(timezone.utc).isoformat(), "output_sha256": sha256_file(target)})
    if result.returncode:
        raise RuntimeError(f"Remote command exit={result.returncode}; inspect {target}; do not retry unchanged")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload", "preflight", "submit"])
    args = parser.parse_args()
    EVIDENCE.mkdir(exist_ok=True)
    manifest_path = PACKAGE / "batch_manifest.json"
    batch = json.loads(manifest_path.read_text())
    remote = batch["remote_root"]
    assert remote == "/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_supplement_v1"
    for item in batch["files"]:
        assert sha256_file(PACKAGE / item["path"]) == item["sha256"]
    digest = sha256_file(manifest_path)
    if args.action == "upload":
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for relative in [item["path"] for item in batch["files"]] + ["batch_manifest.json"]:
                assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
                archive.add(PACKAGE / relative, arcname=relative, recursive=False)
        run(f"set -eu; test \"$(hostname)\" = MZ73; test ! -e {remote}; "
            f"mkdir {remote}; tar -xf - -C {remote}; printf 'UPLOAD_COMPLETE\\n'", "upload.txt", stream.getvalue())
        print("UPLOAD_COMPLETE")
    elif args.action == "preflight":
        command = (
            f"set -eu; test \"$(hostname)\" = MZ73; cd {remote}; "
            f"printf '%s  batch_manifest.json\\n' {digest} | sha256sum -c -; "
            f"export AQCAT_PILOT_ROOT={remote}/runtime; "
            "export AQCAT_ROOT=/home/sbq/sbq/aqcat25; "
            "export AQCAT_PYTHON=/home/sbq/sbq/ml_ts_acceleration/venv/bin/python; "
            f"export TMPDIR={remote}/tmp XDG_CACHE_HOME={remote}/cache/xdg "
            f"TORCH_HOME={remote}/cache/torch HF_HOME={remote}/cache/huggingface; "
            '. "$AQCAT_PILOT_ROOT/aqcat25_mz73_env.sh"; aqcat25_setup_mz73_environment; '
            "bash -n batch_job.sh; bash -n runtime/aqcat25_gpu_job.sh; "
            'bash -n runtime/aqcat25_mz73_env.sh; "$AQCAT_PYTHON" preflight.py'
        )
        result = run(command, "preflight.txt")
        assert b"GPU_BEFORE_EXECUTION_PASS_NO_MODEL_RUN" in result
        write_json(EVIDENCE / "preflight_binding.json", {"batch_manifest_sha256": digest,
                   "remote_preflight_sha256": sha256_file(EVIDENCE / "preflight.txt"), "status": "PASS_NO_MODEL_RUN"})
        print(result.decode().strip())
    else:
        binding = json.loads((EVIDENCE / "preflight_binding.json").read_text())
        assert binding["batch_manifest_sha256"] == digest
        assert binding["remote_preflight_sha256"] == sha256_file(EVIDENCE / "preflight.txt")
        with (EVIDENCE / "local_submission_reservation.json").open("x", encoding="utf-8") as handle:
            json.dump({"batch_manifest_sha256": digest, "state": "SUBMISSION_ATTEMPT_RESERVED_NO_AUTOMATIC_RETRY",
                       "observed_at": datetime.now(timezone.utc).isoformat()}, handle)
        result = run(
            f"set -eu; cd {remote}; printf '%s  batch_manifest.json\\n' {digest} | sha256sum -c - >&2; "
            "set -C; : > submission_attempt.lock; "
            f"sbatch --parsable --output={remote}/slurm-%j.out batch_job.sh > submission_receipt.txt; "
            "cat submission_receipt.txt", "submit.txt")
        receipt = result.decode().strip()
        if not re.fullmatch(r"\d+(;[A-Za-z0-9_.-]+)?", receipt):
            raise ValueError("Submission outcome needs receipt/scheduler reconciliation; do not resubmit")
        job = receipt.split(";")[0]
        scheduler = run(f"scontrol show job {job}", f"scheduler_{job}.txt").decode()
        match = re.search(r"\bJobState=(\S+)", scheduler)
        if not match:
            raise ValueError("Missing scheduler state")
        record = {"job_id": job, "scheduler_state": match.group(1), "remote_root": remote,
                  "observed_at": datetime.now(timezone.utc).isoformat(), "candidate_count": 5,
                  "names": [r["name"] for r in batch["handoffs"]], "batch_manifest_sha256": digest,
                  "submission_receipt_sha256": sha256_file(EVIDENCE / "submit.txt"),
                  "scheduler_evidence_sha256": sha256_file(EVIDENCE / f"scheduler_{job}.txt"),
                  "scientific_status": "PREDICTED_CANDIDATE_GENERATION_ONLY",
                  "unverified": ["ML relaxation convergence", "final chemistry/sites/duplicates", "VASP results"]}
        write_json(EVIDENCE / "submission_summary.json", record)
        print(json.dumps(record))


if __name__ == "__main__":
    main()
