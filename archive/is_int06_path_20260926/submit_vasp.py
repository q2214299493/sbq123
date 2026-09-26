"""One authorized submission, after bounded read-only live cluster checks."""
from datetime import datetime, timezone
import subprocess

from scripts.artifact_io import load_json_object, write_json
from scripts.neb_agent.submission import submit, submission_status
from archive.is_int06_path_20260926.prepare_vasp import RUN


def main():
    status = submission_status(RUN)
    if status["status"] != "NOT_RESERVED":
        raise RuntimeError(f"Do not retry a reserved submission: {status}")
    destination = RUN / "remote_submission_precheck.json"
    if destination.exists():
        raise FileExistsError("Preserve existing live precheck")
    args = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3", "-o", "GSSAPIAuthentication=no",
            "sunboquan-codex", "hostname; sha256sum ~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR; bjobs -a 2>&1 | head -c 2000"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": args,
              "submits_or_modifies_remote": False}
    try:
        check = subprocess.run(args, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        report.update(status="SSH_COMMAND_TIMEOUT_45S", exit_code=None,
                      stdout=decode(exc.stdout), stderr=decode(exc.stderr))
        write_json(destination, report)
        raise RuntimeError("Cluster connection did not complete; no submission attempted") from exc
    report.update(exit_code=check.returncode, stdout=check.stdout, stderr=check.stderr)
    auth = load_json_object(RUN / "user_execution_authorization.json")
    potcar = auth["potcar"]
    passed = check.returncode == 0 and potcar["sha256"] in check.stdout
    report["status"] = "PASS" if passed else "FAILED"
    write_json(destination, report)
    if not passed:
        raise RuntimeError("Live cluster/POTCAR precheck failed; no submission attempted")
    result = submit(RUN, RUN / "execution_gate_decision.json", "sunboquan-codex",
                    auth["target"]["remote_dir"], potcar["source"], potcar["sha256"], "SUBMIT_VASP")
    print(result)


if __name__ == "__main__":
    main()
