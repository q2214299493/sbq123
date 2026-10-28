"""Resume read-only collection by independent cases;preserve prior failures."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import zlib

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .collect import BASE, SUBMITTED, reader

OUTPUT = BASE / "paired_cost_comparison_20261028_v4"


def decode(raw):
    return [json.loads(line) if line.startswith(b"{") else json.loads(zlib.decompress(base64.b64decode(line, validate=True)))
        for line in raw.splitlines()]


def save_case(record, output=OUTPUT):
    folder = output / "snapshots" / record["row"]["name"] / record["row"]["model"]
    folder.mkdir(parents=True)
    for name, item in record["files"].items():
        with (folder / name).open("xb") as target:
            target.write(base64.b64decode(item["base64"], validate=True))
    write_json_exclusive(folder / "extracted.json", record)


def one_case(row, output=OUTPUT, timeout=50, chunked=False):
    label = row["name"] + "_" + row["model"]
    program = reader([row])
    changes = {"with p.open('rb') as f:data=f.read(before.st_size)": "print('before_read',file=sys.stderr,flush=True)\n with p.open('rb') as f:data=f.read(before.st_size)\n print('after_read',file=sys.stderr,flush=True)",
        "frames=raw_frames(Snapshot(data[:cut]),row['atom_count']) if cut else []": "print('before_parse',file=sys.stderr,flush=True)\n frames=raw_frames(Snapshot(data[:cut]),row['atom_count']) if cut else []\n print('after_parse',file=sys.stderr,flush=True)"}
    for old, new in changes.items():
        if program.count(old) != 1:
            raise ValueError("read-only phase instrumentation changed")
        program = program.replace(old, new)
    if chunked:
        old = "with p.open('rb') as f:data=f.read(before.st_size)"
        new = "with p.open('rb',buffering=0) as f:\n  chunks=[];remaining=before.st_size\n  while remaining:\n   chunk=f.read(min(1024**2,remaining))\n   if not chunk:break\n   chunks.append(chunk);remaining-=len(chunk)\n   print('read_bytes',before.st_size-remaining,file=sys.stderr,flush=True)\n  data=b''.join(chunks)"
        if program.count(old) != 1:
            raise ValueError("chunked read instrumentation changed")
        program = program.replace(old, new)
    write_json_exclusive(output / (label + "_reader.json"), {"program": program, "remote_writes": False})
    encoded = base64.b64encode(zlib.compress(program.encode())).decode()
    args = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ControlMaster=no", "-o", "ControlPath=none", "sunboquan-codex",
        'python3 -c "exec(__import__(\'zlib\').decompress(__import__(\'base64\').b64decode(\'' + encoded + '\')))"']
    with (output / (label + ".raw")).open("xb") as stdout, (output / (label + ".stderr")).open("xb") as stderr:
        try:
            result = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
            transport = {"returncode": result.returncode}
        except subprocess.TimeoutExpired:
            transport = {"returncode": None, "timeout_seconds": timeout}
    transport["checked_at"] = datetime.now(timezone.utc).isoformat()
    write_json_exclusive(output / (label + "_transport.json"), transport)
    if transport["returncode"] != 0:
        return {"case": label, "status": "READ_FAILED", "transport": transport}
    payload = decode((output / (label + ".raw")).read_bytes())
    if len(payload) != 2 or payload[1]["row"]["job_id"] != row["job_id"]:
        raise ValueError("single-case identity incomplete")
    save_case(payload[1], output)
    return {"case": label, "status": "COLLECTED", "job_id": row["job_id"], "state": payload[1]["state"],
        "frames": len(payload[1]["frames"]), "checked_at": transport["checked_at"]}


def collect():
    if OUTPUT.exists():
        raise FileExistsError("preserve existing per-case collection")
    OUTPUT.mkdir()
    prior = BASE / "paired_cost_comparison_20261028_v3/raw.jsonl"
    payload = decode(prior.read_bytes())
    if len(payload) != 2 or payload[1]["row"]["job_id"] != "9925060":
        raise ValueError("only the completed authentic first-case record may be reused")
    save_case(payload[1])
    source = load_json_object(SUBMITTED / "submission_summary.json")
    rows = [{**{k: r[k] for k in ["name", "model", "job_id", "remote_dir"]}, "atom_count": 50 if r["name"] == "10_A" else 51}
        for r in source["records"] if r["job_id"] != "9925060"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(one_case, rows))
    result = {"status": "COMPLETE" if all(r["status"] == "COLLECTED" for r in records) else "PARTIAL",
        "reused_closed_case": "9925060", "records": records,
        "source_files": source_file_manifest([Path(__file__), Path(__file__).with_name("collect.py"), prior] + sorted(OUTPUT.glob("*.raw")) + sorted(OUTPUT.glob("*_transport.json")))}
    write_json_exclusive(OUTPUT / "collection.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    collect()
