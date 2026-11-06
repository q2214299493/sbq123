"""Bounded two-job first-ready execution guard; never submit or retry calculations."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .deploy import OUT, REMOTE, ROOT, connection
from .prepare import PACKAGE

PARENT_SHA = "b95896f6da62f52d504c97663b4a30e0b3121872463a73f95ea277f6edaf553d"
MZ_ROOT = "/home/sbq/sbq/fe110_c2_supplement_gpu_20261106_v1"
TERMINAL = {"CANCELLED", "FAILED", "COMPLETED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED"}


def bindings():
    parent = load_json_object(ROOT / "calculations/fe110_c2_site_supplement_20261106/gpu_slurm_ft512_20261106_v1/submission_receipt.json")
    child = load_json_object(OUT / "submission_receipt.json")
    request = PACKAGE / "request.json"
    auth = load_json_object(PACKAGE / "authorization.json")
    race = load_json_object(OUT / "coordinator_authorization.json")
    peer = load_json_object(request)["arbitration"]
    if (parent["job_id"] != "11396" or parent["request_sha256"] != PARENT_SHA
            or sha256_file(request) != child["request_sha256"]
            or race["coordinator_source_sha256"] != sha256_file(Path(__file__))
            or race["supersedes_preparation_source_sha256"] != auth["coordinator_source_sha256"]
            or race["child_job_id"] != child["job_id"] or race["request_sha256"] != child["request_sha256"]
            or race["peer_job_id"] != peer["peer_job_id"] or race["peer_request_sha256"] != peer["peer_request_sha256"]
            or race["action"] != "SELECT_FIRST_READY_CANCEL_ONLY_REPLICA" or not race["user_authorized"]
            or auth["request_sha256"] != child["request_sha256"] or not auth["cancel_only_redundant_replica"]
            or auth["action"] != "RUN_SECOND_GPU_REPLICA_KEEP_FIRST" or not auth["user_authorized"]
            or auth["parent_request_sha256"] != PARENT_SHA):
        raise ValueError("two-job authorization/source binding changed")
    if not child["job_id"].isdigit():
        raise ValueError("actual BUCT2 job id required")
    return {"aqcat_gpu": {"job_id": peer["peer_job_id"], "sha256": peer["peer_request_sha256"], "root": peer["peer_remote_root"]},
            "buct2_gpu": {"job_id": child["job_id"], "sha256": child["request_sha256"], "root": REMOTE}}


def remote(backend, code, payload=None):
    args, dest = connection(backend)
    args += ["-T", dest, "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote(code)]
    p = subprocess.run(args, input=payload, capture_output=True, timeout=35, check=False)
    if p.returncode:
        raise RuntimeError(backend + " remote query/action failed: " + p.stderr.decode("utf-8", "replace")[:1500])
    if len(p.stdout) > 65536:
        raise ValueError("unexpected oversized arbitration reply")
    return json.loads(p.stdout)


def observe(backend, binding):
    code = r'''import datetime,json,re,subprocess
from pathlib import Path
p=subprocess.run(['scontrol','show','job','-o',JOB],capture_output=True,text=True,timeout=15)
if p.returncode:raise RuntimeError(p.stderr[:1000])
f=dict(re.findall(r'(\w+)=([^\s]+)',p.stdout))
if f.get('JobId')!=JOB or f.get('Comment')!=SHA or f.get('UserId')!='sbq(1024)':raise ValueError('native job ownership/request mismatch')
def small(name):
 path=Path(ROOT)/name
 if not path.is_file():return None
 if path.stat().st_size>16384:raise ValueError('oversize producer evidence')
 return json.loads(path.read_bytes())
r={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job_id':JOB,'request_sha256':SHA,'state':f['JobState'],'start_time':f.get('StartTime'),'tz_offset_seconds':int(datetime.datetime.now().astimezone().utcoffset().total_seconds()),'scheduler_raw':p.stdout,'ready':small('output/gpu_ready.json'),'model_device':small('output/model_device.json'),'producer_exit':small('output/producer_exit_record.json')}
print(json.dumps(r))
'''
    constants = "JOB=" + repr(binding["job_id"]) + "\nSHA=" + repr(binding["sha256"]) + "\nROOT=" + repr(binding["root"]) + "\n"
    return remote(backend, constants + code)


def eligible(backend, snapshot):
    if snapshot["state"] not in {"RUNNING", "COMPLETED"}:
        return False
    if snapshot.get("producer_exit") is not None and snapshot["producer_exit"].get("exit_code") != 0:
        return False
    if backend == "aqcat_gpu":
        return snapshot.get("model_device") is not None
    ready = snapshot.get("ready")
    if not (snapshot["state"] == "RUNNING" and ready and ready.get("request_sha256") == snapshot["request_sha256"]
            and ready.get("scheduler_job_id") == snapshot["job_id"] and ready.get("model_loaded") is False):
        return False
    age = (datetime.fromisoformat(snapshot["checked_at"]) - datetime.fromisoformat(ready["checked_at"])).total_seconds()
    # Preserve the original queue slot when the replica is too near its permit timeout.
    return 0 <= age <= 60


def choose(snapshots):
    candidates = [name for name in snapshots if eligible(name, snapshots[name])]
    if not candidates:
        return None
    # A complete valid producer is already useful; never discard it to rerun a gated replica.
    mz = snapshots["aqcat_gpu"]
    if "aqcat_gpu" in candidates and mz["state"] == "COMPLETED" and (mz.get("producer_exit") or {}).get("exit_code") == 0:
        return "aqcat_gpu"
    for name in candidates:
        if snapshots[name].get("tz_offset_seconds") != 28800 or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", snapshots[name].get("start_time", "")):
            raise ValueError("unverified scheduler start time/timezone")
    return min(candidates, key=lambda name: (snapshots[name]["start_time"], name != "aqcat_gpu"))


def cancel(backend, binding):
    code = r'''import datetime,json,re,subprocess
from pathlib import Path
root=Path(ROOT);log=root/'race_cancel_receipt.json'
if log.exists():
 record=json.loads(log.read_bytes())
 if record['job_id']!=JOB or record['request_sha256']!=SHA:raise ValueError('different cancellation binding')
 print(json.dumps(record));raise SystemExit(0)
p=subprocess.run(['scontrol','show','job','-o',JOB],capture_output=True,text=True,timeout=15)
if p.returncode:raise RuntimeError(p.stderr[:1000])
f=dict(re.findall(r'(\w+)=([^\s]+)',p.stdout))
if f.get('JobId')!=JOB or f.get('Comment')!=SHA or f.get('UserId')!='sbq(1024)':raise ValueError('wrong cancellation target')
with (root/'race_cancel_attempt.json').open('x') as h:json.dump({'job_id':JOB,'request_sha256':SHA},h)
q=subprocess.run(['scancel','--ctld',JOB],capture_output=True,text=True,timeout=15)
record={'job_id':JOB,'request_sha256':SHA,'exit_code':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reason':'user-authorized redundant replica only'}
with log.open('x') as h:json.dump(record,h,indent=2)
print(json.dumps(record))
'''
    constants = "ROOT=" + repr(binding["root"]) + "\nJOB=" + repr(binding["job_id"]) + "\nSHA=" + repr(binding["sha256"]) + "\n"
    receipt = remote(backend, constants + code)
    write_json_exclusive(OUT / ("cancel_" + backend + ".json"), receipt)
    return receipt


def grant(binding, peer):
    if peer["state"] not in TERMINAL:
        raise ValueError("peer still active;refusing model permit")
    permit = {"action": "RUN_EXACT_GPU_BATCH", "winner_job_id": binding["job_id"],
        "request_sha256": binding["sha256"], "peer_job_id": peer["job_id"], "peer_request_sha256": peer["request_sha256"],
        "peer_terminal_state": peer["state"], "issued_at": datetime.now(timezone.utc).isoformat()}
    local = OUT / "winner_permit_prepared.json"
    write_json_exclusive(local, permit)
    digest = sha256_file(local)
    code = '''import hashlib,json,os,sys
from pathlib import Path
root=Path(ROOT);data=sys.stdin.buffer.read(16384)
if hashlib.sha256(data).hexdigest()!=SHA:raise ValueError('permit bytes changed')
target=root/'winner_permit.json';temp=root/'winner_permit.prepared.json'
if target.exists():
 if target.read_bytes()!=data:raise ValueError('different permit exists')
else:
 with temp.open('xb') as h:h.write(data);h.flush();os.fsync(h.fileno())
 os.link(temp,target)
print(json.dumps({'status':'PERMIT_PUBLISHED','sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
'''
    receipt = remote("buct2_gpu", "ROOT=" + repr(binding["root"]) + "\nSHA=" + repr(digest) + "\n" + code, local.read_bytes())
    write_json_exclusive(OUT / "permit_publication.json", receipt)
    return digest


def finish(winner, snapshots, bound):
    loser = next(name for name in bound if name != winner)
    if snapshots[loser]["state"] not in TERMINAL:
        cancel(loser, bound[loser])
    for _ in range(12):
        peer = observe(loser, bound[loser])
        if peer["state"] in TERMINAL:
            break
        time.sleep(2)
    else:
        raise TimeoutError("cancellation not terminal;no second model permit issued")
    if winner == "buct2_gpu" and not eligible(winner, observe(winner, bound[winner])):
        raise RuntimeError("BUCT2 no longer ready;no model permit issued")
    permit = grant(bound[winner], peer) if winner == "buct2_gpu" else None
    record = {"status": "WINNER_SELECTED", "winner_backend": winner, "winner": bound[winner],
        "loser_backend": loser, "loser_terminal_evidence": peer, "selection_evidence": snapshots,
        "winner_permit_sha256": permit, "VASP_submitted": False, "training": False}
    write_json_exclusive(OUT / "winner_selection.json", record)
    print("WINNER_SELECTED", winner, bound[winner]["job_id"], flush=True)


def run(watch):
    bound = bindings()
    if watch:
        write_json_exclusive(OUT / "coordinator_lock.json", {"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(),
            "scope": bound, "max_seconds": 604800, "offline_behavior": "BUCT2 exits without model after120s;MZ73 unchanged"})
    deadline = time.monotonic() + (604800 if watch else 60)
    observations = OUT / "arbitration_observations"
    observations.mkdir(exist_ok=True)
    previous = None
    while time.monotonic() < deadline:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pairs = list(pool.map(lambda n: (n, observe(n, bound[n])), bound))
        snapshots = dict(pairs)
        label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        write_json_exclusive(observations / (label + ".json"), snapshots)
        winner = choose(snapshots)
        if winner:
            finish(winner, snapshots, bound)
            return
        current = tuple((n, s["state"], bool(s.get("ready")), bool(s.get("model_device"))) for n, s in snapshots.items())
        if current != previous:
            print("WAITING", current, flush=True)
            previous = current
        if all(s["state"] in TERMINAL for s in snapshots.values()):
            raise RuntimeError("both replicas terminal without eligible GPU producer;no retries authorized")
        if not watch:
            return
        time.sleep(30)
    raise TimeoutError("seven-day arbitration budget exhausted;no model permit or retry granted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    try:
        run(args.watch)
    except BaseException as exc:
        write_json_exclusive(OUT / "coordinator_exit.json", {"exit_code": 1,
            "error": type(exc).__name__ + ": " + str(exc), "VASP_submitted": False, "no_auto_retry": True})
        raise
