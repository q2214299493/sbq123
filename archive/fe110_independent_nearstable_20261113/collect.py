"""Read saved VASP files over SSH; no remote writes, jobs, inference or training."""
from __future__ import annotations

import base64
import subprocess
import zlib
from pathlib import Path

from archive.fe110_combined_force_package_20261023.prepare import save_once
from scripts.artifact_io import load_json_object as load
from scripts.artifact_io import sha256_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUTPUT = BASE / "independent_nearstable_inventory_20261113_v1"

REMOTE = r'''
import base64,hashlib,json,os,socket,zlib
from pathlib import Path
from datetime import datetime,timezone
specifications=SOURCE_SPECIFICATIONS
allowed=(Path.home()/"sbq/Fe110").resolve()
records=[]
for spec in specifications:
    directory=Path(spec["remote_directory"]).expanduser().resolve()
    if directory != allowed and allowed not in directory.parents:
        raise ValueError("source directory outside reviewed Fe110 root")
    record={"job_id":spec["job_id"],"directory":str(directory),"files":{}}
    for name in sorted(set(spec["copy_files"]+["OUTCAR","POTCAR"])):
        path=directory/name
        if not path.is_file():
            record["files"][name]={"exists":False}
            continue
        before=path.stat()
        if before.st_size>64*1024**2:
            raise ValueError("bounded reader file limit exceeded")
        content=path.read_bytes()
        after=path.stat()
        info={"exists":True,"bytes":len(content),"sha256":hashlib.sha256(content).hexdigest(),
              "stable_during_read":(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)}
        if name in spec["copy_files"]:
            info["zlib_base64"]=base64.b64encode(zlib.compress(content)).decode()
        record["files"][name]=info
    records.append(record)
print(json.dumps({"hostname":socket.gethostname(),"uid":os.getuid(),
                  "observed_at_UTC":datetime.now(timezone.utc).isoformat(),"sources":records}))
'''


def save_response(response, sources):
    by_job = {r["job_id"]: r for r in sources}
    for row in response["sources"]:
        cached = by_job[row["job_id"]].get("cached_OUTCAR")
        row["cached_OUTCAR_hash_matches_remote"] = (sha256_file(Path(cached)) == row["files"]["OUTCAR"].get("sha256")) if cached else None
        for name, entry in row["files"].items():
            if "zlib_base64" in entry:
                data = zlib.decompress(base64.b64decode(entry.pop("zlib_base64")))
                if sha256_bytes(data) != entry["sha256"] or not entry["stable_during_read"]:
                    raise ValueError("source changed during read")
                target = OUTPUT / "source_snapshots" / row["job_id"] / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise FileExistsError(target)
                target.write_bytes(data)
                entry["saved_path"] = target.relative_to(OUTPUT).as_posix()
    response.update(remote_writes=False, new_jobs=False, POTCAR_content_copied=False)
    save_once(OUTPUT / "source_collection.json", response)
    return response


def run():
    if (OUTPUT / "source_collection.json").exists():
        result = load(OUTPUT / "source_collection.json")
        for row in result["sources"]:
            for name, entry in row["files"].items():
                if entry.get("saved_path") and sha256_file(OUTPUT / entry["saved_path"]) != entry["sha256"]:
                    raise ValueError("saved source snapshot changed")
        return result
    source_index = load(OUTPUT / "registry_source_evidence.json")["records"]
    remote = {r["scheduler_job_id"]: r["remote_directory"] for r in source_index}
    sources = []
    for name in ("outputs/adsorption_acceptance_20261029_v1/analysis.json",
                 "outputs/fe110_c2_registration_20261102_v1/analysis.json"):
        for row in load(ROOT / name)["records"]:
            if row["formula"] == "C2H3":
                sources.append({"job_id": row["job_id"], "remote_directory": remote[row["job_id"]],
                                "copy_files": ["XDATCAR"], "cached_OUTCAR": str(Path(row["directory"]) / "OUTCAR")})
    for job in ("9925062", "9925065"):
        sources.append({"job_id": job, "remote_directory": remote[job],
                        "copy_files": ["OUTCAR", "XDATCAR", "OSZICAR", "POSCAR", "CONTCAR", "INCAR", "KPOINTS"]})
    if len(sources) != 8 or len({r["job_id"] for r in sources}) != 8:
        raise ValueError("unexpected bounded source membership")
    program = REMOTE.replace("SOURCE_SPECIFICATIONS", repr(sources))
    save_once(OUTPUT / "source_collection_request.json", {
        "sources": sources, "remote_program_sha256": sha256_bytes(program.encode()),
        "remote_writes": False, "new_jobs": False, "POTCAR_content_copied": False})
    with (OUTPUT / "source_collection.stdout").open("xb") as stdout, (OUTPUT / "source_collection.stderr").open("xb") as stderr:
        completed = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                                    "sunboquan-codex", "python3", "-"], input=program.encode(),
                                   stdout=stdout, stderr=stderr, timeout=55, check=False)
    save_once(OUTPUT / "source_collection_transport.json", {"exit_code": completed.returncode})
    if completed.returncode:
        raise RuntimeError("read-only SSH collection failed; retain stdout/stderr; no retry")
    if (OUTPUT / "source_collection.stdout").stat().st_size > 12 * 1024**2:
        raise ValueError("bounded source response limit exceeded")
    response = load(OUTPUT / "source_collection.stdout")
    return save_response(response, sources)


if __name__ == "__main__":
    result = run()
    print({"sources": len(result["sources"]), "remote_writes": False,
           "cached_OUTCAR_matches": {r["job_id"]: r["cached_OUTCAR_hash_matches_remote"] for r in result["sources"]}})
