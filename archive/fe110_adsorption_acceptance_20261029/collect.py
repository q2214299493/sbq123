"""Collect existing C2 outputs and scheduler evidence without changing jobs."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from scripts.adsorption.collect_completed_batch import FILES, REMOTE_PATTERN, ssh_options
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/adsorption_acceptance_20261029_v1"
DB = ROOT / "data/project_registry.sqlite3"
BOOK = ROOT / "outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx"
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
IDENTITY = Path("C:/Users/86177/.ssh/id_ed25519_fe_agent")


def sources():
    original = load_json_object(BASE / "dedup_final_review_20261021_v1/request.json")
    rows = [dict(x["record"]) for x in original["sources"] if x["record"]["cohort"] == "original15"]
    pairs = load_json_object(BASE / "adsorption_control_paired_vasp3_20261020_v1/submission_summary.json")
    with open_registry(DB) as connection:
        connection.execute("PRAGMA query_only=ON")
        for row in rows:
            row["calculation_id"] = "fe110_c2_06_10_adsorption_20261013_" + row["name"]
        for record in [*pairs["records"], {"job_id": "9926807", "name": "10_A", "arm": "finetune"}]:
            job = connection.execute("SELECT * FROM jobs WHERE scheduler_job_id=?", (record["job_id"],)).fetchone()
            files = connection.execute("SELECT * FROM files WHERE calculation_id=?", (job["calculation_id"],)).fetchall()
            incars = [f for f in files if f["filename"] == "INCAR" and f["local_path"]]
            potcars = [f for f in files if f["filename"] == "POTCAR" and f["sha256"]]
            if len(incars) != 1 or len(potcars) != 1:
                raise ValueError("ambiguous input binding: " + record["job_id"])
            name = "paired_" + record["name"] + "_" + record["arm"] if record["job_id"] != "9926807" else "ft512_10_A"
            rows.append({"name": name, "job_id": record["job_id"], "remote_dir": job["remote_directory"],
                         "workdir": str(Path(incars[0]["local_path"]).parent), "potcar_sha256": potcars[0]["sha256"],
                         "calculation_id": job["calculation_id"], "species_id": record["name"][:2],
                         "connectivity": {"06": "[C]O[CH]", "09": "[C]O[CH2]", "10": "[CH][CH2]"}[record["name"][:2]],
                         "formula": "C2H3" if record["name"].startswith("10") else "C2HO" if record["name"].startswith("06") else "C2H2O"})
    if len(rows) != 22 or len({r["job_id"] for r in rows}) != 22:
        raise ValueError("expected the exact 15 original, six paired and one FT calculation")
    return rows


def initialize():
    if OUT.exists():
        raise FileExistsError(OUT)
    rows = sources()
    OUT.mkdir(parents=True)
    shutil.copyfile(BOOK, OUT / "before.xlsx")
    write_json_exclusive(OUT / "sources.json", {"records": rows, "workbook_sha256_before": sha256_file(BOOK),
        "scope": "Existing C2 completed-state review; no job writes, reference calculations or method changes.",
        "created_at": datetime.now(timezone.utc).isoformat()})


def scheduler():
    rows = load_json_object(OUT / "sources.json")["records"]
    target = OUT / "scheduler"
    target.mkdir(exist_ok=False)
    ids = [r["job_id"] for r in rows]
    observed = []
    for program, options in (("bjobs", ["-a", "-w"]), ("bacct", ["-l", "-w"])):
        remote = " ".join([program, *options, *ids])
        run = subprocess.run(["ssh", *ssh_options(IDENTITY), "sunboquan-codex", remote], capture_output=True, timeout=60)
        for stream in ("stdout", "stderr"):
            path = target / (program + "." + stream + ".txt")
            path.write_bytes(getattr(run, stream))
        observed.append({"program": program, "command": remote, "exit_code": run.returncode,
            "stdout_sha256": sha256_file(target / (program + ".stdout.txt")),
            "stderr_sha256": sha256_file(target / (program + ".stderr.txt")),
            "stdout_bytes": len(run.stdout), "stderr_bytes": len(run.stderr)})
    write_json_exclusive(target / "receipt.json", {"checked_at": datetime.now(timezone.utc).isoformat(),
        "server_alias": "sunboquan-codex", "scheduler": "LSF", "commands": observed})
    for row in observed:
        print(row["program"], "exit", row["exit_code"], "stdout_bytes", row["stdout_bytes"], "stderr_bytes", row["stderr_bytes"])


def collect(only):
    rows = load_json_object(OUT / "sources.json")["records"]
    if only:
        selected = set(only.split(","))
        rows = [r for r in rows if r["job_id"] in selected]
        if {r["job_id"] for r in rows} != selected:
            raise ValueError("unknown exact collection job ID")
    if not rows:
        raise ValueError("empty exact collection scope")
    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_snapshot, r): r for r in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
                print("COLLECTED", row["name"], result["remote"]["files"]["OUTCAR"]["byte_size"], flush=True)
            except Exception as exc:
                errors.append({"name": row["name"], "error": str(exc)})
                print("BLOCKED", row["name"], str(exc)[:400], flush=True)
    if errors:
        write_json_exclusive(OUT / ("collection_failures_" + datetime.now(timezone.utc).strftime("%H%M%S") + ".json"), {"errors": errors})
        raise SystemExit(1)


def snapshot_metadata(row, directory):
    metadata = directory / "remote_metadata.json"
    if metadata.exists():
        remote = load_json_object(metadata)
    else:
        script = '''import os,json,hashlib,datetime
d=os.path.expanduser(DIRECTORY)
out={'directory':d,'files':{}}
for name in NAMES:
 p=os.path.join(d,name); before=os.stat(p); h=hashlib.sha256()
 with open(p,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 after=os.stat(p)
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('source changed')
 out['files'][name]={'sha256':h.hexdigest(),'byte_size':before.st_size,'modified_at':datetime.datetime.fromtimestamp(before.st_mtime,datetime.timezone.utc).isoformat()}
print(json.dumps(out))
'''.replace("DIRECTORY", repr(row["remote_dir"])).replace("NAMES", repr(FILES + ("POTCAR",)))
        run = subprocess.run(["ssh", *ssh_options(IDENTITY), "sunboquan-codex", "python3 -"],
                             input=script.encode(), capture_output=True, timeout=180)
        (directory / "metadata.stdout.txt").write_bytes(run.stdout)
        (directory / "metadata.stderr.txt").write_bytes(run.stderr)
        if run.returncode:
            raise ValueError("remote Python hash snapshot failed: " + run.stderr.decode(errors="replace")[:600])
        remote = json.loads(run.stdout)
        write_json_exclusive(metadata, remote)
    return remote


def verify_collected(directory, remote):
    for name in FILES:
        if sha256_file(directory / name) != remote["files"][name]["sha256"]:
            raise ValueError("preserve changed collected evidence: " + name)


def collect_snapshot(row):
    directory = OUT / "sources" / row["name"]
    receipt = directory / "collection.json"
    if receipt.exists():
        previous = load_json_object(receipt)
        if previous["job_id"] != row["job_id"]:
            raise ValueError("collection belongs to another job")
        verify_collected(directory, previous["remote"])
        return previous
    if not REMOTE_PATTERN.fullmatch(row["remote_dir"]) or ".." in row["remote_dir"].split("/"):
        raise ValueError("unsafe remote path")
    directory.mkdir(parents=True, exist_ok=True)
    remote = snapshot_metadata(row, directory)
    if remote["files"]["POTCAR"]["sha256"] != row["potcar_sha256"]:
        raise ValueError("POTCAR bundle changed")
    missing = []
    for name in FILES:
        path = directory / name
        if not path.exists():
            missing.append(name)
        elif sha256_file(path) != remote["files"][name]["sha256"]:
            raise ValueError("preserve mismatched partial evidence: " + name)
    if missing:
        run = subprocess.run(["scp", "-O", "-C", *ssh_options(IDENTITY),
            *[f"sunboquan-codex:{row['remote_dir']}/{name}" for name in missing], str(directory)],
            capture_output=True, timeout=240)
        if run.returncode:
            raise ValueError("source copy failed: " + run.stderr.decode(errors="replace")[:600])
    verify_collected(directory, remote)
    for name in ("INCAR", "POSCAR", "KPOINTS"):
        if sha256_file(directory / name) != sha256_file(Path(row["workdir"]) / name):
            raise ValueError("submitted input changed: " + name)
    result = {"job_id": row["job_id"], "name": row["name"], "submission": row,
        "local_directory": str(directory.resolve()), "remote": remote,
        "collected_at": datetime.now(timezone.utc).isoformat(), "accepted": False,
        "license_boundary": "POTCAR retained remotely; only SHA256 metadata collected"}
    write_json_exclusive(receipt, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["initialize", "scheduler", "collect"])
    parser.add_argument("--only")
    args = parser.parse_args()
    if args.phase == "initialize":
        initialize()
    elif args.phase == "scheduler":
        scheduler()
    else:
        collect(args.only)
