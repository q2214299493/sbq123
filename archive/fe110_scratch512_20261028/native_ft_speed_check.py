"""Native CPU interface check for the frozen partial FT checkpoint;no relaxation."""
import json
import shlex

from scripts.artifact_io import load_json_object, write_json_exclusive
from .prepare_speed import OUTPUT, TRAINING_OUTPUT, TRAINING_REMOTE
from .relaxation_adapter import MODEL_SHA, PYTHONS, SEED_SHA
from .transport import call

PROGRAM = r'''import contextlib,copy,hashlib,importlib.metadata as metadata,io,json,time,torch,numpy as np
from pathlib import Path
from ase.io import read
from ase.optimize import LBFGS
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
torch.set_num_threads(4)
if torch.cuda.is_initialized() or LBFGS.defaults['maxstep']!=.2:raise ValueError('CPU/optimizer interface changed')
started=time.monotonic();path=Path(MODEL)
if sha(path)!=EXPECTED:raise ValueError('frozen FT checkpoint changed')
payload=torch.load(path,map_location='cpu',weights_only=False);config=copy.deepcopy(payload['config']);del payload
config['is_debug']=True
if isinstance(config['dataset'],dict) and 'src' in config['dataset']:
 config['dataset']={'train':config['dataset']}
diagnostics=io.StringIO()
with contextlib.redirect_stdout(diagnostics):
 from fairchem.core.common.relaxation.ase_utils import patched_calc
 from fairchem.core.models.equiformer_v2 import equiformer_v2_film
 calc=patched_calc(config_yml=config,checkpoint_path=str(path),is_spin_off=False,is_low_fi=False,cpu=True)
 rows=[]
 for name,expected in SEEDS.items():
  p=Path('/home/sbq/sbq/fe110_paired_relaxation2_20261027_v2/geometry')/name/'POSCAR'
  if sha(p)!=expected:raise ValueError('frozen origin changed')
  atoms=read(p,format='vasp');atoms.set_tags(np.zeros(len(atoms),dtype=int));atoms.info.update(is_spin_off=False,is_low_fi=False)
  before=atoms.positions.copy();atoms.calc=calc;force=atoms.get_forces(apply_constraint=False)
  if force.shape!=(len(atoms),3) or not np.isfinite(force).all() or not np.array_equal(atoms.positions,before):raise ValueError('FT ASE interface failed')
  rows.append({'name':name,'POSCAR_sha256':expected,'shape':list(force.shape),'finite':True,'coordinates_unchanged':True,'raw_forces_eV_A':force.tolist()})
device=str(next(calc.trainer.model.parameters()).device)
if torch.cuda.is_initialized() or device!='cpu':raise ValueError('unexpected CUDA')
print(json.dumps({'status':'PASS_NATIVE_FINETUNE_ASE_CPU_TWO_ORIGINS','model_sha256':EXPECTED,'model_device':device,
 'CUDA_initialized':False,'optimizer_steps':0,'accuracy_established':False,'elapsed_seconds':time.monotonic()-started,
 'LBFGS_maxstep_A':LBFGS.defaults['maxstep'],'packages':{k:metadata.version(k) for k in ['torch','ase','e3nn']},'cases':rows}),flush=True)
'''


def check(attempt=1):
    if type(attempt) is not int or not 1 <= attempt <= 3:
        raise ValueError("explicit CPU interface attempt must be1..3")
    if (OUTPUT / "native_finetune_cpu_interface.json").exists():
        raise FileExistsError("preserve successful CPU interface check")
    candidate = load_json_object(TRAINING_OUTPUT / "terminal_review_20261028.json")["candidates"]["finetune_best"]
    program = "MODEL=" + repr(TRAINING_REMOTE + "/" + candidate["path"]) + "\nEXPECTED=" + repr(MODEL_SHA["finetune"]) + "\nSEEDS=" + repr(SEED_SHA) + "\n" + PROGRAM
    reader = "native_ft_cpu_reader.json" if attempt == 1 else f"native_ft_cpu_reader_attempt{attempt}.json"
    write_json_exclusive(OUTPUT / reader, {"program": program, "GPU_execution": False, "optimization": False})
    command = shlex.join(["env", "CUDA_VISIBLE_DEVICES=-1", "PYTHONDONTWRITEBYTECODE=1", "OMP_NUM_THREADS=4", "MKL_NUM_THREADS=4",
        "PYTHONPATH=/home/sbq/sbq/fe110_paired_relaxation2_20261027_v2/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor",
        PYTHONS["finetune"], "-c", "import sys;exec(compile(sys.stdin.buffer.read(),'<ft-cpu-reader>','exec'))"])
    transport = "speed2_ft_cpu_v2" if attempt == 1 else f"speed2_ft_cpu_v2_attempt{attempt}"
    result = json.loads(call(command, transport, data=program.encode(), timeout=180))
    if result["status"] != "PASS_NATIVE_FINETUNE_ASE_CPU_TWO_ORIGINS" or result["CUDA_initialized"] is not False:
        raise ValueError("native partial FT interface failed")
    write_json_exclusive(OUTPUT / "native_finetune_cpu_interface.json", result)
    print({k: result[k] for k in ["status", "model_device", "CUDA_initialized", "elapsed_seconds", "packages"]}, flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=int, default=1)
    check(parser.parse_args().attempt)
