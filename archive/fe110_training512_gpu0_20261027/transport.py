"""Exclusive GPU0 deployment and native execution;preserve the unstarted GPU1 package."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import shlex
import subprocess
import tarfile

import yaml

from scripts.adsorption.direct_force_training import verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import OLD, OLD_REMOTE, OUTPUT, PACKAGE, POLICY, REMOTE, RUN_ID


def call(command, name, data=None, timeout=55):
    ssh = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    argv = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=12", "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUTPUT / (name + ".stdout")).open("xb") as stdout, (OUTPUT / (name + ".stderr")).open("xb") as stderr:
        process = subprocess.run(argv, input=data, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    write_json_exclusive(OUTPUT / (name + ".receipt.json"), {"returncode": process.returncode, "checked_at": datetime.now(timezone.utc).isoformat(), "command": command})
    if process.returncode:
        raise RuntimeError(name + " failed;inspect receipt and remote state before any retry")
    return (OUTPUT / (name + ".stdout")).read_bytes()


def upload():
    sha = sha256_file(PACKAGE / "direct_request.json")
    verify(PACKAGE / "direct_request.json", sha)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_symlink():
                raise ValueError("upload symlink forbidden")
            if path.is_file():
                archive.add(path, arcname=path.relative_to(PACKAGE).as_posix(), recursive=False)
    code = '''import json,shutil,socket,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!='/home/ubuntu/hdd/sbq/sbq' or not root.resolve().is_relative_to(boundary):raise ValueError('host/boundary mismatch')
if root.exists():raise FileExistsError('preserve existing target')
if shutil.disk_usage(root.parent).free<3*1024**3:raise RuntimeError('insufficient checkpoint disk')
root.mkdir();count=0
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe archive member')
  target.parent.mkdir(parents=True,exist_ok=True)
  with archive.extractfile(member) as source,target.open('xb') as destination:shutil.copyfileobj(source,destination)
  count+=1
print(json.dumps({'status':'UPLOAD_COMPLETE','files':count,'root':str(root)}),flush=True)
'''
    write_json_exclusive(OUTPUT / "upload_reservation.json", {"request_sha256": sha, "remote_root": REMOTE})
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\n" + code)
    print(call(command, "upload", stream.getvalue(), timeout=120).decode(), flush=True)


def module_command(action):
    digest = sha256_file(PACKAGE / "direct_request.json")
    verify(PACKAGE / "direct_request.json", digest)
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    return ("env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONPATH=" + shlex.quote(prefix)
        + " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -m scripts.adsorption.direct_force_training " + action
        + " --request " + shlex.quote(REMOTE + "/direct_request.json") + " --request-sha256 " + digest)


def retire_gpu1():
    preflight = load_json_object(OUTPUT / "preflight.receipt.json")
    if preflight["returncode"] != 0:
        raise ValueError("GPU0 native preflight must pass before retirement")
    code = '''import hashlib,json,socket
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary):raise ValueError('host/boundary mismatch')
for name in ['direct_launch_marker.json','direct_launch_receipt.json','direct_started.json','direct_batch_exit_record.json']:
 if (root/name).exists():raise ValueError('old GPU1 launch may exist;stop migration')
auth=root/'direct_authorization.json';backup=root/'direct_authorization.retired_for_gpu0.json'
if not auth.is_file() or backup.exists():raise ValueError('old authorization state requires inspection')
digest=hashlib.sha256(auth.read_bytes()).hexdigest()
if digest!=EXPECTED:raise ValueError('old authorization changed')
auth.rename(backup)
with (root/'superseded_by_gpu0.json').open('x') as f:json.dump({'superseded_by':NEW,'old_auth_sha256':digest,'old_launch_markers_absent':True},f,indent=2)
print(json.dumps({'status':'OLD_GPU1_AUTH_RETIRED','old_auth_sha256':digest,'old_launch_markers_absent':True}),flush=True)
'''
    original = OLD / "direct_authorization.json"
    backup = OLD / "direct_authorization.retired_for_gpu0.json"
    if backup.exists():
        raise ValueError("local old authorization already retired;inspect instead of repeating")
    expected = sha256_file(original)
    write_json_exclusive(OUTPUT / "retirement_reservation.json", {"old_auth_sha256": expected, "old_root": OLD_REMOTE, "new_root": REMOTE})
    source = "ROOT=" + repr(OLD_REMOTE) + "\nNEW=" + repr(REMOTE) + "\nEXPECTED=" + repr(expected) + "\n" + code
    result = json.loads(call("env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote(source), "retire_gpu1"))
    original.rename(backup)
    if sha256_file(backup) != expected:
        raise ValueError("retired authorization bytes changed")
    write_json_exclusive(OUTPUT / "retirement_receipt.json", {**result, "new_root": REMOTE, "source_files": source_file_manifest([backup, OUTPUT / "retire_gpu1.stdout", OUTPUT / "retire_gpu1.receipt.json"])})
    print(result, flush=True)


def status(name):
    digest = sha256_file(PACKAGE / "direct_request.json")
    code = '''import json,re,subprocess
from pathlib import Path
root=Path(ROOT);result={'records':{},'producer':{}}
for name in ['preflight_control.json','direct_launch_marker.json','direct_launch_receipt.json','direct_started.json','direct_batch_exit_record.json']:
 p=root/name
 if p.is_file():result['records'][name]=json.loads(p.read_text())
directory=root/'control/output'/RUN_ID
for name in ['started.json','execution_device.json','cuda_allocator_budget.json','native_two_backward_check.json','training_completed.json','producer_exit_record.json']:
 p=directory/name
 if p.is_file():result['producer'][name]=json.loads(p.read_text())
log=directory/'training.log'
if log.is_file():
 with log.open('rb') as f:
  f.seek(max(0,log.stat().st_size-5000));tail=f.read(5000).decode(errors='replace')
 steps=re.findall(r'\\bstep:\\s*([0-9.eE+\\-]+)',tail)
 result['latest_logged_step']=int(float(steps[-1])) if steps else None
 if 'Traceback' in tail:result['error_tail']=tail[-2500:]
result['GPU_processes']=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader'],timeout=12).decode()[:5000]
print(json.dumps(result),flush=True)
'''
    source = "ROOT=" + repr(REMOTE) + "\nRUN_ID=" + repr(RUN_ID) + "\n" + code
    result = json.loads(call("env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote(source), name))
    result["request_sha256"] = digest
    result["source_files"] = source_file_manifest([OUTPUT / (name + ".stdout"), OUTPUT / (name + ".receipt.json"), PACKAGE / "direct_request.json"])
    write_json_exclusive(OUTPUT / (name + ".json"), result)
    print({k: v for k, v in result.items() if k not in ["source_files", "GPU_processes"]}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload", "preflight", "retire-gpu1", "launch", "status"])
    parser.add_argument("--snapshot", default="status_startup")
    args = parser.parse_args()
    if args.action == "upload":
        upload()
    elif args.action == "retire-gpu1":
        retire_gpu1()
    elif args.action == "status":
        status(args.snapshot)
    else:
        if args.action == "launch":
            load_json_object(OUTPUT / "retirement_receipt.json")
            write_json_exclusive(OUTPUT / "launch_reservation.json", {"request_sha256": sha256_file(PACKAGE / "direct_request.json"), "automatic_retry": False})
        print(call(module_command(args.action), args.action, timeout=330 if args.action == "preflight" else 55).decode(), flush=True)
