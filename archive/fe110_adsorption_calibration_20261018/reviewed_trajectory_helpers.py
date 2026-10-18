"""Byte-preserved helper snapshot for this archival, no-submission data review.

These are the existing trajectory reader/force association helpers, not a new
production parser or scientific authority. Source file hashes are recorded below.
"""

from __future__ import annotations

import numpy as np
from ase.geometry import find_mic


# Frozen source: archive/fe110_five_c2_adsorption_20261006/collect_adsorption_acceleration_frames.py; SHA256 2421cb86105304247e4ccef14b6897b9c56b91272a2010681b65a941c50c1409


def selected_steps(total):
    if total < 5:
        raise ValueError("trajectory too short")
    return sorted({1, 2, 5, max(1, round(total * .25)), max(1, round(total * .5)),
                   max(1, round(total * .75)), total - 1, total})


REMOTE_READER = r'''
import base64,hashlib,json,re,sys
from pathlib import Path
for record in RECORDS:
 print('reading '+record['name'],file=sys.stderr,flush=True)
 root=Path(record['remote_dir'].replace('~',str(Path.home()),1)); out=root/'OUTCAR'
 before=out.stat(); h=hashlib.sha256(); frames=[]
 iteration=None; reached=False; current=None
 with out.open('rb') as f:
  def line():
   value=f.readline(); h.update(value); return value
  while True:
   offset=f.tell(); text=line()
   if not text: break
   match=re.search(rb'Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)',text)
   if match:
    iteration=tuple(map(int,match.groups())); reached=False
   if b'aborting loop because EDIFF is reached' in text: reached=True
   if b'TOTAL-FORCE (eV/Angst)' in text:
    raw=text; rows=[]; tokens=[]
    while True:
     value=line(); raw+=value; fields=value.split()
     if len(fields)==6:
      try: row=[float(v) for v in fields]
      except ValueError: continue
      rows.append(row); tokens.append([v.decode() for v in fields[:3]])
     elif rows: break
     elif not value: break
    if not iteration or len(rows) not in (48,49): raise ValueError('invalid force frame')
    current={'ionic_step':iteration[0],'electronic_iteration':iteration[1],
             'EDIFF_marker_before_force':reached,'positions_A':[r[:3] for r in rows],
             'position_tokens':tokens,'forces_eV_per_A':[r[3:] for r in rows],
             'source_byte_range':[offset,f.tell()],'force_table_base64':base64.b64encode(raw).decode()}
    frames.append(current)
   if b'free  energy   TOTEN' in text and current is not None:
    current['toten_eV']=float(text.split()[4])
 after=out.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('source changed')
 with out.open('rb') as f:
  f.seek(max(0,before.st_size-100000)); tail=f.read(100000)
 if b'reached required accuracy' not in tail or b'General timing and accounting informations' not in tail:
  raise ValueError('source not normally force-converged')
 total=frames[-1]['ionic_step']; wanted=set(selected_steps(total))
 files={}
 for name in ('POSCAR','CONTCAR','INCAR','KPOINTS','OSZICAR','XDATCAR'):
  p=root/name
  if p.stat().st_size>2000000: raise ValueError('source file exceeds inspection budget: '+name)
  files[name]=base64.b64encode(p.read_bytes()).decode()
 print(json.dumps({'record':record,'frames':[r for r in frames if r['ionic_step'] in wanted],
                   'total_steps':total,'OUTCAR_sha256':h.hexdigest(),'OUTCAR_bytes':before.st_size,
                   'normal_completion':True,'files':files}),flush=True)
'''


# Frozen source: archive/fe110_five_c2_adsorption_20261006/prepare_c2_force_diagnostic.py; SHA256 12b2dc0a6c6b0e662dd902065338b511fddc8ee6a52d1371e92d11f7703c3695


def verify_frame(atoms, frame):
    positions = np.asarray(frame["positions_A"], dtype=float)
    forces = np.asarray(frame["forces_eV_per_A"], dtype=float)
    if positions.shape != (len(atoms), 3) or forces.shape != (len(atoms), 3):
        raise ValueError("Atom/force shape mismatch")
    if not np.isfinite(positions).all() or not np.isfinite(forces).all():
        raise ValueError("Nonfinite frame")
    _, delta = find_mic(positions - atoms.positions, atoms.cell, pbc=[True, True, False])
    precision = np.array([[len(t.split(".")[-1]) for t in row] for row in frame["position_tokens"]])
    bound = np.linalg.norm(0.5 * 10.0 ** (-precision), axis=1)
    if not np.all(delta <= bound + 1e-8):
        raise ValueError("Force geometry differs from exact structure beyond OUTCAR printing precision")
    if len(atoms.constraints) != 1 or list(atoms.constraints[0].get_indices()) != list(range(18)):
        raise ValueError("Unexpected fixed mask")
    return forces
