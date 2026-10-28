"""Read-only native NequIP ASE CPU check using existing remote weights/seeds."""
import json
import shlex
from pathlib import Path

from scripts.artifact_io import source_file_manifest, write_json_exclusive
from .prepare_speed import OUTPUT, ROOT, TRAINING_REMOTE
from .relaxation_adapter import PYTHONS
from .transport import call

PROGRAM = r'''import importlib.metadata as metadata,json,time,torch,numpy as np
from pathlib import Path
from ase.io import read
torch.set_num_threads(4)
if torch.cuda.is_initialized():raise ValueError('CPU-only interface check')
started=time.monotonic();records=[]
model=Path(TRAINING)/'nequip_v2/output/best.ckpt'
calculator=nequip_calculator(model,MODEL_SHA['nequip'],'cpu')
for name,expected in SEED_SHA.items():
 path=Path('/home/sbq/sbq/fe110_paired_relaxation2_20261027_v2/geometry')/name/'POSCAR'
 if sha256_file(path)!=expected:raise ValueError('existing native seed changed')
 atoms=read(path,format='vasp');before=atoms.positions.copy();atoms.calc=calculator
 raw=atoms.get_forces(apply_constraint=False)
 if raw.shape!=(len(atoms),3) or not np.isfinite(raw).all() or not np.array_equal(before,atoms.positions):raise ValueError('ASE interface failed')
 records.append({'name':name,'POSCAR_sha256':expected,'shape':list(raw.shape),'finite':True,'coordinates_unchanged':True,'raw_forces_eV_A':raw.tolist()})
if torch.cuda.is_initialized():raise ValueError('unexpected CUDA')
print(json.dumps({'status':'PASS_NATIVE_NEQUIP_ASE_CPU_TWO_ORIGINS','model_device':str(next(calculator.model.parameters()).device),
 'model_sha256':sha256_file(model),'CUDA_initialized':False,'optimizer_steps':0,'accuracy_established':False,
 'elapsed_seconds':time.monotonic()-started,'packages':{key:metadata.version(key) for key in ['torch','nequip','e3nn','ase']},'cases':records}),flush=True)
'''


def check():
    adapter = ROOT / "archive/fe110_scratch512_20261028/relaxation_adapter.py"
    program = "__name__='native_interface_check'\n" + adapter.read_text(encoding="utf-8") + "\nTRAINING=" + repr(TRAINING_REMOTE) + "\n" + PROGRAM
    write_json_exclusive(OUTPUT / "native_cpu_reader.json", {"program": program, "remote_weights_or_geometry_changed": False,
        "source_files": source_file_manifest([adapter, Path(__file__)])})
    command = shlex.join(["env", "CUDA_VISIBLE_DEVICES=-1", "PYTHONDONTWRITEBYTECODE=1", "OMP_NUM_THREADS=4", "MKL_NUM_THREADS=4",
        "PYTHONPATH=" + TRAINING_REMOTE + "/nequip_v2/runtime", PYTHONS["nequip"], "-c", "import sys;exec(compile(sys.stdin.buffer.read(),'<cpu-interface-reader>','exec'))"])
    raw = call(command, "speed2_native_cpu_v2", data=program.encode(), timeout=180)
    result = json.loads(raw)
    if result["status"] != "PASS_NATIVE_NEQUIP_ASE_CPU_TWO_ORIGINS" or result["CUDA_initialized"] is not False:
        raise ValueError("native CPU interface check failed")
    write_json_exclusive(OUTPUT / "native_nequip_cpu_interface.json", result)
    print({k: result[k] for k in ["status", "model_device", "CUDA_initialized", "elapsed_seconds", "packages"]}, flush=True)


if __name__ == "__main__":
    check()
