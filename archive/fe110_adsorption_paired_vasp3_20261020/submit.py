"""Exact-six-job authorized adapter; canonical gate/executor own execution."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from archive.fe110_adsorption_paired_vasp3_20261020.prepare import (
    ARMS, DEST, NAMES, ROOT, check_pair,
)
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.execution_backends import load_execution_backends, require_vasp_backend
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action, validate_decision

AUTH_SOURCE = Path(__file__).with_name("submission_authorization.md")


def verified_manifest() -> dict:
    manifest = load_json_object(DEST / "batch_manifest.json")
    receipt = load_json_object(DEST / "preparation_receipt_v2.json")
    expected = {(n, a) for n in NAMES for a in ARMS}
    if len(manifest["jobs"]) != 6 or {(j["name"], j["arm"]) for j in manifest["jobs"]} != expected:
        raise ValueError("exact six-job scope changed")
    binding = next(s for s in receipt["sources"] if s["path"].endswith("/batch_manifest.json"))
    if sha256_file(DEST / "batch_manifest.json") != binding["sha256"]:
        raise ValueError("prepared manifest changed")
    for job in manifest["jobs"]:
        folder = ROOT / job["path"]
        if submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("existing submission/reservation;inspect before any retry")
        for filename, digest in job["files"].items():
            if sha256_file(folder / filename) != digest:
                raise ValueError("prepared input changed:" + filename)
        if preflight(folder, "adsorption_relaxation", write_report=False) != load_json_object(folder / "submission_preflight.json"):
            raise ValueError("preflight/retry evidence changed;new review needed")
    for name in NAMES:
        check_pair(DEST / name / ARMS[0], DEST / name / ARMS[1])
    return manifest


def remote_precheck(manifest: dict) -> dict:
    backend = load_execution_backends().vasp
    require_vasp_backend(backend.server_alias, backend.name)
    jobs = manifest["jobs"]
    if any(j["host"] != backend.server_alias for j in jobs):
        raise ValueError("backend changed")
    payload = json.dumps({"jobs": jobs})
    code = """import os,json,hashlib,getpass,socket
data=json.loads(PAYLOAD)
pots={}
targets=[]
for j in data['jobs']:
    p=os.path.expanduser(j['potcar_source'])
    if p not in pots:
        with open(p,'rb') as f:
            raw=f.read()
        pots[p]={'source':j['potcar_source'],'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                 'TITEL':[line.strip() for line in raw.decode('ascii').splitlines() if 'TITEL' in line]}
    target=os.path.expanduser(j['proposed_remote_dir'])
    targets.append({'name':j['name'],'arm':j['arm'],'target':target,
                    'exists':os.path.lexists(target),'reservation_exists':os.path.lexists(target+'.submission-reservation')})
print(json.dumps({'user':getpass.getuser(),'hostname':socket.gethostname(),'potcars':list(pots.values()),'targets':targets}))
""".replace("PAYLOAD", repr(payload))
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", backend.server_alias, "python3", "-"]
    result = subprocess.run(argv, input=code, capture_output=True, text=True, timeout=60, check=False)
    observed = {"argv": argv, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                "checked_at": datetime.now(timezone.utc).isoformat()}
    write_json_exclusive(DEST / "remote_submission_precheck.json", observed)
    if result.returncode:
        raise RuntimeError("remote precheck failed;see retained receipt")
    parsed = json.loads(result.stdout)
    expected_user = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["vasp"]["user"]
    if parsed["user"] != expected_user or any(t["exists"] or t["reservation_exists"] for t in parsed["targets"]):
        raise ValueError("remote user/target freshness check failed")
    pots = {p["source"]: p for p in parsed["potcars"]}
    for job in jobs:
        pot = pots[job["potcar_source"]]
        spec = (ROOT / job["path"] / "POTCAR.spec").read_text(encoding="ascii").split()
        species = [title.split("PAW_PBE", 1)[1].split()[0] for title in pot["TITEL"]]
        if pot["sha256"] != job["potcar_sha256"] or species != spec:
            raise ValueError("remote POTCAR hash/family/species order mismatch")
    return parsed


def authorize(manifest: dict) -> None:
    threshold = ROOT / "configs/true_fe110_production.yaml"
    thresholds = yaml.safe_load(threshold.read_text(encoding="utf-8"))
    for job in manifest["jobs"]:
        folder = ROOT / job["path"]
        report = load_json_object(folder / "submission_preflight.json")
        bindings = {"thresholds": {"path": str(threshold), "sha256": sha256_file(threshold)},
                    "preflight": {"path": str(folder / "submission_preflight.json"),
                                  "sha256": sha256_file(folder / "submission_preflight.json")}}
        evidence = decide_execution({}, {}, thresholds, climb=False, path_reviewed=True,
                                    preflight=report, source_bindings=bindings)["EVIDENCE"]
        auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "SUBMIT_VASP",
                "calculation_kind": "adsorption_relaxation", "authorized_at": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(AUTH_SOURCE.resolve()), "sha256": sha256_file(AUTH_SOURCE)},
                "target": {"server_alias": job["host"], "remote_dir": job["proposed_remote_dir"]},
                "workdir_identity": workdir_identity(folder), "bundle_sha256": report["bundle_sha256"],
                "evidence_sha256": execution_evidence_sha256(evidence),
                "potcar": {"source": job["potcar_source"], "sha256": job["potcar_sha256"],
                           "spec_sha256": report["files"]["POTCAR.spec"]}}
        path = folder / "user_execution_authorization.json"
        write_json_exclusive(path, auth)
        bindings["authorization"] = {"path": str(path), "sha256": sha256_file(path)}
        decision = decide_execution({}, {}, thresholds, climb=False, path_reviewed=True,
                                    preflight=report, source_bindings=bindings, authorization=auth)
        validate_decision(decision)
        if decision["ALLOWED_ACTIONS"] != ["SUBMIT_VASP"]:
            raise ValueError("canonical gate refused:" + str(decision.get("execution_authorization_error")))
        write_json_exclusive(folder / "submission_decision.json", decision)


def launch(manifest: dict) -> None:
    # Validate all six before making the first scheduler write.
    for job in manifest["jobs"]:
        path = ROOT / job["path"] / "submission_decision.json"
        decision = load_json_object(path)
        require_action(path, "SUBMIT_VASP", decision["state_sha256"])
    for job in manifest["jobs"]:
        folder = ROOT / job["path"]
        result = submit(folder, folder / "submission_decision.json", job["host"],
                        job["proposed_remote_dir"], job["potcar_source"], job["potcar_sha256"], "SUBMIT_VASP")
        print(job["name"], job["arm"], result["job_id"], result["status"], flush=True)


def snapshot() -> dict:
    manifest = load_json_object(DEST / "batch_manifest.json")
    records = []
    for job in manifest["jobs"]:
        folder = ROOT / job["path"]
        status = submission_status(folder)
        if status["status"] != "SUBMITTED":
            raise ValueError("partial/unknown submission;inspect individual receipts")
        evidence = query_lsf_job(status["job_id"], stage="adsorption_relaxation")
        write_json_exclusive(folder / "scheduler_after_submission.json", evidence)
        records.append({"name": job["name"], "arm": job["arm"], "job_id": status["job_id"],
                        "scheduler_status": evidence["status"], "remote_dir": status["remote_dir"], "cores": 32,
                        "receipt_sha256": sha256_file(folder / "submission_record.json"),
                        "scheduler_evidence_sha256": sha256_file(folder / "scheduler_after_submission.json"),
                        "scientific_status": "not_assessed", "energy_eV": None, "force_eV_A": None})
    summary = {"checked_at": datetime.now(timezone.utc).isoformat(), "records": records,
               "source_manifest_sha256": sha256_file(DEST / "batch_manifest.json"),
               "new_VASP_submitted": 6, "new_GPU": 0, "model_promoted": False, "measured_speedup": False}
    write_json_exclusive(DEST / "submission_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("authorize", "launch", "snapshot"), required=True)
    args = parser.parse_args()
    if args.phase == "authorize":
        manifest = verified_manifest()
        remote_precheck(manifest)
        authorize(manifest)
        print("SIX_CURRENT_SUBMIT_VASP_GATES_READY")
    elif args.phase == "launch":
        launch(verified_manifest())
    else:
        print(json.dumps(snapshot()))


if __name__ == "__main__":
    main()
