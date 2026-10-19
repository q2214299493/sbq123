"""Run synthetic tensors through deployed Fairchem on CPU,no model or remote files."""
import argparse
import hashlib
import json
import subprocess

from scripts.artifact_io import sha256_file, write_json_exclusive

from .probe_runtime import OUTPUT, ROOT

REMOTE = r'''
import copy,hashlib,json,os,sys,types
os.environ['CUDA_VISIBLE_DEVICES']=''
import numpy as np
import torch
torch.set_num_threads(1)
from ase import Atoms
from ase.constraints import FixAtoms
from ase.calculators.singlepoint import SinglePointCalculator
from fairchem.core.datasets.ase_datasets import AseDBDataset
from fairchem.core.modules.evaluator import Evaluator
from fairchem.core.common.registry import registry
for package in ('scripts','scripts.adsorption'):
 m=types.ModuleType(package); m.__path__=[]; sys.modules[package]=m
for name,source in SOURCES.items():
 module=types.ModuleType(name); module.__file__='<CPU-smoke-only:'+name+'>'
 sys.modules[name]=module; exec(compile(source,module.__file__,'exec'),module.__dict__)
from scripts.adsorption.force_role_data import DATA_KEYS,ROLE_IDS,ROLE_NAMES,TRAINER
from scripts.adsorption.force_role_runtime import RoleBatchSampler
from scripts.adsorption.role_force_trainer import RoleForceTrainer
assert registry.get_trainer_class(TRAINER) is RoleForceTrainer

class FixtureDataset(AseDBDataset):
 def _load_dataset_get_ids(self,config): self.dbs=[]; return [0,1,2]
 @property
 def indices(self): return np.arange(3)
 @property
 def _metadata(self):
  value={'natoms':np.array([49,50,47]),'row_ids':np.arange(1,4)}
  if self.config['src']=='fixture_train': value['adsorption_sampling_probability']=np.array([.7,.2,.1])
  return value
 def get_atoms(self,idx):
  atoms=Atoms(('Fe45C2OH','Fe45C2OH2','Fe45CH')[idx],positions=np.arange((49,50,47)[idx]*3).reshape(-1,3)*.1,cell=np.eye(3)*100,pbc=True)
  atoms.set_constraint(FixAtoms(indices=list(range(18)))); atoms.set_tags(np.zeros(len(atoms),dtype=int))
  symbols=atoms.get_chemical_symbols(); groups={k:[] for k in ROLE_NAMES}
  for i,s in enumerate(symbols):
   if i<18: continue
   key='adsorbate_'+s if s!='Fe' else 'near_Fe' if i<25 else 'other_Fe'
   groups[key].append(i)
  masses=dict(zip(ROLE_NAMES,[2.,1.,1.,2.,1.])); total=sum(masses[k] for k,g in groups.items() if g)
  w=np.zeros(len(atoms)); roles=np.zeros(len(atoms),dtype=int)
  for k,indices in groups.items():
   if indices: w[indices]=masses[k]/(total*len(indices)); roles[indices]=ROLE_IDS[k]
  atoms.info.update(sid='fixture_'+str(idx),adsorption_force_weights=w.tolist(),adsorption_force_roles=roles.tolist(),adsorption_replay=int(idx==2))
  atoms.calc=SinglePointCalculator(atoms,energy=-1.,forces=np.full((len(atoms),3),.3+idx*.1))
  return atoms

fixture_module=types.ModuleType('role_cpu_fixture'); fixture_module.FixtureDataset=FixtureDataset
sys.modules['role_cpu_fixture']=fixture_module
dataset={'format':'role_cpu_fixture.FixtureDataset','src':'fixture_train','seed':42,
 'a2g_args':{'r_energy':True,'r_forces':True,'r_edges':False,'r_data_keys':list(DATA_KEYS)},
 'atoms_transform_args':{'skip_always':True}}
trainer=RoleForceTrainer.__new__(RoleForceTrainer); trainer.device=torch.device('cpu')
trainer.config={'model':{'otf_graph':True},'optim':{'batch_size':2,'eval_batch_size':2,'num_workers':0,
 'load_balancing':'atoms','grouped_force_objective':True},'cmd':{'seed':42},'dataset':dataset,
 'val_dataset':{**copy.deepcopy(dataset),'src':'fixture_val'},'test_dataset':{},'relax_dataset':{}}
trainer.load_datasets()
assert isinstance(trainer.train_sampler,RoleBatchSampler)
indices=np.asarray(trainer.train_dataset.indices)
np.testing.assert_array_equal(trainer.train_sampler.weights.numpy(),np.array([.7,.2,.1])[indices])
assert sorted(i for batch in trainer.val_sampler for i in batch)==[0,1,2]
assert sum(batch.num_graphs for batch in trainer.val_loader)==3
full_sequence=list(trainer.train_sampler)
trainer.train_sampler.set_epoch_and_start_iteration(0,1)
assert list(trainer.train_sampler)==full_sequence[1:]
trainer.train_sampler.set_epoch(0)
for graph in trainer.train_dataset:
 assert torch.all(graph.tags==0) and int(graph.fixed.sum())==18
 assert graph.adsorption_force_weights.shape==(len(graph.pos),)
 assert torch.all(graph.adsorption_force_weights[:18]==0)
class Scale:
 def norm(self,value): return value/2.887317180633545
 def denorm(self,value): return value*2.887317180633545
 def __call__(self,value): return self.denorm(value)
trainer.loss_functions=[('energy',{'coefficient':0}),('forces',{'coefficient':1})]
trainer.elementrefs={}; trainer.normalizers={'forces':Scale()}
trainer.output_targets={'forces':{'level':'atom','train_on_free_atoms':True,'eval_on_free_atoms':True},'energy':{'level':'system'}}
batch=next(iter(trainer.train_loader))
predicted=(trainer.normalizers['forces'].norm(batch.forces).detach()+.1).requires_grad_()
with torch.no_grad(): predicted[batch.fixed!=0]=1000
out={'forces':predicted,'energy':batch.energy.clone()}
loss=trainer._compute_loss(out,batch); assert abs(loss.item()-.1*np.sqrt(3))<1e-6
loss.backward(); assert torch.all(predicted.grad[batch.fixed!=0]==0) and torch.isfinite(predicted.grad).all()
for dtype in (torch.float16,torch.bfloat16):
 mp_predicted=torch.ones_like(batch.forces,dtype=dtype,requires_grad=True)
 with torch.autocast('cpu',dtype=torch.bfloat16): mp_loss=trainer._compute_loss({'forces':mp_predicted},batch)
 assert mp_loss.dtype==torch.float32 and torch.isfinite(mp_loss)
 mp_loss.backward(); assert torch.all(mp_predicted.grad[batch.fixed!=0]==0) and torch.isfinite(mp_predicted.grad).all()
evaluator=Evaluator.__new__(Evaluator); evaluator.target_metrics={'forces':['mae'],'energy':['mae']}
with torch.no_grad(): metrics=trainer._compute_metrics(out,batch,evaluator)
assert abs(metrics['forces_role_vector_mae']['metric']-.1*np.sqrt(3)*2.887317180633545)<1e-5
assert metrics['forces_adsorbate_C_vector_mae']['numel']>0 and metrics['forces_near_Fe_vector_mae']['numel']>0
with torch.no_grad():
 for val_batch in trainer.val_loader:
  val_metrics=trainer._compute_metrics({'forces':trainer.normalizers['forces'].norm(val_batch.forces),'energy':val_batch.energy.clone()},val_batch,evaluator)
  assert val_metrics['forces_role_vector_mae']['metric']<1e-6
assert not torch.cuda.is_initialized()
print(json.dumps({'status':'PASS_NATIVE_FAIRCHEM_CPU_SYNTHETIC_FIXTURES','native_trainer_datasets_sampler_collater_loss_metrics':True,
 'train_fixture_graphs':3,'validation_fixture_graphs':3,'shuffled_subset_indices':indices.tolist(),'fixed_gradients_zero':True,
 'raw_graph_weights_consumed':True,'normalized_loss':loss.item(),'physical_role_metric_eV_A':metrics['forces_role_vector_mae']['metric'],
 'torch_version':torch.__version__,'model_instantiated':False,'checkpoint_loaded_or_written':False,'GPU_used':False,
 'training_performed':False,'remote_test_files_written':False,'heldout_or_actual_private_structures_sent':False,
 'registry_class_path_selected':True,'CPU_amp_force_dtypes_tested':['float16','bfloat16'],'sampler_resume_exact':True}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    files = [ROOT / ("scripts/adsorption/" + name + ".py") for name in ("force_role_data", "force_role_runtime", "role_force_trainer")]
    sources = {"scripts.adsorption." + p.stem: p.read_text(encoding="utf-8") for p in files}
    code = "SOURCES=" + repr(sources) + "\n" + REMOTE
    output, errors = OUTPUT / f"native_cpu_smoke_{args.attempt}.json", OUTPUT / f"native_cpu_smoke_{args.attempt}.stderr.txt"
    if output.exists() or errors.exists():
        raise FileExistsError("preserve prior smoke attempt")
    command = ("env PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= WANDB_MODE=disabled "
        "XDG_CACHE_HOME=/home/sbq/sbq/aqcat25/cache/xdg TORCH_HOME=/home/sbq/sbq/aqcat25/cache/torch "
        "PYTHONPATH=/home/sbq/sbq/aqcat25_ts_pilot:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor "
        "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python -")
    with output.open("xb") as stdout, errors.open("xb") as stderr:
        result = subprocess.run(["ssh", "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-p", "36039", "sbq@10sx4jr711576.vicp.fun", command],
            input=code.encode(), stdout=stdout, stderr=stderr, timeout=90, check=False)
    write_json_exclusive(OUTPUT / f"native_cpu_smoke_{args.attempt}.receipt.json", {"exit_code": result.returncode,
        "code_sha256": hashlib.sha256(code.encode()).hexdigest(), "stdout_sha256": sha256_file(output),
        "source_hashes": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in files}, "model_run_or_training": False})
    if result.returncode:
        raise RuntimeError("native CPU fixture smoke failed;inspect preserved stderr")
    if output.stat().st_size > 32000:
        raise ValueError("bounded result payload exceeded")
    print(json.dumps(json.loads(output.read_bytes())))


if __name__ == "__main__":
    main()
