"""Stage the new package and run only its bounded native CPU preflight."""
from __future__ import annotations

import io
import shlex
import subprocess
import tarfile
from datetime import datetime, timezone

import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import ARM, OUT, PACKAGE, REMOTE, ROOT

PROGRAM = r'''
import hashlib,json,os,shutil,socket,subprocess,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!=CANONICAL or not root.resolve().is_relative_to(boundary):raise ValueError('host/canonical boundary changed')
if root.exists():raise FileExistsError('preserve existing/partial preflight package')
if shutil.disk_usage(root.parent).free<3*1024**3:raise RuntimeError('insufficient staging disk')
root.mkdir();seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or member.name not in FILES or member.name in seen or not target.is_relative_to(root.resolve()):raise ValueError('unsafe/unbound archive member')
  expected=FILES[member.name]
  if member.size!=expected['bytes'] or member.size>64*1024**2:raise ValueError('archive member size changed')
  data=archive.extractfile(member).read()
  if hashlib.sha256(data).hexdigest()!=expected['sha256']:raise ValueError('staged bytes changed')
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as handle:handle.write(data)
  seen.add(member.name)
if seen!=set(FILES):raise ValueError('incomplete archive')
def write(name,payload):
 with (root/name).open('x') as handle:json.dump(payload,handle,indent=2)
write('package_staging.json',{'status':'COMPLETE_NEW_CPU_PREFLIGHT_PACKAGE','files':len(seen),'training_started':False,'canonical_root':str(root.resolve())})
env=os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES='-1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',WANDB_MODE='disabled',HF_HUB_OFFLINE='1',WITH_PYG_LIB='0',TORCH_SPARSE_USE_PYG_LIB='0',TORCH_SCATTER_USE_PYG_LIB='0')
for key,name in [('TMPDIR','tmp'),('XDG_CACHE_HOME','cache'),('TORCH_HOME','cache/torch'),('HF_HOME','cache/hf'),('MPLCONFIGDIR','cache/matplotlib'),('TORCH_EXTENSIONS_DIR','cache/extensions')]:
 path=root/name;path.mkdir(parents=True,exist_ok=True);env[key]=str(path)
env['PYTHONPATH']=str(root/'control/runtime')+':/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor'
cmd=['/home/sbq/sbq/ml_ts_acceleration/venv/bin/python','-B','-m','scripts.adsorption.training536_cpu_preflight','--request',str(root/'control/training_request.json'),'--contract',str(root/'preflight_contract.json'),'--output',str(root/'preflight')]
try:
 with (root/'native_cpu.stdout').open('xb') as out,(root/'native_cpu.stderr').open('xb') as err:
  result=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=err,timeout=250)
 code=result.returncode
except subprocess.TimeoutExpired:
 code=124
returned=['package_staging.json','native_cpu.stdout','native_cpu.stderr']
if code==0:returned+=['preflight/native_preflight.json','preflight/parameters.json']
write('cpu_transport_exit.json',{'exit_code':code,'training_started':False,'GPU_execution':False,'file_hashes':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in returned}})
print(json.dumps({'CPU_preflight_process_exit':code,'training_started':False,'new_package_files':len(seen)}),flush=True)
sys.exit(code)
'''


def ssh_arguments():
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    options = ["-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=12"]
    return ssh, options


def run():
    if (OUT / "cpu_upload_reservation.json").exists():
        raise FileExistsError("preserve previous staging/preflight; inspect receipt rather than upload again")
    inventory = load_json_object(OUT / "deployment_inventory.json")
    files = {r["path"]: {"sha256": r["sha256"], "bytes": r["bytes"]} for r in inventory["files"]}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, item in files.items():
            path = (PACKAGE / name).resolve()
            if (not path.is_relative_to(PACKAGE.resolve()) or path.is_symlink()
                    or sha256_file(path) != item["sha256"] or path.stat().st_size != item["bytes"]):
                raise ValueError("local deployment bytes changed")
            archive.add(path, arcname=name, recursive=False)
    contract = load_json_object(PACKAGE / "preflight_contract.json")
    if contract["training_authorized"] or contract["forward_backward_optimizer_allowed"]:
        raise ValueError("CPU-only authorization boundary changed")
    program = ("ROOT=" + repr(REMOTE) + "\nCANONICAL=" + repr(contract["canonical_boundary_observed"])
               + "\nFILES=" + repr(files) + "\n" + PROGRAM).encode()
    bootstrap = "import sys;n=int(sys.stdin.buffer.readline());exec(compile(sys.stdin.buffer.read(n),'<536-cpu-package-preflight>','exec'))"
    command = "python3 -B -c " + shlex.quote(bootstrap)
    ssh, options = ssh_arguments()
    destination = ssh["user"] + "@" + ssh["host"]
    argv = ["ssh", "-T", *options, "-p", str(ssh["port"]), destination, command]
    write_json_exclusive(OUT / "cpu_upload_reservation.json", {
        "training_request_sha256": sha256_file(ARM / "training_request.json"), "remote_root": REMOTE,
        "file_count": len(files), "CPU_preflight_only": True, "training_authorized": False,
        "automatic_retry": False, "created_utc": datetime.now(timezone.utc).isoformat()})
    with (OUT / "cpu_transport.stdout").open("xb") as stdout, (OUT / "cpu_transport.stderr").open("xb") as stderr:
        result = subprocess.run(argv, input=str(len(program)).encode() + b"\n" + program + stream.getvalue(),
                                stdout=stdout, stderr=stderr, timeout=320)
    write_json_exclusive(OUT / "cpu_transport_process.json", {"exit_code": result.returncode,
                                                              "training_authorized": False, "GPU_execution": False})
    if result.returncode:
        raise RuntimeError("CPU staging/preflight failed; inspect saved receipt and remote state before retry")
    local = OUT / "native_return"
    local.mkdir()
    names = ["package_staging.json", "native_cpu.stdout", "native_cpu.stderr", "cpu_transport_exit.json",
             "preflight/native_preflight.json", "preflight/parameters.json"]
    # Canonical file bytes return with scp; no JSON extracted from console text.
    sources = [destination + ":" + REMOTE + "/" + n for n in names]
    subprocess.run(["scp", "-q", *options, "-P", str(ssh["port"]), *sources, str(local)], check=True, timeout=45)
    exit_record = load_json_object(local / "cpu_transport_exit.json")
    for name, expected in exit_record["file_hashes"].items():
        if sha256_file(local / name.rsplit("/", 1)[-1]) != expected:
            raise ValueError("returned native evidence bytes changed")
    native = load_json_object(local / "native_preflight.json")
    if native["request_sha256"] != sha256_file(ARM / "training_request.json") or native["CUDA_initialized"]:
        raise ValueError("native request binding/CUDA boundary mismatch")
    write_json_exclusive(OUT / "cpu_preflight_receipt.json", {
        "status": native["status"], "request_sha256": native["request_sha256"],
        "GPU_visibility": "UNKNOWN_NVML_FAILED_BOTH_HOSTS", "GPU_binding": None,
        "training_started": False, "model_inference_or_optimization": False,
        "source_files": source_file_manifest([OUT / "cpu_transport_process.json", *local.iterdir()])})
    print({"status": native["status"], "trainable_numel": native["trainable_numel"],
           "frozen_numel": native["frozen_numel"], "training_started": False}, flush=True)


if __name__ == "__main__":
    run()
