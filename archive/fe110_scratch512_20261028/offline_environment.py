"""Install verified public wheels in the existing isolated native v4 environment."""
import base64
import hashlib
import io
import shlex
import subprocess
import tarfile
import urllib.request

import yaml

from scripts.artifact_io import write_json_exclusive
from .environment import ENV_ROOT
from .probe import OUTPUT, PYTHON, ROOT

PACKAGES = ["nequip/0.19.1", "matscipy/1.1.1", "lightning/2.6.6", "torchmetrics/1.9.0",
    "lightning-utilities/0.15.3", "pytorch-lightning/2.6.6"]

PROGRAM = r'''import hashlib,json,os,socket,subprocess,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary) or not (root/'venv/bin/python').is_file():raise ValueError('native isolated environment mismatch')
if (root/'environment.json').exists():raise FileExistsError('preserve completed environment')
destination=root/'wheelhouse';destination.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  if not member.isfile() or member.name not in WHEELS or member.size>2*1024**2:raise ValueError('unexpected public wheel')
  data=archive.extractfile(member).read()
  if hashlib.sha256(data).hexdigest()!=WHEELS[member.name]:raise ValueError('wheel digest changed')
  with (destination/member.name).open('xb') as target:target.write(data)
if {p.name for p in destination.iterdir()}!=set(WHEELS):raise ValueError('incomplete wheelhouse')
env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES='-1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
python=str(root/'venv/bin/python')
with (root/'offline_install.log').open('xb') as log:
 p=subprocess.run([python,'-m','pip','install','--no-index','--no-deps','--disable-pip-version-check',*[str(destination/n) for n in WHEELS]],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
if p.returncode:raise RuntimeError('offline installation failed')
code="import importlib.metadata as m,json,torch,nequip,nequip.train;print(json.dumps({'versions':{n:m.version(n) for n in ['torch','nequip','e3nn','lightning','numpy','scipy','matscipy']},'CUDA_initialized':torch.cuda.is_initialized()}));assert not torch.cuda.is_initialized()"
p=subprocess.run([python,'-c',code],env=env,capture_output=True,text=True,timeout=60)
(root/'offline_import.stdout').write_text(p.stdout);(root/'offline_import.stderr').write_text(p.stderr)
if p.returncode:raise RuntimeError('native CPU import failed')
result={'status':'NATIVE_CPU_IMPORT_PASS','environment_root':str(root),'base_environment_modified':False,**json.loads(p.stdout)}
with (root/'environment.json').open('x') as target:json.dump(result,target,indent=2)
print(json.dumps(result),flush=True)
'''


def prepare():
    import json
    folder = OUTPUT / "public_wheelhouse"
    folder.mkdir(exist_ok=False)
    wheels = {}
    sources = []
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for spec in PACKAGES:
            metadata = json.load(urllib.request.urlopen("https://pypi.org/pypi/" + spec + "/json", timeout=20))
            candidates = [r for r in metadata["urls"] if r["filename"].endswith(".whl") and ("py3-none-any" in r["filename"]
                or ("cp310" in r["filename"] and "x86_64" in r["filename"] and "manylinux" in r["filename"]))]
            if len(candidates) != 1:
                raise ValueError("ambiguous native wheel")
            item = candidates[0]
            data = urllib.request.urlopen(item["url"], timeout=30).read()
            if hashlib.sha256(data).hexdigest() != item["digests"]["sha256"]:
                raise ValueError("PyPI wheel digest mismatch")
            path = folder / item["filename"]
            path.write_bytes(data)
            wheels[path.name] = item["digests"]["sha256"]
            sources.append({"package": spec, "filename": path.name, "url": item["url"], "sha256": wheels[path.name]})
            archive.add(path, arcname=path.name, recursive=False)
    write_json_exclusive(OUTPUT / "public_wheels.json", {"sources": sources})
    program = "ROOT=" + repr(ENV_ROOT) + "\nWHEELS=" + repr(wheels) + "\n" + PROGRAM
    write_json_exclusive(OUTPUT / "offline_environment_program.json", {"program": program, "GPU_execution": False})
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    command = shlex.join([PYTHON, "-c", "exec(__import__('base64').b64decode('" + base64.b64encode(program.encode()).decode() + "'))"])
    args = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUTPUT / "offline_environment.stdout").open("xb") as stdout, (OUTPUT / "offline_environment.stderr").open("xb") as stderr:
        process = subprocess.run(args, input=stream.getvalue(), stdout=stdout, stderr=stderr, timeout=240, check=False)
    write_json_exclusive(OUTPUT / "offline_environment_receipt.json", {"returncode": process.returncode, "GPU_execution": False})
    if process.returncode:
        raise RuntimeError("offline native environment setup failed;preserve receipts before any retry")
    print((OUTPUT / "offline_environment.stdout").read_text(encoding="utf-8"))


if __name__ == "__main__":
    prepare()
