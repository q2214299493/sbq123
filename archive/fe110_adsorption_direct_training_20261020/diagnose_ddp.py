"""Bounded CPU-only parameter mapping after the failed first GPU producer; no forward/training."""
import json
import shlex

from .transport import REMOTE, call

PROGRAM = r'''
import hashlib,json,os
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']=''
import torch
torch.set_num_threads(4)
from fairchem.core.common.relaxation.ase_utils import patched_calc
from fairchem.core.models.equiformer_v2 import equiformer_v2_film
root=Path(ROOT)
checkpoint=root/'control/output/direct-adsorption-role-ab-20261020-v1/warmstart.pt'
calc=patched_calc(checkpoint_path=str(checkpoint),is_spin_off=False,is_low_fi=False,cpu=True)
model=getattr(calc,'model',None)
if model is None:model=calc.trainer.model
parameters=list(model.named_parameters())
assert all(p.device.type=='cpu' for _,p in parameters) and not torch.cuda.is_initialized()
indices=list(range(374,383))
mapping=[{'index':i,'name':parameters[i][0],'shape':list(parameters[i][1].shape),'requires_grad':parameters[i][1].requires_grad} for i in indices]
path=Path('/home/sbq/sbq/aqcat25/vendor/fairchem/core/trainers/base_trainer.py')
lines=path.read_text().splitlines()
matches=[i for i,line in enumerate(lines) if 'DistributedDataParallel' in line or 'find_unused_parameters' in line]
result={'status':'CPU_PARAMETER_MAPPING_NO_FORWARD','unused_parameters':mapping,'parameter_count':len(parameters),
 'native_DDP_source':[{'line':i+1,'source':'\n'.join(lines[max(0,i-4):i+9])} for i in matches],
 'forward_or_training_run':False,'CUDA_initialized':torch.cuda.is_initialized()}
with (root/'ddp_parameter_diagnostic.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
print(json.dumps(result))
'''


def main():
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    command = "env PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 WANDB_MODE=disabled PYTHONPATH=" + shlex.quote(prefix)
    command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -"
    raw = call(command, "ddp_parameter_diagnostic", ("ROOT=" + repr(REMOTE) + "\n" + PROGRAM).encode(), timeout=90)
    print(json.dumps(json.loads(raw)))


if __name__ == "__main__":
    main()
