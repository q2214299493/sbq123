"""One authorized submission, after bounded read-only live cluster checks."""
from datetime import datetime, timezone
import argparse
import subprocess

from scripts.artifact_io import load_json_object, write_json
from scripts.neb_agent.submission import submit, submission_status
from archive.is_int06_path_20260926.prepare_vasp import RUN


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precheck-name", default="remote_submission_precheck.json")
    args_cli = parser.parse_args()
    if not args_cli.precheck_name.endswith(".json") or any(c in args_cli.precheck_name for c in ("/", "\\")):
        raise ValueError("Precheck name must be a local JSON basename")
    status = submission_status(RUN)
    if status["status"] != "NOT_RESERVED":
        raise RuntimeError(f"Do not retry a reserved submission: {status}")
    destination = RUN / args_cli.precheck_name
    if destination.exists():
        raise FileExistsError("Preserve existing live precheck")
    args = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3", "-o", "GSSAPIAuthentication=no",
            "sunboquan-codex", "set -e; hostname; sha256sum ~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR; "
            "test ! -e ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + RUN.name + "; "
            "test ! -e ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + RUN.name + ".submission-reservation"]
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
