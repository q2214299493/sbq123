"""Execute exactly the human-confirmed sixteen fresh static-label attempts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

import yaml
from ase.io import read

from archive.fe110_reico_sampling93_20261022 import submit as original
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from .preflight import OUTPUT, ROOT

PROPOSAL = OUTPUT / "recovery16_proposal.json"
PROPOSAL_SHA = "2bf820480302be93c320bbd2311b57fc775bc925722a522ff39411c3c3363779"
AUTH = ROOT / "docs/reviews/fe110_reico_remaining_20261024/recovery16_authorization.md"


def checked_cases():
    if sha256_file(PROPOSAL) != PROPOSAL_SHA:
        raise ValueError("human-reviewed recovery proposal changed")
    confirmation = load_json_object(OUTPUT / "recovery16_human_confirmation.json")
    if (confirmation["proposal_sha256"] != PROPOSAL_SHA
            or confirmation["authorization_sha256"] != sha256_file(AUTH)
            or confirmation["user_reply"] != "确认16份无重复，提交新尝试"
            or confirmation["no_matching_job_confirmed_by_human"] is not True):
        raise ValueError("explicit human recovery confirmation missing or changed")
    cases = load_json_object(PROPOSAL)["cases"]
    if len(cases) != 16 or len({r["sample_id"] for r in cases}) != 16:
        raise ValueError("exact sixteen-case scope changed")
    for row in cases:
        source = Path(row["original_workdir"])
        target = Path(row["proposed_workdir"])
        if (source.resolve() != (original.DEST / row["sample_id"]).resolve()
                or target.name != row["sample_id"]
                or row["proposed_remote_dir"] != "~/sbq/Fe110/diagnostics/reico_labels_recovery16_20261024_v1/" + row["sample_id"]):
            raise ValueError("recovery target outside approved scope")
        for name, key in (("submission_attempt.json", "original_attempt_sha256"),
                          ("submission_record.json", "original_record_sha256")):
            if sha256_file(source / name) != row[key]:
                raise ValueError("original unknown marker changed")
        if any(sha256_file(target / name) != expected for name, expected in row["input_hashes"].items()):
            raise ValueError("fresh-attempt scientific input changed")
    return cases


def prepare():
    cases = checked_cases()
    original.checked_ready()
    code = "import os,json,subprocess\n"
    code += "def run(a):\n r=subprocess.run(a,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=20);return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)\n"
    code += "result={'user':run(['whoami']),'resources':run(['busers','-w']),'targets':[],'potcars':{}}\n"
    code += "for d in " + repr([r["proposed_remote_dir"] for r in cases]) + ":\n p=os.path.expanduser(d);result['targets'].append(dict(remote_dir=d,directory_exists=os.path.lexists(p),lock_exists=os.path.lexists(p+'.submission-reservation')))\n"
    code += "for p in " + repr(sorted({r["potcar_source"] for r in cases})) + ":\n result['potcars'][p]=subprocess.check_output(['sha256sum',os.path.expanduser(p)]).decode().split()[0]\n"
    code += "print(json.dumps(result))\n"
    response = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", original.HOST, "python3 -"],
                              input=code, capture_output=True, text=True, timeout=60, check=False)
    live = {"checked_at": datetime.now(timezone.utc).isoformat(), "returncode": response.returncode,
            "stdout": response.stdout, "stderr": response.stderr}
    write_json_exclusive(OUTPUT / "recovery16_remote_preflight.json", live)
    if response.returncode:
        raise RuntimeError("fresh target preflight failed; no submissions attempted")
    parsed = json.loads(response.stdout)
    if (parsed["user"]["stdout"].strip() != "nsgkn_chengdj3"
            or parsed["resources"]["returncode"] != 0
            or any(r["directory_exists"] or r["lock_exists"] for r in parsed["targets"])):
        raise ValueError("fresh target or account preflight failed")
    resource_rows = [line.split() for line in parsed["resources"]["stdout"].splitlines()]
    header = resource_rows[0]
    account = next(row for row in resource_rows[1:] if row[0] == "nsgkn_chengdj3")
    if int(account[header.index("MAX")]) != 128 or int(account[header.index("RUN")]) > 128:
        raise ValueError("account resource policy differs from approved 128 cores")
    geometry = OUTPUT / "recovery16_geometry_adapter.json"
    write_json_exclusive(geometry, {})
    thresholds = yaml.safe_load(original.THRESHOLDS.read_text(encoding="utf-8"))
    ready = []
    for row in cases:
        directory = Path(row["proposed_workdir"])
        if submission_status(directory)["status"] != "NOT_RESERVED":
            raise ValueError("fresh attempt already reserved; inspect before recovery")
        report = preflight(directory, "diagnostic_static", write_report=False)
        if (not report["passed"] or report != load_json_object(directory / "submission_preflight.json")
                or report["bundle_sha256"] != row["bundle_sha256"]
                or parsed["potcars"][row["potcar_source"]] != row["potcar_sha256"]):
            raise ValueError("preflight or POTCAR differs from approved proposal")
        review_path = directory / "submission_geometry_review.json"
        shutil.copyfile(Path(row["original_workdir"]) / review_path.name, review_path)
        review = load_json_object(review_path)
        analysis_path = directory / "submission_no_output_analysis.json"
        analysis = analyze(directory, original.THRESHOLDS, list(range(45, len(read(directory / "POSCAR")))), write_output=False)
        write_json_exclusive(analysis_path, analysis)
        bindings = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in (
            ("geometry", geometry), ("analysis", analysis_path), ("thresholds", original.THRESHOLDS),
            ("preflight", directory / "submission_preflight.json"), ("validation", review_path))}
        kwargs = dict(climb=False, path_reviewed=True, preflight=report, validation=review, source_bindings=bindings)
        evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
        auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": original.ACTION,
                "calculation_kind": "diagnostic_static", "authorized_at": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(AUTH), "sha256": sha256_file(AUTH)},
                "target": {"server_alias": original.HOST, "remote_dir": row["proposed_remote_dir"]},
                "workdir_identity": workdir_identity(directory), "bundle_sha256": report["bundle_sha256"],
                "evidence_sha256": execution_evidence_sha256(evidence),
                "potcar": {"source": row["potcar_source"], "sha256": row["potcar_sha256"],
                           "spec_sha256": report["files"]["POTCAR.spec"]}}
        auth_path = directory / "user_execution_authorization.json"
        write_json_exclusive(auth_path, auth)
        bindings["authorization"] = {"path": str(auth_path), "sha256": sha256_file(auth_path)}
        decision = decide_execution({}, analysis, thresholds, authorization=auth, **kwargs)
        decision_path = directory / "execution_decision.json"
        write_json_exclusive(decision_path, decision)
        require_action(decision_path, original.ACTION, decision["state_sha256"])
        ready.append({**row, "decision_sha256": sha256_file(decision_path)})
    write_json_exclusive(OUTPUT / "recovery16_ready.json", {"cases": ready, "proposal_sha256": PROPOSAL_SHA,
        "confirmation_sha256": sha256_file(OUTPUT / "recovery16_human_confirmation.json"),
        "executor_sha256": sha256_file(Path(__file__)), "remote_preflight_sha256": sha256_file(OUTPUT / "recovery16_remote_preflight.json")})
    print({"fresh_canonical_gates_ready": len(ready), "jobs_submitted": 0})


def submit_one(row):
    directory = Path(row["proposed_workdir"])
    if sha256_file(directory / "execution_decision.json") != row["decision_sha256"]:
        raise ValueError("reviewed fresh gate changed")
    state = submission_status(directory)
    if state["status"] == "NOT_RESERVED":
        state = submit(directory, directory / "execution_decision.json", original.HOST,
                       row["proposed_remote_dir"], row["potcar_source"], row["potcar_sha256"], original.ACTION)
    elif state["status"] != "SUBMITTED":
        raise ValueError("unknown fresh attempt must not be retried")
    if (state["status"] != "SUBMITTED" or state["remote_dir"] != row["proposed_remote_dir"]
            or state["gate_decision_sha256"] != row["decision_sha256"]):
        raise ValueError("fresh receipt does not match exact approved scope")
    return {"sample_id": row["sample_id"], "workdir": str(directory), **state}


def run():
    cases = checked_cases()
    ready = load_json_object(OUTPUT / "recovery16_ready.json")
    if (ready["executor_sha256"] != sha256_file(Path(__file__)) or ready["proposal_sha256"] != PROPOSAL_SHA
            or ready["confirmation_sha256"] != sha256_file(OUTPUT / "recovery16_human_confirmation.json")
            or [{k: v for k, v in r.items() if k != "decision_sha256"} for r in ready["cases"]] != cases):
        raise ValueError("reviewed recovery execution binding changed")
    records = []
    for row in ready["cases"]:
        records.append(submit_one(row))
        print(f"recovery {len(records)}/16 {row['sample_id']} job={records[-1]['job_id']}", flush=True)
    checked_cases()
    write_json_exclusive(OUTPUT / "recovery16_submissions.json", {"records": records,
        "proposal_sha256": PROPOSAL_SHA, "old_markers_preserved": True, "training_performed": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "submit"))
    args = parser.parse_args()
    {"prepare": prepare, "submit": run}[args.action]()
