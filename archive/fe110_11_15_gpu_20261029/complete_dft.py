"""Continue only nine unreserved candidates after a pre-reservation path rejection."""
import argparse
from pathlib import Path
import shutil

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import submission_status, submit
from scripts.ts_strategy_engine.execution_gate import require_action
from . import dft

ROOT, OUTPUT, AUTH = dft.ROOT, dft.OUTPUT, dft.AUTH
FIRST = dft.SUBMISSION
REMAINING = OUTPUT / "dft_submission_remaining9_v2"
FINAL = OUTPUT / "dft_submission_complete_v1"
NINE = [f"{n}_{v}" for n in [13, 14, 15] for v in "ABC"]


def prior_state():
    ready = load_json_object(FIRST / "ready_for_submission.json")
    if not source_file_manifest_valid(ready):
        raise ValueError("original reviewed source bindings changed")
    for job in ready["jobs"]:
        expected = "NOT_RESERVED" if job["name"] in NINE else "SUBMITTED"
        if submission_status(Path(job["directory"]))["status"] != expected:
            raise ValueError("prior state changed; inspect before any continuation")
    return ready


def prepare():
    prior = prior_state()
    REMAINING.mkdir()
    dft.configure_executor()
    dft.executor.OUTPUT = REMAINING
    jobs, pots = [], {}
    for original in prior["jobs"]:
        if original["name"] not in NINE:
            continue
        job = {**original, "directory": str(REMAINING / "inputs" / original["name"])}
        if original["name"].startswith("13_"):
            job["potcar_source"] = "~/sbq/Fe110/potcars/Fe_O_C_H/POTCAR"
        spec = " ".join((ROOT / job["path"] / "POTCAR.spec").read_text(encoding="ascii").split())
        pots[spec] = {"source": job["potcar_source"], "sha256": job["potcar_sha256"]}
        jobs.append(job)
    if [j["name"] for j in jobs] != NINE:
        raise ValueError("exact nine untouched candidates required")
    dft.executor.remote_precheck(jobs, pots)
    for job in jobs:
        folder = Path(job["directory"])
        folder.mkdir(parents=True)
        for filename, digest in job["files"].items():
            source = ROOT / job["path"] / filename
            if sha256_file(source) != digest:
                raise ValueError("input bytes changed")
            shutil.copyfile(source, folder / filename)
        job["decision_sha256"] = dft.executor.bind_gate(job)
    write_json_exclusive(REMAINING / "ready_for_submission.json", {"status": "NINE_NEW_GATES_FOR_UNRESERVED_INPUTS", "jobs": jobs,
        "failure": "13_A rejected by require_remote_path before reservation;absolute POTCAR path changed to equivalent verified ~/sbq path",
        "existing_six_resubmitted": False,
        "source_files": source_file_manifest([Path(__file__), FIRST / "ready_for_submission.json", REMAINING / "remote_precheck.json", AUTH] + [Path(j["directory"]) / "submission_decision.json" for j in jobs])})
    print({"new_gates": len(jobs), "already_submitted_untouched": 6}, flush=True)


def execute():
    prior_state()
    ready = load_json_object(REMAINING / "ready_for_submission.json")
    if not source_file_manifest_valid(ready) or [j["name"] for j in ready["jobs"]] != NINE:
        raise ValueError("remaining-nine exact binding changed")
    for job in ready["jobs"]:
        folder = Path(job["directory"])
        if submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("prior or ambiguous remaining submission;never repeat")
        gate = folder / "submission_decision.json"
        require_action(gate, "SUBMIT_VASP", load_json_object(gate)["state_sha256"])
    for job in ready["jobs"]:
        folder = Path(job["directory"])
        receipt = submit(folder, folder / "submission_decision.json", dft.HOST, job["remote_dir"], job["potcar_source"], job["potcar_sha256"], "SUBMIT_VASP")
        if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != job["bundle_sha256"] or receipt["gate_decision_sha256"] != job["decision_sha256"]:
            raise ValueError("receipt differs from newly approved binding")
        print({"name": job["name"], "job_id": receipt["job_id"], "status": receipt["status"]}, flush=True)
    write_json_exclusive(REMAINING / "submission_completed.json", {"status": "NINE_SUBMITTED_SIX_PRIOR_UNTOUCHED",
        "source_files": source_file_manifest([REMAINING / "ready_for_submission.json"] + [Path(j["directory"]) / "submission_record.json" for j in ready["jobs"]])})


def finalize():
    first = load_json_object(FIRST / "ready_for_submission.json")
    second = load_json_object(REMAINING / "ready_for_submission.json")
    if not all(source_file_manifest_valid(r) for r in [first, second]):
        raise ValueError("submission bindings changed")
    replacements = {j["name"]: j for j in second["jobs"]}
    jobs = [replacements.get(j["name"], j) for j in first["jobs"]]
    for job in jobs:
        receipt = submission_status(Path(job["directory"]))
        if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != job["bundle_sha256"]:
            raise ValueError("all fifteen exact native submission receipts required")
    FINAL.mkdir()
    write_json_exclusive(FINAL / "ready_for_submission.json", {"status": "AGGREGATE_15_REVIEWED_SUBMISSION_BINDINGS", "jobs": jobs,
        "source_files": source_file_manifest([FIRST / "ready_for_submission.json", REMAINING / "ready_for_submission.json"])})
    pots = {}
    for directory in [FIRST, REMAINING]:
        pots.update(load_json_object(directory / "remote_precheck.json")["POTCARs"])
    write_json_exclusive(FINAL / "remote_precheck.json", {"is_aggregate": True, "POTCARs": pots,
        "source_files": source_file_manifest([FIRST / "remote_precheck.json", REMAINING / "remote_precheck.json"])})
    write_json_exclusive(FINAL / "submission_completed.json", {"status": "15_SUBMITTED", "jobs": [load_json_object(Path(j["directory"]) / "submission_record.json") for j in jobs],
        "scientific_validity_reviewed": False, "source_files": source_file_manifest([FINAL / "ready_for_submission.json", AUTH] + [Path(j["directory"]) / "submission_record.json" for j in jobs])})
    dft.configure_executor()
    dft.SUBMISSION = FINAL
    dft.executor.OUTPUT = FINAL
    dft.snapshot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "execute", "finalize"])
    args = parser.parse_args()
    {"prepare": prepare, "execute": execute, "finalize": finalize}[args.action]()
