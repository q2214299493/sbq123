"""Deploy/preflight/launch one authorized private GPU validation; never retrain."""

from __future__ import annotations

import argparse
import json
import subprocess
import tarfile
from pathlib import Path

import yaml

from scripts.artifact_io import sha256_file, write_json_exclusive

from .prepare import DEST, REMOTE, ROOT

PYTHON = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"


def ssh_args() -> list[str]:
    values = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    return ["ssh", "-i", values["identity_file"], "-p", str(values["port"]), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", values["user"] + "@" + values["host"]]


def remote(name: str, body: str, timeout=60) -> dict:
    code = "ROOT_PATH=" + repr(REMOTE) + "\nEXPECTED=" + repr(sha256_file(DEST / "validation_request.json")) + "\n" + body
    result = subprocess.run(ssh_args() + [PYTHON + " -"], input=code.encode(), capture_output=True, timeout=timeout, check=False)
    (DEST / (name + ".stdout.txt")).write_bytes(result.stdout)
    (DEST / (name + ".stderr.txt")).write_bytes(result.stderr)
    write_json_exclusive(DEST / (name + ".receipt.json"), {"exit_code": result.returncode,
        "stdout_sha256": sha256_file(DEST / (name + ".stdout.txt")),
        "stderr_sha256": sha256_file(DEST / (name + ".stderr.txt"))})
    if result.returncode:
        raise RuntimeError("remote " + name + " failed; inspect preserved receipt, never repeat unchanged")
    return json.loads(result.stdout)


def scp(source: str, destination: str) -> None:
    ssh = ssh_args()
    args = ["scp"] + ssh[1:]
    args[args.index("-p")] = "-P"
    args = args[:-1] + [source, destination]
    result = subprocess.run(args, capture_output=True, timeout=90, check=False)
    if result.returncode:
        raise RuntimeError("scoped transfer failed: " + result.stderr.decode(errors="replace")[:1000])


def deploy() -> None:
    remote("mkdir", """import json
from pathlib import Path
p=Path(ROOT_PATH);boundary=Path('/home/sbq/sbq').resolve()
if not p.parent.resolve().is_relative_to(boundary):raise ValueError('remote root escaped')
p.mkdir(exist_ok=False)
print(json.dumps({'created':str(p),'model_executed':False}))
""")
    host = ssh_args()[-1]
    scp(str(DEST / "validation_bundle.tar"), host + ":" + REMOTE + "/validation_bundle.tar")
    expected_archive = sha256_file(DEST / "validation_bundle.tar")
    body = "ARCHIVE_SHA=" + repr(expected_archive) + "\n" + """import hashlib,json,tarfile
from pathlib import Path
root=Path(ROOT_PATH);archive=root/'validation_bundle.tar'
if hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_SHA:raise ValueError('uploaded archive changed')
with tarfile.open(archive) as handle:
 for member in handle.getmembers():
  if not member.isfile() or not (root/member.name).resolve().is_relative_to(root.resolve()):raise ValueError('unsafe archive member')
 handle.extractall(root)
for name in ('tmp','cache/xdg','cache/torch','cache/huggingface'):(root/name).mkdir(parents=True,exist_ok=True)
if hashlib.sha256((root/'validation_request.json').read_bytes()).hexdigest()!=EXPECTED:raise ValueError('request changed')
print(json.dumps({'archive_verified':True,'model_executed':False}))
"""
    remote("unpack", body)


def preflight() -> None:
    body = """import hashlib,json,subprocess,sys
from pathlib import Path
root=Path(ROOT_PATH);sys.path.insert(0,str(root/'runtime'))
from validation_helpers import environment
request=json.loads((root/'validation_request.json').read_bytes())
if hashlib.sha256((root/'validation_request.json').read_bytes()).hexdigest()!=EXPECTED:raise ValueError('request changed')
env=environment(root,request)
p=subprocess.run([env['AQCAT_PYTHON'],str(root/'runtime/runtime.py'),'preflight','--request',str(root/'validation_request.json'),'--authorization',str(root/'submission_authorization.json')],env=env,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55)
(root/'preflight.stdout.txt').write_bytes(p.stdout);(root/'preflight.stderr.txt').write_bytes(p.stderr)
record={'exit_code':p.returncode,'request_sha256':EXPECTED,'model_executed':False}
with (root/'preflight_record.json').open('x') as f:json.dump(record,f)
print(json.dumps(record))
if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-1800:])
"""
    result = remote("preflight", body, timeout=65)
    if result["exit_code"]:
        raise ValueError("remote preflight did not pass")


def launch() -> None:
    remote("launch", """import json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(ROOT_PATH);sys.path.insert(0,str(root/'runtime'))
from runtime import verify,digest
from validation_helpers import environment,gpu_available
request=verify(root/'validation_request.json',root/'submission_authorization.json',remote=True)
if digest(root/'validation_request.json')!=EXPECTED:raise ValueError('request changed')
preflight=json.loads((root/'preflight_record.json').read_bytes())
if preflight['exit_code'] or preflight['request_sha256']!=EXPECTED:raise ValueError('preflight stale')
gpu_available(request)
env=environment(root,request)
with (root/'launch_marker.json').open('x') as f:json.dump({'request_sha256':EXPECTED,'state':'one_attempt_reserved'},f)
with (root/'run_stdout.log').open('xb') as stdout,(root/'run_stderr.log').open('xb') as stderr:
 child=subprocess.Popen(['/usr/bin/timeout','--signal=TERM','--kill-after=15s',str(request['max_wall_seconds'])+'s',env['AQCAT_PYTHON'],str(root/'runtime/runtime.py'),'run','--request',str(root/'validation_request.json'),'--authorization',str(root/'submission_authorization.json')],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
receipt={'pid':child.pid,'run_id':request['run_id'],'request_sha256':EXPECTED,'launched_utc':datetime.now(timezone.utc).isoformat(),'execution_mode':'direct_no_scheduler','scheduler_job_id':None,'training':False,'new_VASP':False}
with (root/'launch_receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt))
""")


def poll() -> None:
    # Read-only console snapshot; do not overwrite earlier command receipts.
    code = "ROOT_PATH=" + repr(REMOTE) + "\n" + """import json,os
from pathlib import Path
root=Path(ROOT_PATH);result={}
for name in ('launch_receipt.json','output/producer_exit_record.json','output/baseline_device.json','output/candidate_device.json'):
 p=root/name
 if p.is_file() and p.stat().st_size<16384:result[name]=json.loads(p.read_bytes())
for name in ('run_stdout.log','run_stderr.log'):
 p=root/name
 if p.is_file():
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-1800));result[name+'_tail']=f.read().decode(errors='replace')
print(json.dumps(result))
"""
    result = subprocess.run(ssh_args() + [PYTHON + " -"], input=code.encode(), capture_output=True, timeout=25, check=True)
    print(result.stdout.decode())


def collect() -> None:
    result = remote("collect_manifest", """import hashlib,json,tarfile
from pathlib import Path
root=Path(ROOT_PATH);output=root/'output'
if not (output/'producer_exit_record.json').is_file():raise ValueError('producer not finished')
files=[p for p in output.rglob('*') if p.is_file()]+[root/'launch_receipt.json',root/'preflight_record.json',root/'run_stdout.log',root/'run_stderr.log']
request=json.loads((root/'validation_request.json').read_bytes())
cap=request.get('max_return_bytes',32000000) if request.get('document_kind')=='adsorption_bounded_random_sampling' else 32000000
if sum(p.stat().st_size for p in files)>cap:raise ValueError('return payload size cap')
manifest={'files':[{'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
with (root/'return_manifest.json').open('x') as f:json.dump(manifest,f)
archive=root/'returned_output.tar'
with tarfile.open(archive,'x') as handle:
 for p in files+[root/'return_manifest.json']:handle.add(p,arcname=p.relative_to(root).as_posix(),recursive=False)
print(json.dumps({'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size}))
""")
    archive = DEST / "returned_output.tar"
    if archive.exists():
        raise FileExistsError("inspect existing local transfer before retry")
    scp(ssh_args()[-1] + ":" + REMOTE + "/returned_output.tar", str(archive))
    if sha256_file(archive) != result["archive_sha256"]:
        raise ValueError("return archive changed")
    returned = DEST / "returned"
    returned.mkdir(exist_ok=False)
    with tarfile.open(archive) as handle:
        for member in handle.getmembers():
            if not member.isfile() or not (returned / member.name).resolve().is_relative_to(returned.resolve()):
                raise ValueError("unsafe return member")
        handle.extractall(returned, filter="data")
    manifest = json.loads((returned / "return_manifest.json").read_bytes())
    for entry in manifest["files"]:
        if sha256_file(returned / entry["path"]) != entry["sha256"]:
            raise ValueError("returned result binding mismatch")
    print(json.dumps({"status": "RETURN_BYTES_VERIFIED", "files": len(manifest["files"])}))


def main() -> None:
    global DEST, REMOTE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "preflight", "launch", "poll", "collect"))
    parser.add_argument("--package", type=Path, help="Explicit work-side package; remote root is read from its bound request")
    args = parser.parse_args()
    if args.package:
        DEST = args.package.resolve()
        if not DEST.is_relative_to(ROOT / "calculations"):
            raise ValueError("package must be in work calculations")
        request = json.loads((DEST / "validation_request.json").read_bytes())
        REMOTE = request["remote_root"]
        from .runtime import verify
        verify(DEST / "validation_request.json", DEST / "submission_authorization.json")
    {"deploy": deploy, "preflight": preflight, "launch": launch, "poll": poll, "collect": collect}[args.action]()


if __name__ == "__main__":
    main()
