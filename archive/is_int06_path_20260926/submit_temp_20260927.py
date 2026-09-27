"""One authorized GPU1802 NEB on the temporary, separately bound LSF account."""
from datetime import datetime, timezone
import json
import shlex
import subprocess

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.execution_backends import require_vasp_backend
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from archive.is_int06_path_20260926.prepare_vasp import RUN


HOST = "sunboquan-cdj1-temp"
POTCAR = "~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR"


def save(path, payload):
    if path.exists():
        raise FileExistsError(f"Preserve existing attempt: {path}")
    write_json(path, payload)


def main():
    assert submission_status(RUN)["status"] == "NOT_RESERVED"
    require_vasp_backend(HOST, "LSF", workdir_name=RUN.name)
    original = load_json_object(RUN / "user_execution_authorization.json")
    report = preflight(RUN, "ordinary_neb", write_report=False)
    assert report == load_json_object(RUN / "submission_preflight.json")
    digest = original["potcar"]["sha256"]
    remote = original["target"]["remote_dir"]
    fe_co = '"$HOME/sbq/Fe_agent_demo/review_jobs/adsorption/fe110_c_o_coads_top25_top30/POTCAR"'
    fe_h = '"$HOME/sbq/Fe_agent_demo/review_jobs/afe110/Fe110_H_bridge/POTCAR"'
    combine = "{ cat " + fe_co + "; awk '{if(n>=1) print; if($0 ~ /End of Dataset/) n++}' " + fe_h + "; }"
    checks = [
        'test "$(id -un)" = nsgkx_cdj1',
        'test "$(hostname)" = ycn03',
        'test -x "$HOME/soft/vasp541vtst/bin/vasp_std"',
        'test -r /home_gkx/env/intel/intel2016.sh',
        'test "$(realpath -e ~/sbq)" = "$(realpath -e "$HOME")/sbq"',
        f"test ! -e {remote}", f"test ! -e {remote}.submission-reservation",
        f"test \"$({combine} | sha256sum | awk '{{print $1}}')\" = {digest}",
        "mkdir -p ~/sbq/Fe110/potcars/Fe_C_O_H",
        f"if test ! -e {POTCAR}; then (set -C; {combine} > {POTCAR}); fi",
        f"test \"$(sha256sum {POTCAR} | awk '{{print $1}}')\" = {digest}",
        f"sha256sum {POTCAR}",
    ]
    command = "bash -c " + shlex.quote("set -euo pipefail; " + " && ".join(checks))
    result = subprocess.run(["ssh", HOST, command], capture_output=True, timeout=45)
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(),
                "server_alias": HOST, "hostname": "10.68.0.103", "user": "nsgkx_cdj1",
                "command": command, "exit_code": result.returncode,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
                "status": "PASS" if result.returncode == 0 else "FAILED"}
    save(RUN / "temporary_backend_precheck_retry1_20260927.json", evidence)
    if result.returncode:
        raise RuntimeError("Temporary backend precheck failed; no submission")
    source = RUN / "user_temporary_backend_request_20260927.json"
    save(source, {"verbatim": "你先短暂提交到这个服务器上",
                  "target": {"hostname": "10.68.0.103", "port": 22, "user": "nsgkx_cdj1"},
                  "scope": "One existing reviewed GPU1802 ordinary NEB; temporary backend only.108 cores,9 interiors,NSW300,no pilot,no duplicate or automatic retry."})
    request = load_json_object(RUN / "execution_gate_request.json")
    request.pop("authorization_file")
    request_path = RUN / "temporary_gate_request_20260927.json"
    save(request_path, request)
    before = build_decision(request_path, RUN / "temporary_gate_before_authorization_20260927.json")
    auth = dict(original)
    auth.update(authorized_at=datetime.now(timezone.utc).isoformat(),
                source={"path": str(source), "sha256": sha256_file(source)},
                target={"server_alias": HOST, "remote_dir": remote},
                evidence_sha256=execution_evidence_sha256(before["EVIDENCE"]),
                potcar={**original["potcar"], "source": POTCAR})
    auth_path = RUN / "temporary_user_authorization_20260927.json"
    save(auth_path, auth)
    authorized_request = RUN / "temporary_authorized_gate_request_20260927.json"
    request["authorization_file"] = str(auth_path)
    save(authorized_request, request)
    gate_path = RUN / "temporary_execution_gate_decision_20260927.json"
    gate = build_decision(authorized_request, gate_path)
    assert "SUBMIT_VASP" in gate["ALLOWED_ACTIONS"], gate["DECISION"]
    receipt = submit(RUN, gate_path, HOST, remote, POTCAR, digest, "SUBMIT_VASP")
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == "__main__":
    main()
