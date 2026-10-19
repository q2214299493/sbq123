"""Exclusive corrected upload/preflight/launch and bounded read-only snapshots."""
import argparse
import io
import json
import re
import shlex
import tarfile

from scripts.adsorption.direct_force_training import verify
from scripts.artifact_io import sha256_file, write_json_exclusive

from .transport import EVIDENCE, PACKAGE, REMOTE, RUN_ID, call, remote_module


def upload(sha):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_symlink():
                raise ValueError("upload symlink forbidden")
            if path.is_file():
                archive.add(path, arcname=path.relative_to(PACKAGE).as_posix(), recursive=False)
    program = r'''
import json,shutil,socket,sys,tarfile
from pathlib import Path
root=Path(ROOT)
boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!='/home/ubuntu/hdd/sbq/sbq' or not root.resolve().is_relative_to(boundary):raise ValueError('host/boundary mismatch')
if root.exists():raise FileExistsError('preserve existing or partial remote package')
if shutil.disk_usage(root.parent).free<3*1024**3:raise RuntimeError('insufficient checkpoint disk')
root.mkdir()
count=0
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe archive member')
  target.parent.mkdir(parents=True,exist_ok=True)
  with archive.extractfile(member) as source,target.open('xb') as output:shutil.copyfileobj(source,output)
  count+=1
print(json.dumps({'status':'UPLOAD_COMPLETE','files':count,'root':str(root)}))
'''
    write_json_exclusive(EVIDENCE / "upload_reservation.json", {"request_sha256": sha, "remote_root": REMOTE})
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\n" + program)
    print(call(command, "upload", stream.getvalue(), timeout=120).decode())


def status(name):
    program = r'''
import json,subprocess
from pathlib import Path
root=Path(ROOT)
result={}
for name in ('direct_launch_receipt.json','direct_started.json','direct_batch_exit_record.json'):
 p=root/name
 if p.is_file():result[name]=json.loads(p.read_text())
for arm in ('control','treatment'):
 p=root/arm/'output'/RUN_ID
 result[arm]={}
 for name in ('started.json','execution_device.json','native_two_backward_check.json','training_completed.json','producer_exit_record.json'):
  f=p/name
  if f.is_file():result[arm][name]=json.loads(f.read_text())
 log=p/'training.log'
 if log.is_file():
  with log.open('rb') as handle:
   handle.seek(max(0,log.stat().st_size-6000));result[arm]['log_tail']=handle.read(6000).decode(errors='replace')
result['GPU_processes']=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader'],timeout=12).decode()[:3000]
print(json.dumps(result))
'''
    source = "ROOT=" + repr(REMOTE) + "\nRUN_ID=" + repr(RUN_ID) + "\n" + program
    raw = call("env PYTHONDONTWRITEBYTECODE=1 python3 -", name, source.encode())
    value = json.loads(raw)
    compact = {key: record for key, record in value.items() if key not in ("control", "treatment")}
    for arm in ("control", "treatment"):
        item = value[arm]
        compact[arm] = {key: record for key, record in item.items() if key != "log_tail"}
        matches = re.findall(r"\bstep:\s*([0-9.eE+\-]+)", item.get("log_tail", ""))
        compact[arm]["latest_logged_step"] = int(float(matches[-1])) if matches else None
        if "Traceback" in item.get("log_tail", ""):
            compact[arm]["error_tail"] = item["log_tail"][-2200:]
    print(json.dumps(compact))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("upload", "preflight", "launch", "status"))
    parser.add_argument("--snapshot", default="status_first")
    args = parser.parse_args()
    sha = sha256_file(PACKAGE / "direct_request.json")
    verify(PACKAGE / "direct_request.json", sha)
    if args.action == "upload":
        upload(sha)
    elif args.action == "status":
        status(args.snapshot)
    else:
        if args.action == "launch":
            write_json_exclusive(EVIDENCE / "launch_reservation.json", {"request_sha256": sha, "automatic_retry": False})
        print(remote_module(args.action, sha).decode())


if __name__ == "__main__":
    main()
