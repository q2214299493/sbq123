"""Upload bounded CPU preflights to the approved host;no GPU execution."""
import io
from pathlib import PurePosixPath
import shlex
import shutil
import subprocess
import tarfile

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .environment import ENV_ROOT
from .finalize import RUNTIME
from .prepare import config
from .probe import OUTPUT, PYTHON, ROOT

REMOTE = "/home/sbq/sbq/fe110_scratch512_cpucheck_20261028_v2"
PROGRAM = r'''import hashlib,json,os,socket,subprocess,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary) or root.exists():raise ValueError('native preflight root not fresh')
root.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or member.name not in FILES or not target.is_relative_to(root.resolve()) or member.size>20*1024**2:raise ValueError('unreviewed archive member')
  data=archive.extractfile(member).read()
  if hashlib.sha256(data).hexdigest()!=FILES[member.name]:raise ValueError('native source binding failed')
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as output:output.write(data)
env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES='-1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',WANDB_MODE='disabled',HYDRA_FULL_ERROR='1')
for name in ['cache','tmp','cache/matplotlib']:(root/name).mkdir(parents=True,exist_ok=True)
env.update(TMPDIR=str(root/'tmp'),XDG_CACHE_HOME=str(root/'cache'),MPLCONFIGDIR=str(root/'cache/matplotlib'),TORCH_HOME=str(root/'cache/torch'))
env['PYTHONPATH']=str(root/'nequip/runtime')
with (root/'nequip_cpu.log').open('xb') as log:
 p=subprocess.run([ENV+'/venv/bin/nequip-train','-cp',str(root/'nequip'),'-cn','config.yaml'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
if p.returncode:raise RuntimeError('native NequIP CPU smoke failed:'+ (root/'nequip_cpu.log').read_text(errors='replace')[-3000:])
env['PYTHONPATH']=str(root/'finetune/runtime')+':/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor'
env.update(WITH_PYG_LIB='0',TORCH_SPARSE_USE_PYG_LIB='0',TORCH_SCATTER_USE_PYG_LIB='0')
p=subprocess.run([sys.executable,'-m','scripts.adsorption.force_training_preflight','--request',str(root/'finetune/training_request.json'),'--native-cli'],cwd=root,env=env,capture_output=True,text=True,timeout=120)
(root/'finetune_cpu.stdout').write_text(p.stdout);(root/'finetune_cpu.stderr').write_text(p.stderr)
if p.returncode:raise RuntimeError('native finetune parser preflight failed:'+p.stderr[-2500:])
env['PYTHONPATH']=str(root/'nequip/runtime')
inspect="import json,torch;from pathlib import Path;p=Path("+repr(str(root/'nequip/output/best.ckpt'))+");v=torch.load(p,map_location='cpu',weights_only=False);s=[float(x['step']) for x in v['optimizer_states'][0]['state'].values() if 'step' in x];assert v['global_step']==2 and s and min(s)==max(s)==2;assert all(bool(torch.isfinite(t).all()) and not t.is_cuda for t in v['state_dict'].values() if isinstance(t,torch.Tensor));print(json.dumps({'global_step':v['global_step'],'optimizer_state_step_min':min(s),'optimizer_state_step_max':max(s),'CUDA_initialized':torch.cuda.is_initialized(),'checkpoint_bytes':p.stat().st_size}));assert not torch.cuda.is_initialized()"
q=subprocess.run([ENV+'/venv/bin/python','-c',inspect],env=env,capture_output=True,text=True,timeout=45)
if q.returncode:raise RuntimeError('native checkpoint scalar verification failed:'+q.stderr[-1500:])
result={'status':'BOTH_NATIVE_CPU_PREFLIGHTS_PASS_NO_GPU_TRAINING','native_checkpoint':json.loads(q.stdout),'finetune':json.loads(p.stdout),'upload_files_checked':len(FILES),'root':str(root),'GPU_training_started':False}
with (root/'preflight.json').open('x') as target:json.dump(result,target,indent=2)
print(json.dumps(result),flush=True)
'''


def run():
    folder = OUTPUT / "native_cpu_package_v2"
    folder.mkdir(exist_ok=False)
    for name in RUNTIME:
        target = folder / "nequip/runtime" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for split in ["train", "development"]:
        shutil.copyfile(OUTPUT / ("package/nequip/data/smoke_" + split + ".xyz"), folder / "nequip" / ("smoke_" + split + ".xyz"))
    stats = load_json_object(OUTPUT / "package/nequip/data/export.json")["training_only_initialization"]
    cfg = config(PurePosixPath(REMOTE) / "nequip", PurePosixPath(REMOTE) / "nequip/output", stats, smoke=True)
    with (folder / "nequip/config.yaml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)
    shutil.copytree(OUTPUT / "package/finetune/control", folder / "finetune")
    transport(folder)


def transport(folder):
    paths = sorted(p for p in folder.rglob("*") if p.is_file())
    files = {p.relative_to(folder).as_posix(): sha256_file(p) for p in paths}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path in paths:
            archive.add(path, arcname=path.relative_to(folder).as_posix(), recursive=False)
    program = "ROOT=" + repr(REMOTE) + "\nENV=" + repr(ENV_ROOT) + "\nFILES=" + repr(files) + "\n" + PROGRAM
    write_json_exclusive(OUTPUT / "native_cpu_v2_framed_program.json", {"program": program, "file_count": len(files), "GPU_execution": False})
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    bootstrap = "import sys;n=int(sys.stdin.buffer.readline());exec(compile(sys.stdin.buffer.read(n),'<reviewed-cpu-preflight>','exec'))"
    command = shlex.join([PYTHON, "-c", bootstrap])
    args = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    data = program.encode()
    payload = str(len(data)).encode() + b"\n" + data + stream.getvalue()
    with (OUTPUT / "native_cpu_v2_framed.stdout").open("xb") as stdout, (OUTPUT / "native_cpu_v2_framed.stderr").open("xb") as stderr:
        try:
            process = subprocess.run(args, input=payload, stdout=stdout, stderr=stderr, timeout=360, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            write_json_exclusive(OUTPUT / "native_cpu_v2_framed_receipt.json", {"returncode": None, "error": type(exc).__name__, "GPU_execution": False})
            raise
    write_json_exclusive(OUTPUT / "native_cpu_v2_framed_receipt.json", {"returncode": process.returncode, "GPU_execution": False})
    if process.returncode:
        raise RuntimeError("native CPU preflight failed;inspect saved output before any retry")
    import json
    result = json.loads((OUTPUT / "native_cpu_v2_framed.stdout").read_bytes())
    write_json_exclusive(OUTPUT / "native_cpu_v2.json", result)
    print(result)


if __name__ == "__main__":
    run()
