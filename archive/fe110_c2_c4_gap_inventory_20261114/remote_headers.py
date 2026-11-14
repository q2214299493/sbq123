"""Read small existing geometries in registered DFT directories; no remote writes."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .collect import OUT

PROGRAM = r'''
from pathlib import Path
import hashlib,json,re,sys
from collections import Counter
allowed=(Path.home()/'sbq/Fe110').resolve()
print('remote_reader_started registered_directories='+str(len(DIRECTORIES)),file=sys.stderr,flush=True)
paths=set();blocked=[]
for directory in DIRECTORIES:
 root=Path(directory).expanduser().resolve()
 if not root.is_relative_to(allowed):
  blocked.append(str(root));continue
 if not root.is_dir():continue
 for name in ('POSCAR','CONTCAR'):
  paths.add(root/name)
# Image directories are limited to registered file pointers below; do not walk every job.
for filename in FILES:
 p=Path(filename).expanduser().resolve()
 if p.is_relative_to(allowed):paths.add(p)
 else:blocked.append(str(p))
rows=[]
for number,path in enumerate(sorted(paths)):
 if number%100==0:print('paths_checked='+str(number),file=sys.stderr,flush=True)
 if not path.is_file():continue
 row={'path':str(path),'byte_size':path.stat().st_size}
 try:
  before=path.stat()
  if before.st_size>2*1024**2:
   row['status']='SKIPPED_OVER_2MIB';rows.append(row);continue
  data=path.read_bytes();lines=data.decode('utf-8-sig',errors='replace').splitlines()
  row['sha256']=hashlib.sha256(data).hexdigest()
  if len(lines)<8 or not all(re.fullmatch(r'[A-Z][a-z]?',s) for s in lines[5].split()):
   row['status']='VASP4_OR_INCOMPLETE_NEEDS_CONFIRMATION'
  else:
   species=lines[5].split();counts=[int(s) for s in lines[6].split()]
   if len(species)!=len(counts) or not counts or min(counts)<0:raise ValueError('counts')
   totals=Counter()
   for s,n in zip(species,counts):totals[s]+=n
   row.update(status='VASP5_HEADER_ONLY',composition_counts=dict(totals),total_C=totals['C'],Fe_count=totals['Fe'],natoms=sum(counts))
   if 4<=totals['C']<=6:row['geometry_text']=data.decode('utf-8-sig')
  after=path.stat();row['stable_during_read']=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
 except Exception as error:
  row['status']='READ_ERROR';row['error']=type(error).__name__+': '+str(error)
 rows.append(row)
print(json.dumps({'read_only':True,'remote_writes':False,'registered_directory_scope':len(DIRECTORIES),
 'allowed_root':str(allowed),'blocked_out_of_scope':blocked,'records':rows,
 'status_counts':dict(Counter(r['status'] for r in rows)),
 'carbon_frame_alias_counts':dict(Counter(str(r.get('total_C','unknown')) for r in rows)),
 'not_an_exhaustive_unregistered_remote_filesystem_search':True}))
'''


def run():
    snapshot = load_json_object(OUT / "registry_snapshot.json")["tables"]
    directories = sorted({r["remote_directory"] for r in snapshot["jobs"]
                          if r["server_alias"] == "sunboquan-codex" and r["remote_directory"]})
    files = sorted({r["remote_path"] for r in snapshot["files"] if r["remote_path"]
                    and (r["filename"] in ("POSCAR", "CONTCAR") or r["filename"].lower().endswith(".vasp"))})
    write_json_exclusive(OUT / "remote_header_request_v2.json", {"directories": directories, "files": files,
                        "read_only": True, "changed_scope": "registered_pointers_only_no_per_job_directory_walk",
                        "prior_failure": "55s timeout without progress;old files retained"})
    program = "DIRECTORIES=" + repr(directories) + "\nFILES=" + repr(files) + "\n" + PROGRAM
    args = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=12", "sunboquan-codex", "python3 -B -"]
    try:
        with (OUT / "remote_geometry_headers_v2.json").open("xb") as stdout, (OUT / "remote_headers_v2.stderr").open("xb") as stderr:
            completed = subprocess.run(args, input=program.encode("utf-8"), stdout=stdout, stderr=stderr, timeout=240)
    except subprocess.TimeoutExpired:
        write_json_exclusive(OUT / "remote_headers_receipt_v2.json", {
            "process_exit_code": None, "failure": "TIMEOUT_240_SECONDS", "remote_writes": False,
            "header_inventory_complete": False, "automatic_retry": False,
            "source_files": source_file_manifest([Path(__file__), OUT / "remote_header_request_v2.json"])})
        raise
    write_json_exclusive(OUT / "remote_headers_receipt_v2.json", {"process_exit_code": completed.returncode,
                       "source_files": source_file_manifest([Path(__file__), OUT / "remote_header_request_v2.json"]),
                       "remote_writes": False})
    if completed.returncode:
        raise RuntimeError("read-only header retrieval failed; inspect receipt, no automatic retry")
    result = load_json_object(OUT / "remote_geometry_headers_v2.json")
    print(json.dumps({k: result[k] for k in ("registered_directory_scope", "status_counts", "carbon_frame_alias_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    run()
