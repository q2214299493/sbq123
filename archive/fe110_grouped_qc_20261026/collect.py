"""Recover exactly the authorized14 closed jobs, without remote writes."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from archive.fe110_reico_label_qc_20261023.collect import identity_path
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.adsorption.collect_completed_batch import FILES, REMOTE_PATTERN, ssh_options
from scripts.artifact_io import (
    load_json_object, sha256_file, sha256_text, source_file_manifest,
    source_file_manifest_valid, write_json_atomic,
)
from scripts.neb_agent.submission import submission_status
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
INPUT = BASE / "grouped_inputs_20261025_v1"
SOURCE = BASE / "grouped_submission_20261025_v1/submission_summary.json"
OUTPUT = BASE / "grouped_qc_20261026_v2"
HOST = "sunboquan-codex"


def scope():
    source = load_json_object(SOURCE)
    if not source_file_manifest_valid(source):
        raise ValueError("submission binding changed")
    rows = source["records"]
    if len(rows) != 14 or len({r["job_id"] for r in rows}) != 14:
        raise ValueError("exact14 distinct native receipts required")
    for row in rows:
        directory = INPUT / row["role"] / row["sample_id"]
        live = submission_status(directory)
        if live["status"] != "SUBMITTED" or live["job_id"] != row["job_id"] or live["remote_dir"] != row["remote_dir"]:
            raise ValueError("native receipt changed")
        if not REMOTE_PATTERN.fullmatch(row["remote_dir"]):
            raise ValueError("unsafe remote source")
    return rows


def snapshot(rows):
    path = OUTPUT / "scheduler_snapshot.json"
    if path.exists():
        result = load_json_object(path)
        if result["requested"] != rows:
            raise ValueError("changed scheduler scope")
    else:
        argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", HOST,
                "bjobs", "-a", *[r["job_id"] for r in rows]]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=40, check=False)
        result = {"requested": rows, "checked_at": datetime.now(timezone.utc).isoformat(),
                  "query": {"argv": argv, "returncode": p.returncode, "stdout": p.stdout,
                            "stderr": p.stderr, "stdout_sha256": sha256_text(p.stdout)}}
        save_once(path, result)
    query = result["query"]
    evidence = []
    for row in rows:
        item = {"schema_version": 1, "document_kind": "scheduler_job_evidence",
                "stage": "vasp_force_label" if row["role"] == "single_points" else "adsorption_relaxation",
                "scheduler": "LSF", "server_alias": HOST, "job_id": row["job_id"],
                "status": _parse_lsf_bjobs(query["stdout"], row["job_id"]),
                "checked_at": result["checked_at"], "source_command": " ".join(query["argv"]), "query": query}
        validate_stored_lsf_evidence(item, required_status="DONE")
        evidence.append(item)
    save_once(OUTPUT / "scheduler_evidence.json", {"jobs": evidence})


def metadata(rows, identity):
    path = OUTPUT / "remote_metadata.json"
    if path.exists():
        saved = load_json_object(path)
        if saved["requested"] != rows:
            raise ValueError("metadata scope changed")
        return saved["records"]
    script = """import os,json,hashlib,datetime
records=[]
for row in ROWS:
 d=os.path.expanduser(row['remote_dir']); item={'sample_id':row['sample_id'],'job_id':row['job_id'],'directory':d,'files':{}}
 names=NAMES+(['XDATCAR'] if row['role']=='optimizations' else [])
 for name in names:
  p=os.path.join(d,name); before=os.stat(p); h=hashlib.sha256()
  with open(p,'rb') as f:
   for block in iter(lambda:f.read(1048576),b''):h.update(block)
  after=os.stat(p)
  if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('source changed '+p)
  item['files'][name]={'sha256':h.hexdigest(),'byte_size':before.st_size,'modified_at':datetime.datetime.fromtimestamp(before.st_mtime,datetime.timezone.utc).isoformat()}
 records.append(item)
print(json.dumps({'records':records}))
""".replace("ROWS", repr(rows)).replace("NAMES", repr(list(FILES) + ["POTCAR", "script.lsf"]))
    encoded = base64.b64encode(script.encode()).decode("ascii")
    command = '/usr/bin/python3 -c "exec(__import__(\'base64\').b64decode(\'' + encoded + '\'))"'
    argv = ["ssh", "-n", *ssh_options(identity), HOST, command]
    try:
        p = subprocess.run(argv, capture_output=True, timeout=55, check=False)
    except subprocess.TimeoutExpired:
        save_once(OUTPUT / "metadata_timeout.json", {"timeout_seconds": 55, "reader_sha256": sha256_text(script)})
        raise
    if p.returncode:
        save_once(OUTPUT / "metadata_failure.json", {"returncode": p.returncode, "stderr": p.stderr.decode(errors="replace")})
        raise RuntimeError("metadata failed")
    import json
    result = json.loads(p.stdout)
    save_once(path, {"requested": rows, "records": result["records"],
                     "reader": script, "reader_sha256": sha256_text(script), "argv": argv})
    return result["records"]


def collect_one(row, remote, identity):
    directory = OUTPUT / "collection" / row["sample_id"]
    directory.mkdir(parents=True, exist_ok=True)
    files = list(FILES) + (["XDATCAR"] if row["role"] == "optimizations" else [])
    expected = {"name": row["sample_id"], "job_id": row["job_id"], "remote_dir": row["remote_dir"],
                "workdir": str(INPUT / row["role"] / row["sample_id"]), "potcar_sha256": row["potcar_sha256"]}
    missing = []
    for name in files:
        path = directory / name
        if path.exists():
            if sha256_file(path) != remote["files"][name]["sha256"]:
                raise ValueError("preserve changed partial file " + str(path))
        else:
            missing.append(name)
    if missing:
        argv = ["scp", "-O", "-C", *ssh_options(identity),
                *[f"{HOST}:{row['remote_dir']}/{name}" for name in missing], str(directory)]
        p = subprocess.run(argv, capture_output=True, timeout=180, check=False)
        if p.returncode:
            raise RuntimeError(p.stderr.decode(errors="replace")[:800])
    for name in files:
        if sha256_file(directory / name) != remote["files"][name]["sha256"]:
            raise ValueError("remote/local hash mismatch " + name)
    original = Path(expected["workdir"])
    for name in ("INCAR", "POSCAR", "KPOINTS", "script.lsf"):
        actual = sha256_file(directory / name) if name != "script.lsf" else remote["files"][name]["sha256"]
        if actual != sha256_file(original / name):
            raise ValueError("submitted input changed " + name)
    if remote["files"]["POTCAR"]["sha256"] != row["potcar_sha256"]:
        raise ValueError("target POTCAR changed")
    receipt = {"job_id": row["job_id"], "name": row["sample_id"], "submission": expected,
               "local_directory": str(directory.resolve()), "remote": remote,
               "accepted": False, "license_boundary": "POTCAR remains remote;metadata only"}
    save_once(directory / "collection.json", receipt)
    return {"sample_id": row["sample_id"], "job_id": row["job_id"],
            "receipt_sha256": sha256_file(directory / "collection.json")}


def run(smoke=False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = scope()
    save_once(OUTPUT / "collection_binding.json", {"source_files": source_file_manifest([
        SOURCE, Path(__file__), INPUT / "verification.json"]), "requested": rows})
    snapshot(rows)
    identity = identity_path()
    info = {r["sample_id"]: r for r in metadata(rows, identity)}
    requested = rows[:1] if smoke else rows
    collected, failures = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_one, row, info[row["sample_id"]], identity): row for row in requested}
        for future in as_completed(futures):
            row = futures[future]
            try:
                collected.append(future.result())
                print("COLLECTED " + row["sample_id"], flush=True)
            except Exception as exc:
                failures.append({"sample_id": row["sample_id"], "error": str(exc)})
                print("BLOCKED " + row["sample_id"] + " " + str(exc), flush=True)
            write_json_atomic(OUTPUT / "collection_progress.json", {"collected": collected, "failures": failures})
    save_once(OUTPUT / ("collection_smoke.json" if smoke else "collection_summary.json"),
              {"collected": sorted(collected, key=lambda r: r["sample_id"]), "failures": failures,
               "remote_writes": False, "new_calculations_or_training": False})
    if failures:
        raise RuntimeError("preserved collection failures; inspect before retry")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    run(parser.parse_args().smoke)
