"""Explicitly authorized new attempt; preserve the unresolved old reservation."""
from datetime import datetime, timezone
import argparse
import shutil
import subprocess

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.submission import preflight, submission_status
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review
from scripts.ts_strategy_engine.workflow import AnalyzeRequest, analyze_search
from archive.is_int06_path_20260926.prepare_vasp import ROOT, RUN as OLD


RUN = OLD.parent / "h_is_a_int06_gpu1802_neb_temp_r2_20260928"
HOST = "sunboquan-cdj1-temp"
REMOTE = "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + RUN.name


def main():
    if RUN.exists():
        raise FileExistsError("Preserve prepared attempt; do not rebuild")
    assert submission_status(OLD)["status"] == "UNKNOWN_NEEDS_RECONCILIATION"
    attempt = load_json_object(OLD / "submission_attempt.json")
    original = load_json_object(OLD / "temporary_user_authorization_20260927.json")
    old_report = load_json_object(OLD / "submission_preflight.json")
    remote_old = attempt["remote_dir"]
    command = (
        "set -e; "
        f"test ! -e {remote_old}; "
        f"test \"$(cat {remote_old}.submission-reservation/reservation_id)\" = {attempt['reservation_id']}; "
        f"test ! -e {REMOTE}; test ! -e {REMOTE}.submission-reservation; "
        f"test \"$(sha256sum {original['potcar']['source']} | awk '{{print $1}}')\" = {original['potcar']['sha256']}; "
        "printf 'OLD_TARGET_ABSENT_AND_RESERVATION_PRESERVED\\n'; bjobs -a -w"
    )
    check = subprocess.run(["ssh", HOST, command], capture_output=True, timeout=45)
    if check.returncode:
        raise RuntimeError("Recovery precheck failed; no new workdir or submission")
    stdout = check.stdout.decode("utf-8", errors="replace")
    assert "OLD_TARGET_ABSENT_AND_RESERVATION_PRESERVED" in stdout
    assert RUN.name not in stdout and OLD.name not in stdout
    RUN.mkdir()
    for relative, digest in old_report["files"].items():
        source = OLD / relative
        assert sha256_file(source) == digest
        destination = RUN / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        assert sha256_file(destination) == digest
    for name in ("path_generation_report.json", "reaction_contract.normalized.json", "path_review.json",
                 "dist.dat", "movie.xyz", "work_review_evidence.json", "work_review.png", ".gitattributes"):
        shutil.copyfile(OLD / name, RUN / name)
    assert validate_path_review(RUN / "path_review.json", RUN / "path_generation_report.json")[0]
    contract_path = RUN / "reaction_contract.normalized.json"
    contract = load_contract(contract_path)
    assert validate_path_binding(RUN, contract)["valid"]
    write_json(RUN / "submission_recovery_review.json", {
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "user_reply": "继续", "prior_question": "确认本次没有匹配作业，并授权修复上传后重新提交？",
        "scope": "One new attempt with banner-safe upload; original local/remote reservations remain unchanged.",
        "old_attempt": {"path": str(OLD / "submission_attempt.json"), "sha256": sha256_file(OLD / "submission_attempt.json")},
        "old_failure_evidence": {"path": str(OLD / "temporary_upload_failure_reconciliation_20260927.json"),
                                 "sha256": sha256_file(OLD / "temporary_upload_failure_reconciliation_20260927.json")},
        "fresh_read_only_check": {"command": command, "exit_code": check.returncode, "stdout": stdout},
        "scientific_inputs": "Byte-identical original preflight manifest; same accepted review and VTST movie evidence."})
    geometry = diagnose(RUN, ["49"], [str(i) for i in range(18)],
                        ROOT / "configs/neb_agent/default_thresholds.yaml", reaction_pairs=[[49, 37]], expected_interior=9)
    assert geometry["status"] != "STOP"
    analyze_search(AnalyzeRequest(workdir=RUN, contract=contract_path,
                   thresholds=ROOT / "configs/neb_agent/default_thresholds.yaml", path_review=RUN / "path_review.json"))
    report = preflight(RUN, "ordinary_neb")
    assert report["passed"], report["errors"]
    authorize_prepared()


def authorize_prepared():
    if (RUN / "user_execution_authorization.json").exists():
        raise FileExistsError("Preserve existing authorization")
    assert submission_status(RUN)["status"] == "NOT_RESERVED"
    original = load_json_object(OLD / "temporary_user_authorization_20260927.json")
    old_report = load_json_object(OLD / "submission_preflight.json")
    report = preflight(RUN, "ordinary_neb", write_report=False)
    assert report == load_json_object(RUN / "submission_preflight.json") and report["passed"]
    assert report["files"].keys() == old_report["files"].keys()
    for name, digest in old_report["files"].items():
        # Geometry evidence binds the new absolute paths, not changed positions.
        if name != "path_geometry_diagnosis.json":
            assert report["files"][name] == digest, name
    assert (RUN / "submission_recovery_review.json").exists()
    request = {"geometry_file": str(RUN / "path_geometry_diagnosis.json"),
               "analysis_file": str(RUN / "neb_analysis.json"),
               "thresholds_file": str(ROOT / "configs/neb_agent/default_thresholds.yaml"),
               "preflight_file": str(RUN / "submission_preflight.json"), "climb": False, "path_reviewed": True}
    write_json(RUN / "gate_request_before_authorization.json", request)
    before = build_decision(RUN / "gate_request_before_authorization.json", RUN / "gate_before_authorization.json")
    source = RUN / "user_execution_request.json"
    write_json(source, {"verbatim": "继续", "received_date": "2026-09-28",
                       "recovery_review_sha256": sha256_file(RUN / "submission_recovery_review.json"),
                       "scope": "Continue the explicitly reviewed upload recovery with one new108-rank/9-interior ordinary NEB on10.68.0.103/nsgkx_cdj1; no pilot, changed geometry or parameters, duplicate job, or automatic retry."})
    auth = {**original, "authorized_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(source), "sha256": sha256_file(source)},
            "target": {"server_alias": HOST, "remote_dir": REMOTE},
            "workdir_identity": workdir_identity(RUN), "bundle_sha256": report["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(before["EVIDENCE"])}
    write_json(RUN / "user_execution_authorization.json", auth)
    request["authorization_file"] = str(RUN / "user_execution_authorization.json")
    write_json(RUN / "execution_gate_request.json", request)
    gate = build_decision(RUN / "execution_gate_request.json", RUN / "execution_gate_decision.json")
    assert "SUBMIT_VASP" in gate["ALLOWED_ACTIONS"]
    print(gate["DECISION"], gate["ALLOWED_ACTIONS"], report["bundle_sha256"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-prepared", action="store_true")
    args = parser.parse_args()
    authorize_prepared() if args.authorize_prepared else main()
