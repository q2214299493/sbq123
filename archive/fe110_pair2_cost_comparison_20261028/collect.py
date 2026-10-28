"""Compact read-only force/SCF snapshots using the existing raw-frame owner."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import zlib

from archive.fe110_grouped_qc_20261026.review import force_table, moment_table, raw_frames
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import LOCAL_MAGNETIZATION_ROW_PATTERN

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
SUBMITTED = BASE / "paired_submission4_20261027_v1"
ML = BASE / "paired_relaxation2_20261027_v2"
OUTPUT = BASE / "paired_cost_comparison_20261028_v3"

READER = r'''
s=subprocess.run(['bjobs','-a','-w']+[r['job_id'] for r in ROWS],capture_output=True,text=True,timeout=20)
if s.returncode:raise ValueError('scheduler query failed:'+s.stderr)
states={}
for line in s.stdout.splitlines():
 fields=line.split()
 if len(fields)>=3 and fields[0].isdigit():states[fields[0]]=fields[2]
if set(states)!=set(r['job_id'] for r in ROWS):raise ValueError('scheduler identity mismatch')
print(json.dumps({'kind':'scheduler','returncode':s.returncode,'stdout':s.stdout,'states':states}),flush=True)
class Snapshot:
 def __init__(self,data):self.data=data
 def read_bytes(self):return self.data
for row in ROWS:
 root=Path(os.path.expanduser(row['remote_dir']));p=root/'OUTCAR';before=p.stat()
 if before.st_size>64*1024**2:raise ValueError('OUTCAR exceeds read cap')
 with p.open('rb') as f:data=f.read(before.st_size)
 if len(data)!=before.st_size:raise ValueError('source truncated during read')
 after=p.stat();stable=(before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino)
 if states[row['job_id']]=='DONE' and not stable:raise ValueError('closed OUTCAR changed')
 starts=list(re.finditer(rb'Iteration\s+(\d+)\s*\(\s*1\s*\)',data));cut=len(data)
 if states[row['job_id']]=='RUN' and starts:cut=starts[-1].start()
 frames=raw_frames(Snapshot(data[:cut]),row['atom_count']) if cut else []
 result={'kind':'case','row':row,'state':states[row['job_id']],'OUTCAR':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
  'stable_during_read':stable,'extent':'whole_file' if stable else 'source_prefix_at_open','parsed_prefix_end':cut},'files':{},'frames':[]}
 for name in ['OSZICAR','INCAR','POSCAR','CONTCAR','KPOINTS']:
  source=root/name;content=source.read_bytes()
  if len(content)>1024**2:raise ValueError('small file exceeds cap')
  result['files'][name]={'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'base64':base64.b64encode(content).decode()}
 for frame in frames:
  if 'forces_eV_per_A' not in frame or 'toten_eV' not in frame:continue
  forces=frame['forces_eV_per_A'];free=forces[18:];ads=forces[45:]
  entry={k:frame[k] for k in ['ionic_step','electronic_iteration','EDIFF_marker_before_force','toten_eV','source_byte_range']}
  entry.update(movable_fmax_eV_A=max(sum(v*v for v in force)**.5 for force in free),adsorbate_fmax_eV_A=max(sum(v*v for v in force)**.5 for force in ads),
   raw_force_table_sha256=hashlib.sha256(frame['raw_force_table']).hexdigest(),local_moment_tables=frame['local_moment_tables'])
  if frame['ionic_step']==1:
   entry.update(positions_A=frame['positions_A'],position_tokens=frame['position_tokens'],forces_eV_per_A=forces,
    raw_force_table_base64=base64.b64encode(frame['raw_force_table']).decode())
  result['frames'].append(entry)
 result['header_base64']=base64.b64encode(data[:12000]).decode()
 result['tail_base64']=base64.b64encode(data[-16000:]).decode()
 result['ionic_accuracy_marker']=b'reached required accuracy' in data
 result['normal_completion_footer']=b'General timing and accounting informations for this job' in data
 result['LOOP_plus_samples']=[line.decode(errors='replace') for line in data.splitlines() if b'LOOP+' in line][:2]
 content=json.dumps(result).encode();compressed=zlib.compress(content)
 print('emitting '+row['job_id']+' '+str(len(content))+' -> '+str(len(compressed)),file=sys.stderr,flush=True)
 print(base64.b64encode(compressed).decode(),flush=True)
'''


def reader(rows):
    functions = "\n\n".join(inspect.getsource(f) for f in [moment_table, force_table, raw_frames])
    old = "np.cumsum([0] + [len(line) for line in lines]).tolist()"
    if functions.count(old) != 1:
        raise ValueError("raw-frame byte-offset implementation changed")
    # Integer byte offsets only;force/moment parsing remains byte-identical owner code.
    functions = functions.replace(old, "list(accumulate([0] + [len(line) for line in lines]))")
    prefix = "import os,sys,json,re,hashlib,base64,subprocess,zlib\nfrom pathlib import Path\nfrom itertools import accumulate\n"
    prefix += "LOCAL_MAGNETIZATION_ROW_PATTERN=re.compile(" + repr(LOCAL_MAGNETIZATION_ROW_PATTERN.pattern) + ")\n"
    return prefix + "ROWS=" + repr(rows) + "\n" + functions + "\n" + READER


def collect():
    if OUTPUT.exists():
        raise FileExistsError("preserve existing compact snapshot")
    summary = load_json_object(SUBMITTED / "submission_summary.json")
    rows = [{**{k: r[k] for k in ["name", "model", "job_id", "remote_dir"]}, "atom_count": 50 if r["name"] == "10_A" else 51} for r in summary["records"]]
    if len(rows) != 4 or {r["job_id"] for r in rows} != {"9925060", "9925062", "9925063", "9925065"}:
        raise ValueError("only the four existing benchmark jobs may be read")
    OUTPUT.mkdir()
    program = reader(rows)
    write_json_exclusive(OUTPUT / "reader.json", {"program": program, "remote_writes": False,
        "owner_source_sha256": sha256_file(ROOT / "archive/fe110_grouped_qc_20261026/review.py"),
        "owner_function_sha256": {f.__name__: hashlib.sha256(inspect.getsource(f).encode()).hexdigest() for f in [moment_table, force_table, raw_frames]},
        "adaptation": "np.cumsum integer byte offsets replaced by itertools.accumulate;no scientific parser change"})
    encoded = base64.b64encode(zlib.compress(program.encode())).decode()
    args = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ControlMaster=no", "-o", "ControlPath=none",
        "sunboquan-codex", 'python3 -c "exec(__import__(\'zlib\').decompress(__import__(\'base64\').b64decode(\'' + encoded + '\')))"']
    with (OUTPUT / "raw.jsonl").open("xb") as stdout, (OUTPUT / "stderr.txt").open("xb") as stderr:
        result = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=90, check=False)
    write_json_exclusive(OUTPUT / "transport.json", {"returncode": result.returncode, "checked_at": datetime.now(timezone.utc).isoformat(), "command": args})
    if result.returncode:
        raise ValueError("compact read failed;inspect retained stderr")
    lines = (OUTPUT / "raw.jsonl").read_bytes().splitlines()
    decoded = [line if line.startswith(b"{") else zlib.decompress(base64.b64decode(line, validate=True)) for line in lines]
    with (OUTPUT / "raw_decoded.jsonl").open("xb") as output:
        output.write(b"\n".join(decoded) + b"\n")
    payload = [json.loads(line) for line in decoded]
    if len(payload) != 5 or payload[0]["kind"] != "scheduler" or {r["row"]["job_id"] for r in payload[1:]} != {r["job_id"] for r in rows}:
        raise ValueError("incomplete comparison snapshot")
    for record in payload[1:]:
        folder = OUTPUT / "snapshots" / record["row"]["name"] / record["row"]["model"]
        folder.mkdir(parents=True)
        for name, item in record["files"].items():
            data = base64.b64decode(item["base64"], validate=True)
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("returned small-file hash mismatch")
            with (folder / name).open("xb") as output:
                output.write(data)
        write_json_exclusive(folder / "extracted.json", record)
    write_json_exclusive(OUTPUT / "collection.json", {"status": "COMPACT_FORCE_AND_SCF_SNAPSHOT_COLLECTED", "scheduler": payload[0],
        "cases": [{"name": r["row"]["name"], "model": r["row"]["model"], "job_id": r["row"]["job_id"], "state": r["state"], "frames": len(r["frames"]), "OUTCAR": r["OUTCAR"]} for r in payload[1:]],
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "reader.json", OUTPUT / "raw.jsonl", OUTPUT / "transport.json"]),
        "no_new_calculations_or_restarts": True})
    print({"status": "COLLECTED", "network_bytes": (OUTPUT / "raw.jsonl").stat().st_size,
        "cases": [(r["row"]["job_id"], r["state"], len(r["frames"])) for r in payload[1:]]}, flush=True)


if __name__ == "__main__":
    collect()
