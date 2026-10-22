"""Submit the user's frozen 280-label batch through the canonical per-job gate."""
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
SAMPLING = ROOT / "calculations/fe110_reico_pilot300_20261022/sampling93_v1"
DEST = SAMPLING / "dft_inputs_v1"
BATCH_SHA = "117bdce2fdbd2220a48412976db7e1a295151b1ff0b48c7a869a47dff2f6ec08"
SELECTION_SHA = "022e46102437678a541c587bbd30aaa1e0db27992ea8fcedca3092343701cd34"
COUNT = 280
AUTH_SOURCE = ROOT / "docs/reviews/fe110_reico_sampling93_20261022/dft_submission_authorization.md"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/diagnostics/reico_pilot292_labels_20261022_v1"
ACTION = "SUBMIT_DIAGNOSTIC_VASP"
POTCARS = {
    "Fe C O H": ("~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR", "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"),
    "Fe C H": ("~/sbq/Fe110/potcars/Fe_C_H/POTCAR", "bd39c0ebfbbe6207bc8e1b976677b4687ae2d2956f5a74dc1dea3298adef063a"),
}


def saved(path, value):
    write_json_exclusive(path, value)
    return load_json_object(path)


def checked_batch():
    if sha256_file(DEST / "batch_request.json") != BATCH_SHA:
        raise ValueError("authorized batch changed")
    batch = load_json_object(DEST / "batch_request.json")
    if len(batch["samples"]) != COUNT or len({r["sample_id"] for r in batch["samples"]}) != COUNT:
        raise ValueError("authorized sample scope changed")
    if batch["selection_sha256"] != SELECTION_SHA:
        raise ValueError("selection binding changed")
    for row in batch["samples"]:
        directory = Path(row["directory"])
        if directory.resolve() != (DEST / row["sample_id"]).resolve() or row["cores"] != 32:
            raise ValueError("sample directory or resource scope changed")
        if any(sha256_file(directory / n) != s for n, s in row["input_hashes"].items()):
            raise ValueError("prepared input bytes changed")
        for name in ("structure", "frame_metadata"):
            if sha256_file(Path(row[name + "_path"])) != row[name + "_sha256"]:
                raise ValueError("sample source bytes changed")
    return batch


def sources():
    selection_path = SAMPLING / "selection/selected_frames.json"
    if sha256_file(selection_path) != SELECTION_SHA:
        raise ValueError("reviewed selection changed")
    result = {}
    for source in load_json_object(selection_path)["source_runs"]:
        package = Path(source["package"])
        manifest = package / "returned/return_manifest.json"
        request_path = package / "validation_request.json"
        if (sha256_file(manifest) != source["manifest_sha256"]
                or sha256_file(request_path) != source["producer"]["request_sha256"]):
            raise ValueError("sampling source evidence changed")
        request = load_json_object(request_path)
        config_path = package / "evidence/geometry_config.json"
        config = load_json_object(config_path)
        if sha256_file(config_path) != request["generation_config_sha256"]:
            raise ValueError("sampling geometry guards changed")
        result[package.resolve()] = (request, config, manifest, request_path, config_path)
    return result


def prepare_one(row, source_data, thresholds, geometry_path, live):
    directory = DEST / row["sample_id"]
    if submission_status(directory)["status"] != "NOT_RESERVED":
        raise ValueError("existing submission state;inspect receipts before recovery")
    report = preflight(directory, "diagnostic_static", write_report=False)
    if not report["passed"] or report != load_json_object(directory / "submission_preflight.json"):
        raise ValueError("current preflight differs from frozen preparation")
    profile = load_json_object(directory / "input_profile.json")
    if sha256_file(Path(profile["profile_path"])) != profile["profile_sha256"]:
        raise ValueError("scientific profile changed")
    incar = load_json_object(directory / "incar_validation.json")
    binding = load_json_object(directory / "incar_validation_binding.json")
    if (incar["status"] != "PASS" or incar["errors"] or incar["warnings"]
            or sha256_file(Path(binding["source"])) != binding["source_sha256"]
            or any(sha256_file(directory / n) != binding[n + "_sha256"] for n in ("INCAR", "POSCAR"))):
        raise ValueError("INCAR validation binding changed")
    frame = Path(row["structure_path"])
    package = frame.parents[4].resolve()
    request, config, manifest, request_path, config_path = source_data[package]
    if frame.parent != package / "returned/output/sampling" / row["family_id"]:
        raise ValueError("source family path changed")
    initial = read(frame.parent / "step_000.vasp", format="vasp")
    current = read(directory / "POSCAR", format="vasp")
    audit = geometry_audit(current, initial, config["pair_minimum_A"], request["limits"])
    if audit["failures"]:
        raise ValueError("sampled geometry guard failed")
    review_path = directory / "submission_geometry_review.json"
    review = saved(review_path, {
        "document_kind": "fe110_reico_selected_static_submission_review",
        "status": "REVIEWED_FOR_FIXED_GEOMETRY_DFT_LABEL_ONLY", "sample_id": row["sample_id"],
        "structure_sha256": row["structure_sha256"], "source_batch_sha256": BATCH_SHA,
        "selection_sha256": SELECTION_SHA, "sampling_request_sha256": sha256_file(request_path),
        "source_return_manifest_sha256": sha256_file(manifest), "geometry_config_sha256": sha256_file(config_path),
        "incar_validation_sha256": sha256_file(directory / "incar_validation.json"),
        "pairwise_geometry_audit": audit, "stable_adsorption_accepted": False,
        "scope": "fixed geometry energy/forces/magnetic label;no optimizer/minimum/TS acceptance",
    })
    analysis_path = directory / "submission_no_output_analysis.json"
    analysis = saved(analysis_path, analyze(directory, THRESHOLDS, list(range(45, len(current))), write_output=False))
    bindings = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in (
        ("geometry", geometry_path), ("analysis", analysis_path), ("thresholds", THRESHOLDS),
        ("preflight", directory / "submission_preflight.json"), ("validation", review_path))}
    kwargs = dict(climb=False, path_reviewed=True, preflight=report, validation=review, source_bindings=bindings)
    evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
    potcar_path, potcar_sha = POTCARS[" ".join((directory / "POTCAR.spec").read_text().split())]
    if live["POTCARs"][potcar_path] != potcar_sha:
        raise ValueError("live POTCAR mismatch")
    auth_path = directory / "user_execution_authorization.json"
    auth = saved(auth_path, {
        "schema_version": 1, "document_kind": "user_execution_authorization", "action": ACTION,
        "calculation_kind": "diagnostic_static", "authorized_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(AUTH_SOURCE), "sha256": sha256_file(AUTH_SOURCE)},
        "target": {"server_alias": HOST, "remote_dir": REMOTE + "/" + row["sample_id"]},
        "workdir_identity": workdir_identity(directory), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence),
        "potcar": {"source": potcar_path, "sha256": potcar_sha, "spec_sha256": report["files"]["POTCAR.spec"]},
    })
    bindings["authorization"] = {"path": str(auth_path), "sha256": sha256_file(auth_path)}
    decision = decide_execution({}, analysis, thresholds, authorization=auth, **kwargs)
    path = directory / "execution_decision.json"
    saved(path, decision)
    require_action(path, ACTION, decision["state_sha256"])
    return {"sample_id": row["sample_id"], "decision_sha256": sha256_file(path),
            "potcar_source": potcar_path, "potcar_sha256": potcar_sha}


def prepare():
    batch = checked_batch()
    remote = load_json_object(DEST / "remote_presubmission_check.json")
    live = remote["parsed"]
    if (remote["exit_code"] != 0 or remote["source_batch_sha256"] != BATCH_SHA
            or live["user"] != "nsgkn_chengdj3" or not live["VASP_executable"]
            or not live["intel_environment_exists"] or live["remote_root_exists"]
            or live["account_resource_query"]["returncode"] != 0):
        raise ValueError("remote runtime, account or new target is unavailable")
    source_data = sources()
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    geometry_path = DEST / "diagnostic_geometry_adapter.json"
    saved(geometry_path, {})
    ready = []
    for row in batch["samples"]:
        ready.append(prepare_one(row, source_data, thresholds, geometry_path, live))
        if len(ready) % 25 == 0:
            print(f"gates {len(ready)}/{COUNT}", flush=True)
    first = load_json_object(DEST / "first24_proposal.json")
    first_ids = [r["sample_id"] for r in first["samples"]]
    if first["source_prepared_batch_sha256"] != BATCH_SHA or len(set(first_ids)) != 24:
        raise ValueError("first submission tranche changed")
    by_id = {r["sample_id"]: r for r in ready}
    ordered = [by_id[n] for n in first_ids] + [r for r in ready if r["sample_id"] not in first_ids]
    saved(DEST / "ready_for_submission.json", {"batch_sha256": BATCH_SHA, "samples": ordered,
          "remote_preflight_sha256": sha256_file(DEST / "remote_presubmission_check.json"),
          "authorization_source_sha256": sha256_file(AUTH_SOURCE), "cores_per_job": 32, "account_core_limit": 128})
    print(f"HASH_BOUND_STATIC_GATES_READY {len(ordered)}", flush=True)


def checked_ready():
    batch = checked_batch()
    ready = load_json_object(DEST / "ready_for_submission.json")
    rows = ready["samples"]
    if (ready["batch_sha256"] != BATCH_SHA or len(rows) != COUNT
            or {r["sample_id"] for r in rows} != {r["sample_id"] for r in batch["samples"]}):
        raise ValueError("reviewed submission scope changed")
    for row in rows:
        if sha256_file(DEST / row["sample_id"] / "execution_decision.json") != row["decision_sha256"]:
            raise ValueError("reviewed gate changed")
    return rows


def submit_batch(start=0, count=24):
    rows = checked_ready()
    if start < 0 or count <= 0 or start + count > len(rows):
        raise ValueError("invalid bounded submission tranche")
    records = []
    for row in rows[start:start + count]:
        directory = DEST / row["sample_id"]
        state = submission_status(directory)
        if state["status"] == "SUBMITTED":
            record = load_json_object(directory / "submission_record.json")
        elif state["status"] == "NOT_RESERVED":
            record = submit(directory, directory / "execution_decision.json", HOST,
                            REMOTE + "/" + row["sample_id"], row["potcar_source"], row["potcar_sha256"], ACTION)
        else:
            raise RuntimeError("unknown reservation outcome;inspect remote and receipts;never retry automatically")
        if (record["status"] != "SUBMITTED" or record["gate_decision_sha256"] != row["decision_sha256"]
                or record["remote_dir"] != REMOTE + "/" + row["sample_id"]):
            raise ValueError("submission receipt does not match the reviewed scope")
        records.append({"sample_id": row["sample_id"], **record})
        print(f"{start + len(records)}/{len(rows)} {row['sample_id']} job={record['job_id']}", flush=True)
    path = DEST / f"submission_tranche_{start:03d}_{start + count:03d}.json"
    summary = {"status": "TRANCHE_SUBMITTED", "batch_sha256": BATCH_SHA, "start": start,
               "count": count, "records": records, "training_performed": False}
    if path.exists():
        if load_json_object(path) != summary:
            raise ValueError("existing tranche receipt differs;inspect before recovery")
    else:
        saved(path, summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "submit"))
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=24)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        submit_batch(args.start, args.count)
