"""Create an isolated native CPU-preflight environment;never runs a GPU model."""
from datetime import datetime, timezone
import base64
import shlex
import subprocess

import yaml

from scripts.artifact_io import write_json_exclusive
from .probe import OUTPUT, PYTHON, ROOT

ENV_ROOT = "/home/sbq/sbq/fe110_scratch512_env_20261028_v4"
PROGRAM = r'''import importlib.metadata as m,json,os,site,socket,subprocess,sys,time
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!='/home/ubuntu/hdd/sbq/sbq' or not root.resolve().is_relative_to(boundary):raise ValueError('host/write boundary mismatch')
if root.exists():raise FileExistsError('preserve existing isolated environment')
root.mkdir()
env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES='-1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PIP_CACHE_DIR=str(root/'cache'))
print(json.dumps({'phase':'creating_isolated_venv','GPU_execution':False}),flush=True)
subprocess.run([sys.executable,'-m','venv','--without-pip','--system-site-packages',str(root/'venv')],env=env,check=True,timeout=90)
base_site=next(Path(p) for p in site.getsitepackages() if str(sys.prefix) in p)
new_site=root/'venv/lib/python3.10/site-packages'
with (new_site/'readonly_base_packages.pth').open('x') as f:f.write(str(base_site)+'\n')
pins=['nequip==0.19.1','e3nn==0.6.0','lightning==2.6.6','torchmetrics==1.9.0','numpy==1.26.4','matscipy==1.1.1']
(root/'requirements.txt').write_text('\n'.join(pins)+'\n')
python=str(root/'venv/bin/python')
print(json.dumps({'phase':'installing_only_into_new_venv'}),flush=True)
with (root/'install.log').open('xb') as log:
 p=subprocess.run([python,'-m','pip','install','--index-url','https://pypi.org/simple','--disable-pip-version-check','--report',str(root/'pip_report.json'),*pins],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
if p.returncode:raise RuntimeError('isolated pip failed;retained install.log')
code="import importlib.metadata as m,json,torch,nequip,nequip.train;print(json.dumps({'versions':{n:m.version(n) for n in ['torch','nequip','e3nn','lightning','numpy','matscipy']},'CUDA_initialized':torch.cuda.is_initialized()}));assert not torch.cuda.is_initialized()"
p=subprocess.run([python,'-c',code],env=env,capture_output=True,text=True,timeout=60)
(root/'import.stdout').write_text(p.stdout);(root/'import.stderr').write_text(p.stderr)
if p.returncode:raise RuntimeError('native CPU import failed;retained import logs')
result={'status':'NATIVE_CPU_IMPORT_PASS','environment_root':str(root),'base_environment_modified':False,**json.loads(p.stdout)}
(root/'environment.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
'''


def prepare():
    program = "ROOT=" + repr(ENV_ROOT) + "\n" + PROGRAM
    write_json_exclusive(OUTPUT / "native_environment_v4_program.json", {"program": program, "GPU_execution": False})
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    command = shlex.join([PYTHON, "-c", "exec(__import__('base64').b64decode('" + base64.b64encode(program.encode()).decode() + "'))"])
    args = ["ssh", "-n", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUTPUT / "native_environment_v4.stdout").open("xb") as stdout, (OUTPUT / "native_environment_v4.stderr").open("xb") as stderr:
        try:
            p = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=450, check=False)
            result = {"returncode": p.returncode}
        except subprocess.TimeoutExpired:
            result = {"returncode": None, "timeout_seconds": 450}
    result.update(checked_at=datetime.now(timezone.utc).isoformat(), GPU_execution=False)
    write_json_exclusive(OUTPUT / "native_environment_v4_receipt.json", result)
    if result["returncode"] != 0:
        raise RuntimeError("native environment setup failed;inspect receipts before retry")
    print((OUTPUT / "native_environment_v4.stdout").read_text(encoding="utf-8"))


if __name__ == "__main__":
    prepare()
