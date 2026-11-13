"""Read existing server outputs through stdin; no remote files or jobs created."""
from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path

from scripts.artifact_io import load_json_object, write_json_exclusive
from .collect import OUT, PACKAGE

PROGRAM = r'''
import hashlib,json,re
from pathlib import Path
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def parse(target):
 root=Path(target['directory']).expanduser();path=root/'OUTCAR'
 result={'requested':target,'directory':str(root),'source_exists':path.is_file(),'remote_writes':False}
 if not path.is_file():return result
 result['source_bytes']=path.stat().st_size
 if path.stat().st_size>250*1024**2:return {**result,'error':'bounded_read_size_limit'}
 result['inputs']={n:(root/n).read_text(errors='replace') for n in ['INCAR','KPOINTS','POSCAR'] if (root/n).is_file()}
 result['input_sha256']={n:digest(root/n) for n in result['inputs']}
 result['POTCAR_sha256']=digest(root/'POTCAR') if (root/'POTCAR').is_file() else None
 inc=result['inputs'].get('INCAR','');nsw=re.search(r'(?mi)^\s*NSW\s*=\s*(-?\d+)',inc)
 steps={1} if nsw and int(nsw[1])<=0 else set(target['steps']);result['selected_DFT_steps']=sorted(steps)
 h=hashlib.sha256();frames={};active=None;natoms=None;normal=False;titles=[]
 with path.open('rb') as f:
  def line():
   value=f.readline();h.update(value);return value
  while True:
   offset=f.tell();s=line()
   if not s:break
   if b'General timing and accounting' in s:normal=True
   if b'TITEL' in s:titles.append(s.decode().strip())
   n=re.search(rb'NIONS\s*=\s*(\d+)',s)
   if n:natoms=int(n[1])
   m=re.search(rb'Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)',s)
   if m:
    step,it=map(int,m.groups())
    if step in steps:
     active=frames.setdefault(step,{'ionic_step':step,'local_moment_tables':[]})
     active['electronic_iteration']=it;active['EDIFF_marker_before_force']=False
    else:active=None
   if active is None:continue
   if b'aborting loop because EDIFF is reached' in s:active['EDIFF_marker_before_force']=True
   if b'magnetization (x)' in s and natoms:
    moments=[]
    for _ in range(natoms+8):
     z=line().split()
     if z and z[0].isdigit():moments.append(float(z[-1]))
     if len(moments)==natoms:break
    if len(moments)==natoms:active['local_moment_tables'].append(moments)
   if b'TOTAL-FORCE (eV/Angst)' in s and natoms:
    rows=[];tokens=[];raw=s+line()
    for _ in range(natoms):
     z=line();raw+=z;parts=z.split();rows.append([float(x) for x in parts[:6]]);tokens.append([x.decode() for x in parts[:3]])
    active.update(positions_A=[z[:3] for z in rows],forces_eV_per_A=[z[3:] for z in rows],position_tokens=tokens,source_byte_range=[offset,f.tell()],force_extraction_sha256=hashlib.sha256(raw).hexdigest())
   if b'free  energy   TOTEN' in s and 'forces_eV_per_A' in active:
    active['toten_eV']=float(s.split()[4]);active['TOTEN_line']=s.decode().strip();active['TOTEN_byte_offset']=offset
 result.update(OUTCAR_sha256=h.hexdigest(),normal_completion=normal,natoms=natoms,POTCAR_titles=list(dict.fromkeys(titles)),frames=list(frames.values()))
 result['expected_hash_matches']=result['OUTCAR_sha256']==target['sha256']
 return result
output=[]
for target in TARGETS:
 try:output.append(parse(target))
 except Exception as e:output.append({'requested':target,'error':type(e).__name__+': '+str(e),'remote_writes':False})
print(json.dumps({'read_only':True,'new_jobs':False,'results':output},ensure_ascii=False))
'''


def run():
    manifest = load_json_object(PACKAGE / "training_manifest.json")
    index = load_json_object(OUT / "raw_source_index.json")["entries"]
    dependency = load_json_object(OUT / "registry_dependency_snapshot.json")
    jobs = {str(r["scheduler_job_id"]): r for r in dependency["jobs"]}
    missing = defaultdict(list)
    for rows in [*manifest["splits"].values(), manifest["quarantined_observed_heldout"]]:
        for row in rows:
            if not any(Path(v["paths"]["OUTCAR"]).is_file() for v in index.get(row["source_OUTCAR_sha256"], [])):
                missing[(str(row.get("source_job_id")), row["source_OUTCAR_sha256"])].append(row)
    targets = []
    for (job, digest), rows in missing.items():
        source = jobs.get(job, {})
        if source.get("server_alias") == "sunboquan-codex" and source.get("remote_directory"):
            targets.append({"job_id": job, "sha256": digest, "directory": source["remote_directory"],
                            "steps": sorted({int(r["ionic_step"]) for r in rows})})
    write_json_exclusive(OUT / "remote_read_targets.json", {"targets": targets, "read_only": True})
    program = "TARGETS=" + repr(targets) + "\n" + PROGRAM
    args = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=12", "sunboquan-codex", "python3 -B -"]
    with (OUT / "remote_raw_evidence.json").open("xb") as stdout, (OUT / "remote_read.stderr").open("xb") as stderr:
        result = subprocess.run(args, input=program.encode(), stdout=stdout, stderr=stderr, timeout=240)
    write_json_exclusive(OUT / "remote_read_receipt.json", {"process_exit_code": result.returncode,
                                                           "target_count": len(targets), "remote_writes": False,
                                                           "model_or_DFT_calculation": False})
    if result.returncode:
        raise RuntimeError("read-only source retrieval failed; inspect receipt before retry")
    evidence = load_json_object(OUT / "remote_raw_evidence.json")
    print(json.dumps({"source_count": len(evidence["results"]),
                      "hash_matches": sum(r.get("expected_hash_matches", False) for r in evidence["results"]),
                      "source_missing": sum(not r.get("source_exists", False) for r in evidence["results"])}))


if __name__ == "__main__":
    run()
