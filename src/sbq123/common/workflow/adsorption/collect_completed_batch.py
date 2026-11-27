"""Read-only remote collection of submitted adsorption outputs; no acceptance or writes to jobs."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.execution_backends import load_execution_backends

FILES = ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR", "KPOINTS")
REMOTE_PATTERN = re.compile(r"^~/sbq/[A-Za-z0-9_./-]+$")


def ssh_options(identity: Path) -> list[str]:
    return ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o",
            "IdentitiesOnly=yes", "-i", str(identity)]


def remote_metadata(server: str, identity: Path, directory: str) -> dict:
    if not REMOTE_PATTERN.fullmatch(directory) or ".." in directory.split("/"):
        raise ValueError("unsafe remote calculation path")
    script = """
import os, json, subprocess, datetime
d = os.path.expanduser(DIRECTORY)
out = {'directory': d, 'files': {}}
for name in NAMES:
 p = os.path.join(d, name)
 st = os.stat(p)
 print('READING ' + name + ' ' + str(st.st_size), flush=True)
 digest = subprocess.check_output(['sha256sum', p]).decode('ascii').split()[0]
 out['files'][name] = {'sha256': digest, 'byte_size': st.st_size,
  'modified_at': datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat()}
print(json.dumps(out))
""".replace("DIRECTORY", repr(directory)).replace("NAMES", repr(FILES + ("POTCAR",)))
    try:
        run = subprocess.run(["ssh", *ssh_options(identity), server, "python3 -"],
                             input=script.encode(), capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        progress = (exc.stdout or b"").decode("utf-8", "replace")[-1000:]
        raise RuntimeError(f"remote metadata timeout; last progress: {progress}") from exc
    if run.returncode:
        raise RuntimeError(f"remote metadata exit {run.returncode}: {run.stderr.decode('utf-8', 'replace')[:800]}")
    documents = [line for line in run.stdout.decode("utf-8", "replace").splitlines()
                 if line.startswith('{"directory":')]
    if len(documents) != 1:
        raise ValueError("missing or ambiguous remote metadata response")
    return json.loads(documents[0])


def collect_one(row: dict, server: str, identity: Path, output: Path) -> dict:
    directory = output / row["name"]
    receipt = directory / "collection.json"
    if receipt.exists():
        previous = load_json_object(receipt)
        if previous["job_id"] != row["job_id"]:
            raise ValueError("collection receipt belongs to another job")
        for name in FILES:
            if sha256_file(directory / name) != previous["remote"]["files"][name]["sha256"]:
                raise ValueError(f"collected evidence changed: {name}")
        return previous
    directory.mkdir(parents=True, exist_ok=True)
    remote = remote_metadata(server, identity, row["remote_dir"])
    missing = []
    for name in FILES:
        path = directory / name
        if path.exists():
            if sha256_file(path) != remote["files"][name]["sha256"]:
                raise ValueError(f"preserve partial/mismatched file; do not overwrite: {path}")
        else:
            missing.append(name)
    if missing:
        command = ["scp", "-O", "-C", *ssh_options(identity),
                   *[f"{server}:{row['remote_dir']}/{name}" for name in missing], str(directory)]
        run = subprocess.run(command, capture_output=True, timeout=180, check=False)
        if run.returncode:
            raise RuntimeError(f"scp exit {run.returncode}: {run.stderr.decode('utf-8', 'replace')[:800]}")
    for name in FILES:
        if sha256_file(directory / name) != remote["files"][name]["sha256"]:
            raise ValueError(f"remote/local hash mismatch: {name}")
    if remote["files"]["POTCAR"]["sha256"] != row["potcar_sha256"]:
        raise ValueError("POTCAR differs from the submitted bundle")
    for name in ("INCAR", "POSCAR", "KPOINTS"):
        if sha256_file(directory / name) != sha256_file(Path(row["workdir"]) / name):
            raise ValueError(f"remote input differs from reviewed submitted input: {name}")
    result = {"job_id": row["job_id"], "name": row["name"], "submission": row,
              "local_directory": str(directory.resolve()), "remote": remote,
              "collected_at": datetime.now(timezone.utc).isoformat(),
              "accepted": False, "license_boundary": "POTCAR content retained remotely; hash only"}
    write_json_atomic(receipt, result, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--only", help="one job ID for small-sample collection")
    args = parser.parse_args()
    server = load_execution_backends().vasp.server_alias
    rows = [r for path in args.submission for r in load_json_object(path)["records"]]
    if args.only:
        rows = [r for r in rows if r["job_id"] == args.only]
    if not rows or len({r["job_id"] for r in rows}) != len(rows):
        raise ValueError("empty or duplicate submitted job set")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", r["name"]) for r in rows):
        raise ValueError("unsafe local candidate name")
    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_one, row, server, args.identity, args.output): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
                print(f"COLLECTED {result['job_id']} {result['name']}", flush=True)
            except Exception as exc:
                errors.append({"job_id": row["job_id"], "error": str(exc)})
                print(f"BLOCKED {row['job_id']} {exc}", flush=True)
    if errors:
        write_json_atomic(args.output / "collection_failures.json", errors, ensure_ascii=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
