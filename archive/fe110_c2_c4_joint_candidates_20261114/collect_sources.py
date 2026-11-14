"""Read existing Fe110 geometry headers beyond registered directories only."""
from __future__ import annotations

from pathlib import Path
import subprocess

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "c2_c4_joint_candidates_20261114_v1"
PRIOR = BASE / "c2_c4_gap_inventory_20261114_v1"

PROGRAM = r'''
from pathlib import Path
from collections import Counter
import base64,hashlib,json,os,re,sys
base=(Path.home()/'sbq/Fe110').resolve()
records=[];walked=0;limits=[];unknown=[]
print('reader_started',file=sys.stderr,flush=True)
for directory,children,files in os.walk(base,followlinks=False):
 root=Path(directory);depth=len(root.relative_to(base).parts)
 children[:]=sorted(n for n in children if n not in {'potcars','.git','__pycache__'}) if depth<8 else []
 walked+=1
 if walked>6000:limits.append('directory_limit6000');break
 if walked%200==0:print('directories='+str(walked)+' geometries='+str(len(records)),file=sys.stderr,flush=True)
 for name in sorted(files):
  if not (name.startswith(('POSCAR','CONTCAR','XDATCAR')) or name.lower().endswith(('.vasp','.xyz','.extxyz'))):continue
  p=root/name
  if not p.resolve().is_relative_to(base):continue
  row={'path':str(p),'filename':name,'read_only':True}
  try:
   before=p.stat();row['byte_size']=before.st_size
   with p.open('rb') as f:head=f.read(16384)
   lines=head.decode('utf-8-sig',errors='replace').splitlines()
   totals=Counter()
   if p.suffix.lower() in {'.xyz','.extxyz'}:
    n=int(lines[0])
    if n>500 or n<1 or len(lines)<n+2:raise ValueError('unsupported_or_incomplete_xyz_header')
    symbols=[s.split()[0] for s in lines[2:n+2]]
    if not all(re.fullmatch(r'[A-Z][a-z]?',s) for s in symbols):raise ValueError('invalid_xyz_species')
    totals.update(symbols);row['coordinate_scope']='FIRST_XYZ_FRAME_ONLY'
   else:
    if len(lines)<8 or not all(re.fullmatch(r'[A-Z][a-z]?',s) for s in lines[5].split()):raise ValueError('VASP4_or_incomplete')
    species=lines[5].split();counts=[int(s) for s in lines[6].split()]
    if len(species)!=len(counts) or not counts or min(counts)<0:raise ValueError('counts')
    for s,n in zip(species,counts):totals[s]+=n
    row['coordinate_scope']='XDATCAR_COMPOSITION_HEADER_ONLY' if name.startswith('XDATCAR') else 'VASP5'
   row.update(status='HEADER_PARSED',composition_counts=dict(totals),total_C=totals['C'],Fe_count=totals['Fe'])
   if 4<=totals['C']<=6:
    if before.st_size>2*1024**2:
     row['coordinate_binding']='Needs confirmation;over2MiB'
    else:
     data=p.read_bytes();row['sha256']=hashlib.sha256(data).hexdigest();row['original_bytes_base64']=base64.b64encode(data).decode()
     row['coordinate_binding']='ORIGINAL_BYTES_RETURNED_NOT_NEW_STRUCTURE'
   after=p.stat();row['stable_during_read']=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
  except Exception as error:
   row['status']='UNKNOWN_OR_EMPTY';row['error']=type(error).__name__+': '+str(error);unknown.append(str(p))
  records.append(row)
  if len(records)>=20000:limits.append('geometry_limit20000');break
 if limits:break
print(json.dumps({'status':'BOUNDED_SCOPE_COMPLETE' if not limits else 'INCOMPLETE_LIMIT','read_only':True,'root':str(base),
 'directories_inspected':walked,'geometry_records':len(records),'limits':limits,'records':records,
 'carbon_counts':dict(Counter(str(r.get('total_C','unknown')) for r in records)),
 'C4_C5_C6_records':sum(4<=r.get('total_C',0)<=6 for r in records),
 'scope':'existing unpacked geometry files,depth<=8;no archives unpacked,no external server or GPU traversal',
 'new_jobs_or_remote_writes':False}))
'''


def run():
    args = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=12", "sunboquan-codex", "python3 -B -"]
    try:
        with (OUT / "server_extended_geometry_index.json").open("xb") as stdout, (OUT / "server_extended_geometry_index.stderr").open("xb") as stderr:
            completed = subprocess.run(args, input=PROGRAM.encode(), stdout=stdout, stderr=stderr, timeout=240)
    except subprocess.TimeoutExpired:
        write_json_exclusive(OUT / "server_extended_geometry_receipt.json", {
            "status": "TIMEOUT_240s", "read_only": True, "automatic_retry": False,
            "source_files": source_file_manifest([Path(__file__)])})
        raise
    write_json_exclusive(OUT / "server_extended_geometry_receipt.json", {
        "exit_code": completed.returncode, "read_only": True,
        "source_files": source_file_manifest([Path(__file__)])})
    if completed.returncode:
        raise RuntimeError("read-only retrieval failed;inspect receipt before any follow-up")
    d = load_json_object(OUT / "server_extended_geometry_index.json")
    print({k: d[k] for k in ("status", "directories_inspected", "geometry_records", "carbon_counts", "C4_C5_C6_records")}, flush=True)


if __name__ == "__main__":
    run()
