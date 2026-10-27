"""Exclusive deployment and bounded collection for one paired ML relaxation comparison."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import shlex
import subprocess
import tarfile

import yaml

from .runtime import MODULE, verify
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
    command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -m " + MODULE + " " + action
    command += " --request " + shlex.quote(REMOTE + "/request.json")
    if action == "launch":
        receipt = load_json_object(OUTPUT / "preflight.receipt.json")
        if receipt["returncode"] != 0:
            raise ValueError("native preflight has not passed")
        write_json_exclusive(OUTPUT / "launch_reservation.json", {"request_sha256": sha256_file(PACKAGE / "request.json")})
    print(call(command, action, timeout=180 if action == "preflight" else 55).decode(), flush=True)


def collect(checkpoint):
    from archive.fe110_training512_gpu0_20261027.collect import extract_returned
    program = '''import hashlib,json
from pathlib import Path
root=Path(ROOT)
for name in ['controller_exit_record.json','producer_exit_record.json']:
 p=root/'output'/name
 if not p.is_file():raise ValueError('comparison not terminal;do not recollect blindly')
 r=json.loads(p.read_text())
 if r['exit_code']!=0 or r['request_sha256']!=SHA:raise ValueError('producer/controller failed')
files=[]
for p in sorted((root/'output').rglob('*')):
 if p.is_symlink():raise ValueError('output symlink forbidden')
 if p.is_file():
  size=p.stat().st_size
  if size>4*1024**2:raise ValueError('per-file collection cap exceeded')
  files.append({'path':p.relative_to(root).as_posix(),'bytes':size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for name in ['launch_marker.json','launch_receipt.json']:
 p=root/name;files.append({'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
if sum(r['bytes'] for r in files)>8*1024**2:raise ValueError('collection cap exceeded')
print(json.dumps({'request_sha256':SHA,'files':files}),flush=True)
'''
    digest = sha256_file(PACKAGE / "request.json")
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\nSHA=" + repr(digest) + "\n" + program)
    manifest_name = checkpoint + "_manifest"
    archive_name = checkpoint + "_archive"
    manifest = json.loads(call(command, manifest_name))
    write_json_exclusive(OUTPUT / (manifest_name + ".json"), manifest)
    program = "import sys,tarfile\nfrom pathlib import Path\nwith tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:\n for name in FILES:archive.add(Path(ROOT)/name,arcname=name,recursive=False)\n"
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\nFILES=" + repr([r["path"] for r in manifest["files"]]) + "\n" + program)
    blob = call(command, archive_name, timeout=120)
    extract_returned(blob, manifest, OUTPUT / "returned")
    write_json_exclusive(OUTPUT / "collection_receipt.json", {"status": "PAIRED_ML_COLLECTED", "files": len(manifest["files"]),
        "request_sha256": digest, "source_files": source_file_manifest([OUTPUT / (manifest_name + ".json"), OUTPUT / (archive_name + ".stdout")])})
    print({"status": "PAIRED_ML_COLLECTED", "files": len(manifest["files"])}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload", "preflight", "launch", "collect"])
    parser.add_argument("--checkpoint", default="collection")
    args = parser.parse_args()
    if args.action == "upload":
        upload()
    elif args.action == "collect":
        collect(args.checkpoint)
    else:
        module(args.action)
