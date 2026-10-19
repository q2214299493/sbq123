"""Read only exact copied DB/POSCAR numerics on MZ73; never runs a model."""
import json

from .transport import REMOTE, call

PROGRAM = r'''
import json,numpy as np
from pathlib import Path
from ase.db import connect
from ase.io import read
result={}
for arm in ('control','treatment'):
 root=Path(ROOT)/arm
 manifest=json.loads((root/'training_manifest.json').read_text())
 summary={key:{'mismatch_count':0,'max_abs_difference':0.,'examples':[]} for key in ('positions','cell','pbc','forces')}
 for split in ('train','development'):
  for dbrow,row in zip(connect(root/(split+'.db')).select(),manifest['splits'][split]):
   atoms=dbrow.toatoms();original=read(root/row['structure_path'],format='vasp')
   values={'positions':(atoms.positions,original.positions),'cell':(atoms.cell.array,original.cell.array),
    'pbc':(atoms.pbc,original.pbc),'forces':(atoms.get_forces(apply_constraint=False),np.asarray(row['forces_eV_per_A']))}
   for key,(actual,expected) in values.items():
    if not np.array_equal(actual,expected):
     difference=float(np.max(np.abs(np.asarray(actual,dtype=float)-np.asarray(expected,dtype=float))))
     out=summary[key];out['mismatch_count']+=1;out['max_abs_difference']=max(out['max_abs_difference'],difference)
     if len(out['examples'])<3:out['examples'].append({'sample_id':row['sample_id'],'max_abs_difference':difference})
 result[arm]=summary
print(json.dumps({'numerical_comparison':result,'model_loaded':False,'remote_files_written':False}))
'''


def main():
    command = "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -"
    raw = call(command, "numeric_roundtrip_diagnostic", ("ROOT=" + repr(REMOTE) + "\n" + PROGRAM).encode())
    print(json.dumps(json.loads(raw)))


if __name__ == "__main__":
    main()
