"""Single authorized inference execution and write-once producer receipt."""

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from evaluate_fe45_calibration import sha256_file
from force_prediction_preflight import CHECKPOINT, validate

ROOT = Path(__file__).resolve().parent


def main():
    batch = validate()
    output = ROOT / "output"
    output.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    code = subprocess.run(
        [
            sys.executable,
            str(ROOT / "evaluate_fe45_calibration.py"),
            "--checkpoint",
            str(CHECKPOINT),
            "--labels",
            str(ROOT / "labels.json"),
            "--structures",
            str(ROOT / "structures"),
            "--output",
            str(output / "predictions.json"),
        ],
        check=False,
    ).returncode
    receipt = {
        "gpu_job_id": os.environ["SLURM_JOB_ID"],
        "hostname": socket.gethostname(),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": code,
        "status": "success" if code == 0 else "failed",
        "checkpoint_sha256": batch["checkpoint_sha256"],
        "source_batch_sha256": sha256_file(ROOT / "batch_manifest.json"),
        "predictions_sha256": sha256_file(output / "predictions.json") if code == 0 else None,
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    }
    with (output / "producer_exit_record.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
