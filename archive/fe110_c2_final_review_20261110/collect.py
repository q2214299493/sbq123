"""Collect the exact ten submitted adsorption sources; no remote job writes."""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import tarfile

from archive.fe110_c2_supplement_vasp_20261107.dft import SUBMISSION
from archive.fe110_scratch512_20261028 import submit_c2_dft as transport
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_c2_site_supplement_20261106/final_review_20261110_v1"
REMOTE = "sbq/Fe110/adsorption/c2_site_supplement_20261107_v1"


def main():
    if OUT.exists():
        raise SystemExit("Collection already exists; inspect receipts instead of overwriting.")
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    jobs = [{"name": row["name"], "job_id": load_json_object(Path(row["directory"]) / "submission_record.json")["job_id"],
             "remote_dir": row["remote_dir"], "source_input_dir": row["directory"]} for row in ready["jobs"]]
    OUT.mkdir()
    transport.OUTPUT = OUT
    program = r'''import json,hashlib,subprocess
from pathlib import Path
root=Path.home()/REMOTE
def command(argv):
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=25)
  return {'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except subprocess.TimeoutExpired:
  return {'argv':argv,'timeout':True,'stdout':'','stderr':'timeout'}
files=[]
for job in JOBS:
 folder=root/job['name']
 for p in sorted(folder.iterdir()):
  if not p.is_file() or p.is_symlink():continue
  if p.name not in {'POSCAR','CONTCAR','OUTCAR','OSZICAR','XDATCAR','INCAR','KPOINTS','POTCAR.spec','script.lsf'} and not p.name.endswith(('.out','.err','.log')):continue
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
  files.append({'relative_path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
ids=[j['job_id'] for j in JOBS]
print(json.dumps({'root':str(root),'files':files,'bjobs':command(['bjobs','-a','-w']+ids),
                  'bhist':command(['bhist','-l']+ids),'bacct':command(['bacct','-l']+ids)}))
'''.replace("REMOTE", repr(REMOTE)).replace("JOBS", repr(jobs))
    inventory, raw = transport.ssh_read(program, "remote_inventory_scheduler")
    write_json_exclusive(OUT / "collection_manifest.json", {"checked_at": raw["checked_at"], "jobs": jobs, **inventory})
    # Stream only inventoried outputs. No licensed POTCAR or large restart files.
    names = [row["relative_path"] for row in inventory["files"]]
    if not names or any(len(Path(name).parts) != 2 or Path(name).parts[0] not in {j['name'] for j in jobs} for name in names):
        raise ValueError("Unexpected remote file scope.")
    archive = OUT / "sources.tar.gz"
    with archive.open("xb") as target:
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex",
                                 "tar -czf - -C " + inventory["root"] + " -- " + " ".join(names)],
                                stdout=target, stderr=subprocess.PIPE, timeout=240)
    if result.returncode:
        raise ValueError("Collection failed: " + result.stderr.decode(errors="replace")[:1000])
    destination = OUT / "sources"
    destination.mkdir()
    expected = {row["relative_path"]: row for row in inventory["files"]}
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if member.name not in expected or not member.isfile():
                raise ValueError("Unexpected archive member: " + member.name)
            target = destination / member.name
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe archive path.")
            target.parent.mkdir(exist_ok=True)
            source = bundle.extractfile(member)
            with target.open("xb") as handle:
                while chunk := source.read(1024 * 1024):
                    handle.write(chunk)
            if target.stat().st_size != expected[member.name]["bytes"] or sha256_file(target) != expected[member.name]["sha256"]:
                raise ValueError("Source hash mismatch: " + member.name)
    if sum(1 for p in destination.glob("*/*") if p.is_file()) != len(expected):
        raise ValueError("Incomplete collection.")
    write_json_exclusive(OUT / "collection_receipt.json", {"status": "HASH_VERIFIED", "file_count": len(expected),
                         "bytes": sum(row["bytes"] for row in inventory["files"]),
                         "checked_at": datetime.now(timezone.utc).isoformat(), "archive_sha256": sha256_file(archive)})
    print(json.dumps({"files": len(expected), "MiB": round(sum(r['bytes'] for r in inventory['files'])/2**20, 2),
                      "jobs": [(j['name'], j['job_id']) for j in jobs]}), flush=True)


if __name__ == "__main__":
    main()
