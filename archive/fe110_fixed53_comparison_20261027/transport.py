"""Exclusive deployment and bounded collection for one fixed53 comparison."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import shlex
import subprocess
import tarfile

import yaml

from scripts.adsorption.fixed_force_comparison import verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import OUTPUT, PACKAGE, POLICY, REMOTE


def call(command, name, data=None, timeout=55):
    ssh = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    argv = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
            "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUTPUT / (name + ".stdout")).open("xb") as stdout, (OUTPUT / (name + ".stderr")).open("xb") as stderr:
        result = subprocess.run(argv, input=data, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    write_json_exclusive(OUTPUT / (name + ".receipt.json"), {"returncode": result.returncode,
        "checked_at": datetime.now(timezone.utc).isoformat(), "command": command})
    if result.returncode:
        raise RuntimeError(name + " failed;inspect receipt/remote state,never blindly retry")
    return (OUTPUT / (name + ".stdout")).read_bytes()


def upload():
    verify(PACKAGE / "request.json")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_symlink():
                raise ValueError("package symlink forbidden")
            if path.is_file():
                archive.add(path, arcname=path.relative_to(PACKAGE).as_posix(), recursive=False)
    code = '''import json,shutil,sys,tarfile,socket
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary):raise ValueError('wrong host/root')
if root.exists():raise FileExistsError('preserve existing orpartial comparison package')
root.mkdir();count=0
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe archive')
  target.parent.mkdir(parents=True,exist_ok=True)
  with archive.extractfile(member) as source,target.open('xb') as output:shutil.copyfileobj(source,output)
  count+=1
print(json.dumps({'status':'UPLOADED','files':count}),flush=True)
'''
    write_json_exclusive(OUTPUT / "upload_reservation.json", {"request_sha256": sha256_file(PACKAGE / "request.json")})
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\n" + code)
    print(call(command, "upload", stream.getvalue(), timeout=120).decode(), flush=True)


def module(action):
    verify(PACKAGE / "request.json")
    prefix = REMOTE + "/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    command = "env PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=" + shlex.quote(REMOTE + "/cache/matplotlib")
    command += " TORCH_EXTENSIONS_DIR=" + shlex.quote(REMOTE + "/cache/torch_extensions") + " PYTHONPATH=" + shlex.quote(prefix)
    command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -m scripts.adsorption.fixed_force_comparison " + action
    command += " --request " + shlex.quote(REMOTE + "/request.json")
    if action == "launch":
        receipt = load_json_object(OUTPUT / "preflight.receipt.json")
        if receipt["returncode"] != 0:
            raise ValueError("native preflight has not passed")
        write_json_exclusive(OUTPUT / "launch_reservation.json", {"request_sha256": sha256_file(PACKAGE / "request.json")})
    print(call(command, action, timeout=180 if action == "preflight" else 55).decode(), flush=True)


def collect(name):
    program = '''import json
from pathlib import Path
root=Path(ROOT);result={}
for name in ['launch_marker.json','launch_receipt.json','output/started.json','output/controller_exit_record.json','output/producer_exit_record.json']:
 p=root/name
 if p.is_file():result[name]=json.loads(p.read_text())
if result.get('output/controller_exit_record.json',{}).get('exit_code')==0:
 result['predictions']={}
 for name in ['baseline','control','new512']:
  result['predictions'][name]=json.loads((root/'output'/str(name+'_forces.json')).read_text())
  result[str(name+'_device')]=json.loads((root/'output'/str(name+'_device.json')).read_text())
else:
 p=root/'output/prediction.log'
 if p.is_file():
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-2000));result['log_tail']=f.read(2000).decode(errors='replace')
print(json.dumps(result),flush=True)
'''
    raw = call("env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\n" + program), name)
    value = json.loads(raw)
    value["source_files"] = source_file_manifest([OUTPUT / (name + ".stdout"), OUTPUT / (name + ".receipt.json"), PACKAGE / "request.json"])
    write_json_exclusive(OUTPUT / (name + ".json"), value)
    print({"controller": value.get("output/controller_exit_record.json"), "producer": value.get("output/producer_exit_record.json"),
        "prediction_rows": {k: len(v["samples"]) for k, v in value.get("predictions", {}).items()}, "log_tail": value.get("log_tail")}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload", "preflight", "launch", "collect"])
    parser.add_argument("--snapshot", default="result")
    args = parser.parse_args()
    if args.action == "upload":
        upload()
    elif args.action == "collect":
        collect(args.snapshot)
    else:
        module(args.action)
