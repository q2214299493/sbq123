"""Synthetic native-DDP CPU regression,not an AQCat25 forward or training job."""
import json
import shlex

from scripts.artifact_io import sha256_file

from .transport import REMOTE, ROOT, call

PROGRAM = r'''
import hashlib,json,os,sys,types
from pathlib import Path
from types import SimpleNamespace
os.environ['CUDA_VISIBLE_DEVICES']=''
import torch
from torch import nn
from torch.nn.parallel import DistributedDataParallel as DDP
torch.set_num_threads(1)
root=Path(ROOT)
scratch=root/'ddp_cpu_regression';scratch.mkdir(exist_ok=False)
from scripts.adsorption.role_force_trainer import RoleForceTrainer as Old
module=types.ModuleType('cpu_fixed_role_trainer')
exec(compile(SOURCE,'<new-role-source-CPU-test>','exec'),module.__dict__)
class Toy(nn.Module):
 def __init__(self):
  super().__init__();self.force=nn.Linear(3,3);self.energy=nn.Linear(3,1)
 def forward(self,x):return {'forces':self.force(x),'energy':self.energy(x).sum().reshape(1)}
batch=SimpleNamespace(forces=torch.zeros(2,3),fixed=torch.zeros(2,dtype=torch.long),natoms=torch.tensor([2]),adsorption_force_weights=torch.tensor([.5,.5]))
results={};gradients={};losses={}
for name,cls in (('before',Old),('fixed',module.RoleForceTrainer)):
 torch.manual_seed(42)
 torch.distributed.init_process_group('gloo',init_method=(scratch/(name+'.store')).as_uri(),rank=0,world_size=1)
 trainer=cls.__new__(cls);trainer.loss_functions=[('energy',{'coefficient':0}),('forces',{'coefficient':1})]
 trainer.elementrefs={};trainer.normalizers={}
 model=DDP(Toy());optimizer=torch.optim.SGD(model.parameters(),lr=.001)
 error=None;steps=0;energy_grad=None
 try:
  for step in range(2):
   optimizer.zero_grad(set_to_none=True)
   out=model(torch.ones(2,3));loss=trainer._compute_loss(out,batch);loss.backward()
   if step==0:
    gradients[name]=model.module.force.weight.grad.clone();losses[name]=loss.item()
    energy_grad=model.module.energy.weight.grad
   optimizer.step();steps+=1
 except RuntimeError as exc:error=str(exc)
 finally:torch.distributed.destroy_process_group()
 results[name]={'completed_steps':steps,'expected_DDP_error':bool(error and 'Expected to have finished reduction' in error),
  'energy_grad_none':energy_grad is None,'energy_grad_exact_zero':bool(energy_grad is not None and torch.count_nonzero(energy_grad)==0)}
assert results['before']['expected_DDP_error'] and results['before']['completed_steps']==1
assert results['fixed']['completed_steps']==2 and results['fixed']['energy_grad_exact_zero']
assert torch.equal(gradients['before'],gradients['fixed']) and losses['before']==losses['fixed']
assert not torch.cuda.is_initialized()
result={'status':'PASS_NATIVE_CPU_DDP_TOY_ONLY','cases':results,'force_loss_identical':True,'force_gradients_identical':True,
 'new_role_source_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),'CUDA_initialized':False,'AQCat25_forward_or_training':False}
with (root/'ddp_cpu_regression.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
print(json.dumps(result))
'''


def main():
    source = (ROOT / "scripts/adsorption/role_force_trainer.py").read_text(encoding="utf-8")
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    command = "env PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= PYTHONPATH=" + shlex.quote(prefix)
    command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -"
    program = "ROOT=" + repr(REMOTE) + "\nSOURCE=" + repr(source) + "\n" + PROGRAM
    raw = call(command, "ddp_cpu_regression", program.encode(), timeout=90)
    print(json.dumps(json.loads(raw)))
    assert sha256_file(ROOT / "scripts/adsorption/role_force_trainer.py") == json.loads(raw)["new_role_source_sha256"]


if __name__ == "__main__":
    main()
