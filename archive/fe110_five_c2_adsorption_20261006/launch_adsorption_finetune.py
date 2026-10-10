"""Exclusive transport for the single reviewed adsorption fine-tuning request."""

import argparse
import importlib.util
import io
import json
import re
import tarfile
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6"
EVIDENCE = PACKAGE.parent / "adsorption_finetune_submission_v6"
REMOTE = "/home/sbq/sbq/adsorption_c2_finetune_20261010_v6"
EXPECTED = "5e04e87a2a04f3937734f2592c2f442172d24cfb189a14d66554b854c50cb311"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("upload", "preflight", "submit"))
    action = parser.parse_args().action
    request_path = PACKAGE / "training_request.json"
    if sha256_file(request_path) != EXPECTED:
        raise ValueError("Reviewed request changed")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["remote_package_root"] == REMOTE
    authorization = EVIDENCE / "submission_authorization.json"
    approval = json.loads(authorization.read_text(encoding="utf-8"))
    assert approval["user_authorized"] is True
    assert approval["request_sha256"] == EXPECTED
    assert approval["action"] == "RUN_GPU_ADSORPTION_SMALL_FINETUNE"
    for item in request["artifacts"]:
        relative = Path(item["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert sha256_file(PACKAGE / relative) == item["sha256"]
    spec = importlib.util.spec_from_file_location("transport", Path(__file__).with_name("supplement_gpu_remote.py"))
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    transport.EVIDENCE = EVIDENCE
    preflight_script = PACKAGE / "runtime/preflight_adsorption_finetune.py"
    extras = {"submission_authorization.json": authorization}
    authorization_sha = sha256_file(authorization)
    preflight_sha = sha256_file(preflight_script)
    verify = (f"printf '%s  training_request.json\\n' {EXPECTED} | sha256sum -c - >&2; "
              f"printf '%s  submission_authorization.json\\n' {authorization_sha} | sha256sum -c - >&2; ")
    if action == "upload":
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for relative in [r["path"] for r in request["artifacts"]] + ["training_request.json"]:
                archive.add(PACKAGE / relative, arcname=relative, recursive=False)
            for relative, source in extras.items():
                archive.add(source, arcname=relative, recursive=False)
        result = transport.run(f'set -eu; test "$(hostname)" = MZ73; test ! -e {REMOTE}; '
                               f"mkdir {REMOTE}; tar -xf - -C {REMOTE}; printf 'UPLOAD_COMPLETE\\n'",
                               "upload.txt", stream.getvalue())
        print(result.decode().strip())
    elif action == "preflight":
        command = (f"set -eu; cd {REMOTE}; " + verify
                   + f"printf '%s  runtime/preflight_adsorption_finetune.py\\n' {preflight_sha} | sha256sum -c -; "
                   + "source runtime/aqcat25_mz73_env.sh; aqcat25_require_mz73; "
                   + "aqcat25_setup_mz73_environment; bash -n runtime/adsorption_finetune_job.sh; "
                   + '"$AQCAT_PYTHON" runtime/force_finetune.py verify --request training_request.json; '
                   + f'"$AQCAT_PYTHON" runtime/preflight_adsorption_finetune.py {REMOTE}; '
                   + "nvidia-smi --query-gpu=index,memory.total,memory.used,utilization.gpu --format=csv,noheader; "
                   + "squeue -u sbq -h -o '%i %T %j'")
        result = transport.run(command, "preflight.txt")
        assert b'"status": "PASS_NO_MODEL_RUN"' in result
        write_json(EVIDENCE / "preflight_binding.json", {
            "status": "PASS_NO_MODEL_RUN", "request_sha256": EXPECTED,
            "authorization_sha256": authorization_sha, "preflight_script_sha256": preflight_sha,
            "remote_preflight_sha256": sha256_file(EVIDENCE / "preflight.txt")})
        print(result.decode().strip())
    else:
        binding = json.loads((EVIDENCE / "preflight_binding.json").read_text(encoding="utf-8"))
        assert binding["status"] == "PASS_NO_MODEL_RUN" and binding["request_sha256"] == EXPECTED
        assert binding["authorization_sha256"] == authorization_sha
        assert binding["preflight_script_sha256"] == preflight_sha
        assert binding["remote_preflight_sha256"] == sha256_file(EVIDENCE / "preflight.txt")
        with (EVIDENCE / "local_submission_reservation.json").open("x", encoding="utf-8") as handle:
            json.dump({"request_sha256": EXPECTED, "automatic_retry": False}, handle)
        result = transport.run(f"set -eu; cd {REMOTE}; " + verify + "set -C; : > submission_attempt.lock; "
                               + f"sbatch --parsable --chdir={REMOTE} --output={REMOTE}/slurm-%j.out "
                               + f"--export=ALL,PACKAGE_ROOT={REMOTE},AUTHORIZATION={REMOTE}/submission_authorization.json "
                               + "runtime/adsorption_finetune_job.sh > submission_receipt.txt; cat submission_receipt.txt",
                               "submit.txt")
        receipt = result.decode().strip()
        if not re.fullmatch(r"\d+(;[A-Za-z0-9_.-]+)?", receipt):
            raise ValueError("Unknown submission outcome; reconcile receipt; do not retry")
        job = receipt.split(";")[0]
        scheduler = transport.run(f"scontrol show job {job}", f"scheduler_{job}.txt").decode()
        match = re.search(r"\bJobState=(\S+)", scheduler)
        assert match, "Unknown scheduler state; do not resubmit"
        summary = {"job_id": job, "scheduler_state": match.group(1), "remote_root": REMOTE,
                   "request_sha256": EXPECTED, "authorization_sha256": authorization_sha,
                   "submission_receipt_sha256": sha256_file(EVIDENCE / "submit.txt"),
                   "scheduler_evidence_sha256": sha256_file(EVIDENCE / f"scheduler_{job}.txt"),
                   "training_limits": request["training_limits"], "checkpoint_promoted": False,
                   "scientific_acceptance": False, "actual_speedup_proved": False}
        write_json(EVIDENCE / "submission_summary.json", summary)
        print(json.dumps(summary))


if __name__ == "__main__":
    main()
