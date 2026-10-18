"""Collect existing adsorption-training evidence; never run a model or submit jobs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.artifact_io import sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6"
DEST = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_calibration_20261018_v1"
REMOTE = "/home/sbq/sbq/adsorption_c2_finetune_20261010_v6"

GPU_READER = r'''
import base64,hashlib,json
from pathlib import Path
root=Path(REMOTE_ROOT);output=root/'output/job_2185'
files={}
for name in ('producer_exit_record.json','development_comparison.json'):
 p=output/name
 if p.stat().st_size>200000:raise ValueError('evidence size cap')
 data=p.read_bytes()
 files[name]={'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
checkpoints={}
for name,p in (('baseline',Path('/home/sbq/sbq/aqcat25/demo_single/model.pt')),('candidate',output/'candidate.pt')):
 before=p.stat();sha=digest(p);after=p.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('checkpoint changed')
 checkpoints[name]={'path':str(p),'sha256':sha,'bytes':before.st_size}
print(json.dumps({'files':files,'checkpoints':checkpoints,'request_sha256':digest(root/'training_request.json'),
 'manifest_sha256':digest(root/'training_manifest.json'),'model_executed':False}))
'''

VASP_PROBE = r'''
import getpass,json,os,socket
from pathlib import Path
p=Path.home()/'sbq'
result={'user':getpass.getuser(),'hostname':socket.gethostname(),'path':str(p),'remote_write':False}
try:
 result['stat_bytes']=p.stat().st_size
 result['access_status']='READABLE' if os.access(str(p),os.R_OK|os.X_OK) else 'ACCESS_DENIED'
except OSError as e:
 result.update(access_status='ACCESS_ERROR',errno=e.errno,error=str(e))
print(json.dumps(result))
'''


def collect() -> None:
    DEST.mkdir(parents=True, exist_ok=False)
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    commands = [
        ("gpu_evidence", ["ssh", "-i", ssh["identity_file"], "-p", str(ssh["port"]),
                          "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                          ssh["user"] + "@" + ssh["host"], "python3 -"],
         "REMOTE_ROOT=" + repr(REMOTE) + "\n" + GPU_READER),
        ("vasp_access_probe", ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                               "sunboquan-codex", "python3 -"], VASP_PROBE),
    ]
    receipts = []
    for name, args, code in commands:
        result = subprocess.run(args, input=code.encode(), capture_output=True, timeout=60, check=False)
        stdout, stderr = DEST / (name + ".json"), DEST / (name + ".stderr.txt")
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        receipts.append({"name": name, "exit_code": result.returncode,
                         "stdout_sha256": sha256_file(stdout), "stderr_sha256": sha256_file(stderr)})
        if result.returncode:
            write_json_exclusive(DEST / "collection_receipt.json", {"status": "FAILED_READ_ONLY_COLLECTION", "records": receipts})
            raise RuntimeError("read-only collection failed; preserve partial receipt: " + name)
    payload = json.loads((DEST / "gpu_evidence.json").read_bytes())
    evidence = DEST / "training_evidence"
    evidence.mkdir()
    for name, entry in payload["files"].items():
        if name not in {"producer_exit_record.json", "development_comparison.json"}:
            raise ValueError("unexpected evidence filename")
        data = base64.b64decode(entry["base64"], validate=True)
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("remote file bytes changed")
        (evidence / name).write_bytes(data)
    validation = subprocess.run([sys.executable, str(OLD / "runtime/force_finetune.py"), "verify",
                                 "--request", str(OLD / "training_request.json")], capture_output=True, check=False)
    (DEST / "local_package_validation.txt").write_bytes(validation.stdout + validation.stderr)
    write_json_exclusive(DEST / "collection_receipt.json", {"status": "COLLECTED_EXISTING_EVIDENCE_ONLY",
        "observed_at": datetime.now(timezone.utc).isoformat(), "records": receipts,
        "local_package_validation_exit_code": validation.returncode,
        "local_package_validation_sha256": sha256_file(DEST / "local_package_validation.txt"),
        "model_executed": False, "gpu_submitted": False, "vasp_submitted": False})
    if validation.returncode:
        raise RuntimeError("existing source package validation failed")


def validate_model_predictions(model: dict, expected: dict, checkpoint_sha: str) -> None:
    if model["checkpoint_sha256"] != checkpoint_sha:
        raise ValueError("checkpoint prediction binding mismatch")
    samples = model["samples"]
    if len(samples) != len(expected) or {s["sample_id"] for s in samples} != set(expected):
        raise ValueError("development sample set mismatch")
    aggregates = {}
    for sample in samples:
        row = expected[sample["sample_id"]]
        if sample["structure_sha256"] != row["structure_sha256"] or sample["role"] != row["sample_role"]:
            raise ValueError("prediction/DFT structure or role mismatch")
        category = "retention" if "retention" in row["sample_role"] else "C2"
        for group, metric in sample["groups"].items():
            count, error = metric["atom_count"], metric["vector_rmse_eV_A"]
            if not count:
                if error is not None:
                    raise ValueError("empty group has finite error")
                continue
            if not isinstance(count, int) or count < 0 or not math.isfinite(error) or error < 0:
                raise ValueError("invalid metric")
            key = category + "/" + group
            previous = aggregates.setdefault(key, [0, 0.0])
            previous[0] += count
            previous[1] += count * error**2
    if set(aggregates) != set(model["groups"]):
        raise ValueError("aggregate group set mismatch")
    for key, (count, squared) in aggregates.items():
        declared = model["groups"][key]
        if declared["atom_count"] != count or not math.isclose(declared["vector_rmse_eV_A"], math.sqrt(squared / count), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("aggregate differs from source sample metrics")


def summarize(comparison: dict, manifest: dict, request_sha: str, checkpoints: dict) -> dict:
    """Review bookkeeping exactly; report regressions as evidence, not acceptance gates."""
    if comparison["request_sha256"] != request_sha or comparison["heldout_consumed"] is not False:
        raise ValueError("stale request or heldout already consumed")
    expected = {row["sample_id"]: row for row in manifest["splits"]["development"]}
    for name in ("baseline", "candidate"):
        validate_model_predictions(comparison["models"][name], expected, checkpoints[name]["sha256"])
    baseline, candidate = [comparison["models"][n]["groups"] for n in ("baseline", "candidate")]
    if set(baseline) != set(candidate):
        raise ValueError("model group coverage differs")
    groups = {}
    for key in baseline:
        before, after = [value[key]["vector_rmse_eV_A"] for value in (baseline, candidate)]
        groups[key] = {"atom_count": baseline[key]["atom_count"], "baseline_vector_RMSE_eV_A": before,
                       "candidate_vector_RMSE_eV_A": after, "change_eV_A": after - before,
                       "reduction_percent": 100 * (before - after) / before if before else None,
                       "trend": "IMPROVED" if after < before else "REGRESSION_WARNING" if after > before else "UNCHANGED"}
    return {"status": "DEVELOPMENT_REVIEW_ONLY_NOT_CALIBRATED_OR_PROMOTED", "groups": groups,
            "development_samples": len(expected), "heldout_consumed": False,
            "geometry_drift_tested": False, "new_06_10_family_validation": False,
            "checkpoint_promoted": False, "acceleration_proved": False}


def review() -> None:
    receipt = json.loads((DEST / "collection_receipt.json").read_bytes())
    if receipt["local_package_validation_exit_code"] != 0:
        raise ValueError("source package failed")
    for row in receipt["records"]:
        if row["exit_code"] or sha256_file(DEST / (row["name"] + ".json")) != row["stdout_sha256"]:
            raise ValueError("collection receipt mismatch")
    payload = json.loads((DEST / "gpu_evidence.json").read_bytes())
    for name, entry in payload["files"].items():
        if sha256_file(DEST / "training_evidence" / name) != entry["sha256"]:
            raise ValueError("collected evidence changed")
    request_sha = sha256_file(OLD / "training_request.json")
    if payload["request_sha256"] != request_sha or payload["manifest_sha256"] != sha256_file(OLD / "training_manifest.json"):
        raise ValueError("remote/local training source mismatch")
    exit_record = json.loads((DEST / "training_evidence/producer_exit_record.json").read_bytes())
    if exit_record["job_id"] != "2185" or exit_record["exit_code"] or exit_record["request_sha256"] != request_sha:
        raise ValueError("training did not complete this request")
    manifest = json.loads((OLD / "training_manifest.json").read_bytes())
    comparison = json.loads((DEST / "training_evidence/development_comparison.json").read_bytes())
    summary = summarize(comparison, manifest, request_sha, payload["checkpoints"])
    summary.update(source_job_id="2185", source_request_sha256=request_sha,
                   source_manifest_sha256=payload["manifest_sha256"], checkpoints=payload["checkpoints"],
                   source_split_counts={key: len(rows) for key, rows in manifest["splits"].items()},
                   current_vasp_access=json.loads((DEST / "vasp_access_probe.json").read_bytes()),
                   screened_current_reference_jobs=["9848801", "9848803", "9848805"],
                   current_06_10_trajectories_added=False)
    write_json_exclusive(DEST / "development_review.json", summary)
    heldout = manifest["splits"]["heldout"]
    write_json_exclusive(DEST / "independent_validation_plan.json", {
        "document_kind": "adsorption_frozen_candidate_validation_plan", "status": "LOCAL_PLAN_NOT_EXECUTION_AUTHORITY",
        "source_request_sha256": request_sha, "source_manifest_sha256": payload["manifest_sha256"],
        "checkpoints": payload["checkpoints"], "heldout_count": len(heldout),
        "heldout": [{key: row[key] for key in ("sample_id", "structure_path", "structure_sha256", "calculation_group", "source_OUTCAR_sha256")} for row in heldout],
        "checks": ["exact-structure baseline/candidate raw force errors separated movableFe/C/O/H and adsorbate",
                   "preserve whole-job split, fixed mask, original force labels and all SIGMA0.20 bindings",
                   "bounded relaxation from reserved VASP minima: graph/site, surface-aware RMSD and movableFe drift",
                   "no energy ranking calibration claim from force-only fine-tuning",
                   "new06-10 family remains separately unvalidated until its readable compatible labels are reviewed"],
        "heldout_epoch_selection": "FORBIDDEN", "optimization_of_heldout_labels": "FORBIDDEN",
        "soft_warnings": "group regressions require magnitude/context review; no invented zero-regression acceptance gate",
        "requires_before_execution": ["separately reviewed hash-bound executable GPU request and explicit user authorization",
                                      "available GPU and current execution-backend contract"],
        "training_authorized": False, "gpu_submitted": False, "vasp_submitted": False,
        "model_promoted": False, "acceleration_proved": False})
    print(json.dumps(summary, indent=2))


def record() -> None:
    summary = json.loads((DEST / "development_review.json").read_bytes())
    pool = json.loads((DEST / "current_trajectories/dataset_review.json").read_bytes())
    split = json.loads((DEST / "current_trajectories/split_review.json").read_bytes())
    if len(pool["samples"]) != 24 or split["retained_counts"] != {"train": 24}:
        raise ValueError("unexpected reviewed label pool")
    evidence_paths = [
        (ROOT / "docs/reviews/fe110_adsorption_calibration_20261018.md", "repository_document"),
        (ROOT / "archive/fe110_adsorption_calibration_20261018/authorization.md", "user_authorization"),
        (DEST / "development_review.json", "module_validation"),
        (DEST / "current_trajectories/dataset_review.json", "module_validation"),
        (DEST / "current_trajectories/split_review.json", "module_validation"),
        (DEST / "independent_validation_plan.json", "repository_document"),
        (DEST / "validation_junit.xml", "module_validation"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    # Refresh final documentation/test bindings with a superseding event;
    # never edit the earlier immutable preparation event.
    event_id = "task-fe110-adsorption-calibration-ready-20261018"
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "Reuse completed adsorption candidate2185 and24 new compatible trajectory labels; development improved, independent and geometry validation pending; no new scientific job.",
        "evidence": [{"locator": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path),
                      "authority": authority, "observed_at": now} for path, authority in evidence_paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-calibration-prepared-20261018"],
        "payload": {
            "objective": "Calibrate adsorption acceleration using existing compatible VASP structures/trajectories and the existing frozen AQCat25 candidate; preserve ongoing VASP work.",
            "phase": "active",
            "current_evidence": [
                "Existing training2185 completed with producer exit0;candidate SHA" + summary["checkpoints"]["candidate"]["sha256"] + ";not promoted.",
                "Original source package34train/12development/16heldout passed hash/source/mask validation;12development groups improve;C2adsorbate vectorRMSE0.222462→0.083809eV/A.",
                "No new model was run;old16heldout remain unconsumed. Development agreement does not establish better minima or measured VASP speedup.",
                "Recovered3 complete existing jobs06_C/07_B/08_A:24 exact-frame labels;SIGMA0.20/POTCAR/SCF/coordinates/force/energy/fixed-layer/graph checks pass;no cross-split near duplicates against old62rows.",
                "Four-job read did not complete within its180s budget;08_B missing,partial receipt preserved,no VASP rerun or repeated full collection. XDATCAR cell rounding handled using input lattice and printed precision.",
                "New24rows are future training candidates only. Existing15VASP jobs remain untouched;no new training,GPU/VASP submission or model-default change."
            ],
            "one_executable_step": "Prepare one hash-bound executable GPU validation request for frozen2185:16heldout exact-force comparisons plus bounded geometry drift/same-seed comparisons; obtain separate submission authority before execution.",
            "submission_boundary": "Local collection,preparation and review only. No new scientific execution,training,retry,promotion or existing-job stop authorized.",
            "done_when": [
                "Existing2185 producer/checkpoint/development evidence is retrieved byte-for-byte and reviewed without an independent-calibration or speedup claim.",
                "Available new trajectory labels are source/SCF/geometry/compatibility/split reviewed;missing08_B and original heldout isolation remain explicit.",
                "A separately authorized GPU validation has tested the frozen candidate on heldout forces and bounded DFT-minimum/same-seed geometry before adoption."
            ],
            "constraints": [
                "Previously screened06_C/07_B/08_A are not pristine heldout data;do not train/select epochs on the frozen16.",
                "Force-only adaptation does not calibrate adsorption-energy ranking;do not loosen DFT criteria or claim acceleration without matched VASP timing.",
                "MatRIS remains an audit option and all backend roles remain unchanged."
            ],
            "authoritative_references": ["configs/execution_backends.yaml", "modules/adsorption_workflow/README.md",
                "docs/reviews/fe110_adsorption_calibration_20261018.md", (DEST / "development_review.json").relative_to(ROOT).as_posix()]
        }}
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"event": str(target), "sha256": sha256_file(target)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "review", "record"))
    args = parser.parse_args()
    {"collect": collect, "review": review, "record": record}[args.action]()


if __name__ == "__main__":
    main()
