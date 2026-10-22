"""Bind and submit exactly six authorized sampled statics using canonical owners."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml
from ase.io import read

from scripts.adsorption.reico_sampling import geometry_audit
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

ROOT = Path(__file__).resolve().parents[2]
SAMPLING = ROOT / "calculations/fe110_reico_pilot300_20261022/sampling6_v1"
DEST = SAMPLING / "dft_review6_v1"
BATCH_SHA = "037509b016c3e42c94a3c2a3e9cff2db375b7017322cc78423e914a8cdfa5696"
SAMPLES = ["family_0029_step010", "family_0002_step020", "family_0007_step010",
           "family_0078_step020", "family_0052_step007", "family_0004_step020"]
AUTH_SOURCE = ROOT / "docs/reviews/fe110_reico_sampling6_20261022/dft_submission_authorization.md"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/diagnostics/reico_sampling6_force_checks_20261022_v1"
ACTION = "SUBMIT_DIAGNOSTIC_VASP"


def checked_batch():
    if sha256_file(DEST / "batch_request.json") != BATCH_SHA:
        raise ValueError("the authorized six-input batch changed")
    batch = load_json_object(DEST / "batch_request.json")
    if [r["sample_id"] for r in batch["samples"]] != SAMPLES:
        raise ValueError("six-sample scope changed")
    for row in batch["samples"]:
        directory = ROOT / row["directory"]
        if directory.resolve() != (DEST / row["sample_id"]).resolve():
            raise ValueError("sample directory changed")
        if any(sha256_file(directory / name) != sha for name, sha in row["input_hashes"].items()):
            raise ValueError("prepared input bytes changed")
    return batch


def saved(path, value):
    write_json_exclusive(path, value)
    return load_json_object(path)


def prepare():
    batch = checked_batch()
    remote = load_json_object(DEST / "remote_presubmission_check.json")
    if remote["exit_code"] != 0:
        raise ValueError("remote preflight failed")
    import json
    live = json.loads(remote["stdout"])
    if (live["user"] != "nsgkn_chengdj3" or not live["VASP_executable"]
            or not live["intel_environment_exists"]
            or any(v["exists"] or v["reservation_exists"] for v in live["targets"].values())):
        raise ValueError("remote runtime/target is unavailable;do not submit")
    config = load_json_object(SAMPLING / "evidence/geometry_config.json")
    sampling_request = load_json_object(SAMPLING / "validation_request.json")
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    geometry_path = DEST / "diagnostic_geometry_adapter.json"
    saved(geometry_path, {})
    ready = []
    for row in batch["samples"]:
        directory = DEST / row["sample_id"]
        if submission_status(directory)["status"] != "NOT_RESERVED":
            raise ValueError("existing submission state;inspect receipt instead of retrying")
        report = preflight(directory, "diagnostic_static", write_report=False)
        if not report["passed"] or report != load_json_object(directory / "submission_preflight.json"):
            raise ValueError("current preflight no longer matches saved inputs")
        profile = load_json_object(directory / "input_profile.json")
        if sha256_file(Path(profile["profile_path"])) != profile["profile_sha256"]:
            raise ValueError("scientific profile changed")
        incar = load_json_object(directory / "incar_validation.json")
        if incar["status"] != "PASS" or incar["errors"]:
            raise ValueError("INCAR validation failed")
        initial = read(SAMPLING / "returned/output/sampling" / row["family_id"] / "step_000.vasp", format="vasp")
        current = read(directory / "POSCAR", format="vasp")
        audit = geometry_audit(current, initial, config["pair_minimum_A"], sampling_request["limits"])
        if audit["failures"] or sha256_file(ROOT / row["structure_path"]) != row["structure_sha256"]:
            raise ValueError("reviewed sampled geometry changed")
        review_path = directory / "submission_geometry_review.json"
        review = saved(review_path, {"document_kind": "fe110_reico_sampled_static_submission_review",
            "status": "REVIEWED_FOR_FIXED_GEOMETRY_DFT_LABEL_ONLY", "sample_id": row["sample_id"],
            "structure_sha256": row["structure_sha256"], "source_batch_sha256": BATCH_SHA,
            "sampling_request_sha256": sha256_file(SAMPLING / "validation_request.json"),
            "source_return_manifest_sha256": sha256_file(SAMPLING / "returned/return_manifest.json"),
            "incar_validation_sha256": sha256_file(directory / "incar_validation.json"),
            "pairwise_geometry_audit": audit, "stable_adsorption_accepted": False,
            "scope": "single fixed geometry E/F/magnetic probe;no NEB or TS claim"})
        analysis_path = directory / "submission_no_output_analysis.json"
        analysis = saved(analysis_path, analyze(directory, THRESHOLDS, list(range(45, len(current))), write_output=False))
        bindings = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in (
            ("geometry", geometry_path), ("analysis", analysis_path), ("thresholds", THRESHOLDS),
            ("preflight", directory / "submission_preflight.json"), ("validation", review_path))}
        kwargs = dict(climb=False, path_reviewed=True, preflight=report, validation=review, source_bindings=bindings)
        evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
        parent = ROOT / "calculations/fe110_reico_pilot300_20261022/probe6_v1" / row["family_id"]
        receipt = load_json_object(parent / "submission_record.json")
        potcar_path, potcar_sha = receipt["potcar_source"], receipt["potcar_sha256"]
        if live["POTCARs"][potcar_path] != potcar_sha:
            raise ValueError("live POTCAR hash mismatch")
        auth_path = directory / "user_execution_authorization.json"
        auth = saved(auth_path, {"schema_version": 1, "document_kind": "user_execution_authorization",
            "action": ACTION, "calculation_kind": "diagnostic_static", "authorized_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(AUTH_SOURCE), "sha256": sha256_file(AUTH_SOURCE)},
            "target": {"server_alias": HOST, "remote_dir": REMOTE + "/" + row["sample_id"]},
            "workdir_identity": workdir_identity(directory), "bundle_sha256": report["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(evidence), "potcar": {
                "source": potcar_path, "sha256": potcar_sha, "spec_sha256": report["files"]["POTCAR.spec"]}})
        bindings["authorization"] = {"path": str(auth_path), "sha256": sha256_file(auth_path)}
        decision = decide_execution({}, analysis, thresholds, authorization=auth, **kwargs)
        decision_path = directory / "execution_decision.json"
        saved(decision_path, decision)
        require_action(decision_path, ACTION, decision["state_sha256"])
        ready.append({"sample_id": row["sample_id"], "decision_sha256": sha256_file(decision_path),
                      "potcar_source": potcar_path, "potcar_sha256": potcar_sha})
    saved(DEST / "ready_for_submission.json", {"batch_sha256": BATCH_SHA, "samples": ready})
    print("SIX_HASH_BOUND_STATIC_GATES_READY")


def submit_batch():
    checked_batch()
    ready = load_json_object(DEST / "ready_for_submission.json")
    if ready["batch_sha256"] != BATCH_SHA or [s["sample_id"] for s in ready["samples"]] != SAMPLES:
        raise ValueError("reviewed submission scope changed")
    records = []
    for row in ready["samples"]:
        directory = DEST / row["sample_id"]
        decision = directory / "execution_decision.json"
        if sha256_file(decision) != row["decision_sha256"]:
            raise ValueError("reviewed gate changed")
        state = submission_status(directory)
        if state["status"] == "SUBMITTED":
            record = load_json_object(directory / "submission_record.json")
        elif state["status"] == "NOT_RESERVED":
            record = submit(directory, decision, HOST, REMOTE + "/" + row["sample_id"],
                            row["potcar_source"], row["potcar_sha256"], ACTION)
        else:
            raise RuntimeError("unknown reservation outcome;do not repeat submission")
        if (record["gate_decision_sha256"] != row["decision_sha256"]
                or record["remote_dir"] != REMOTE + "/" + row["sample_id"]):
            raise ValueError("submission receipt does not match this reviewed scope")
        records.append({"sample_id": row["sample_id"], **record})
        print(row["sample_id"] + " job=" + record["job_id"], flush=True)
    saved(DEST / "submission_summary.json", {"status": "SIX_SAMPLED_STATICS_SUBMITTED", "records": records,
          "batch_sha256": BATCH_SHA, "new_DFT_jobs_submitted": 6, "training_performed": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "submit"))
    args = parser.parse_args()
    {"prepare": prepare, "submit": submit_batch}[args.action]()
