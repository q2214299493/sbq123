"""Exact-once Slurm transport and read-only status; never stop jobs or run VASP."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import shlex
import subprocess
import tarfile

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .prepare import OUT, PACKAGE, REMOTE, ROOT


def call(command, phase, data=None, timeout=55):
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    argv = ["ssh", "-T", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=12", "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUT / f"{phase}.stdout").open("xb") as output, (OUT / f"{phase}.stderr").open("xb") as error:
        result = subprocess.run(argv, input=data, stdout=output, stderr=error, timeout=timeout, check=False)
    write_json_exclusive(OUT / f"{phase}.receipt.json", {"exit_code": result.returncode,
        "checked_at": datetime.now(timezone.utc).isoformat(), "command": command,
        "stdout_sha256": sha256_file(OUT / f"{phase}.stdout")})
    if result.returncode:
        raise RuntimeError(f"{phase} failed; inspect preserved evidence before any retry")
    return (OUT / f"{phase}.stdout").read_bytes()


def upload():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_symlink():
                raise ValueError("package symlink forbidden")
            if path.is_file():
                archive.add(path, arcname=path.relative_to(PACKAGE).as_posix(), recursive=False)
    code = '''import json,shutil,socket,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary):raise ValueError('host/root mismatch')
root.mkdir(exist_ok=False);count=0
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe archive')
  target.parent.mkdir(parents=True,exist_ok=True)
  with archive.extractfile(member) as source,target.open('xb') as output:shutil.copyfileobj(source,output)
  count+=1
print(json.dumps({'status':'UPLOADED','files':count}))
'''
    write_json_exclusive(OUT / "upload_reservation.json", {"request_sha256": sha256_file(PACKAGE / "request.json")})
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\n" + code)
    print(call(command, "upload", stream.getvalue(), timeout=120).decode(), flush=True)


def preflight():
    command = f"bash -n {REMOTE}/run.sbatch && "
    command += "env PYTHONDONTWRITEBYTECODE=1 " + "PYTHONPATH=" + shlex.quote(
        f"{REMOTE}:{REMOTE}/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor")
    command += f" /home/sbq/sbq/ml_ts_acceleration/venv/bin/python {REMOTE}/worker.py preflight --request {REMOTE}/request.json --sha256 "
    command += sha256_file(PACKAGE / "request.json")
    print(call(command, "native_preflight", timeout=180).decode(), flush=True)


def submit():
    if load_json_object(OUT / "native_preflight.receipt.json")["exit_code"] != 0:
        raise ValueError("native CPU/input preflight has not passed")
    digest = sha256_file(PACKAGE / "request.json")
    write_json_exclusive(OUT / "submit_reservation.json", {"request_sha256": digest, "VASP_authorized": False})
    code = '''import datetime,json,subprocess
from pathlib import Path
root=Path(ROOT)
with (root/'submission_attempt.json').open('x') as handle:json.dump({'request_sha256':SHA},handle)
p=subprocess.run(['sbatch','--parsable','--job-name=fe12-'+SHA[:10],'--comment='+SHA,'--export=ALL,REQUEST_SHA256='+SHA,str(root/'run.sbatch')],capture_output=True)
with (root/'sbatch.stdout').open('xb') as h:h.write(p.stdout)
with (root/'sbatch.stderr').open('xb') as h:h.write(p.stderr)
raw=p.stdout.decode('utf-8','replace').strip();job=raw.split(';')[0]
record={'request_sha256':SHA,'exit_code':p.returncode,'native_stdout':raw,'job_id':job if job.isdigit() else None,'submitted_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scheduler':'Slurm','VASP_submitted':False}
if p.returncode==0 and job.isdigit():
 q=subprocess.run(['squeue','-h','-j',job,'-o','%i|%T|%R|%S|%N'],capture_output=True,text=True)
 record['queue_snapshot']={'exit_code':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
with (root/'submission_receipt.json').open('x') as h:json.dump(record,h,indent=2)
print(json.dumps(record))
if p.returncode or not job.isdigit():raise SystemExit(3)
'''
    command = "python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\nSHA=" + repr(digest) + "\n" + code)
    raw = call(command, "submit", timeout=55)
    receipt = json.loads(raw)
    write_json_exclusive(OUT / "submission_receipt.json", receipt)
    print(raw.decode(), flush=True)


def status():
    receipt = load_json_object(OUT / "submission_receipt.json")
    job = receipt["job_id"]
    if not job.isdigit():
        raise ValueError("no actual scheduler job id")
    command = "squeue -h -j " + job + " -o '%i|%T|%R|%S|%N'"
    argv = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    result = subprocess.run(["ssh", "-T", "-i", argv["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-p", str(argv["port"]), argv["user"] + "@" + argv["host"], command], capture_output=True, timeout=20)
    print(result.stdout.decode(), end="")
    if result.returncode:
        raise RuntimeError(result.stderr.decode())


def observe():
    job = load_json_object(OUT / "submission_receipt.json")["job_id"]
    if not job.isdigit():
        raise ValueError("no actual scheduler job id")
    code = '''import datetime,json,subprocess
argv=['squeue','--start','-j',JOB,'-h','-o','%i|%T|%R|%S|%N']
q=subprocess.run(argv,capture_output=True,text=True)
print(json.dumps({'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'clock_source':'MZ73','argv':argv,'exit_code':q.returncode,'stdout':q.stdout,'stderr':q.stderr}))
raise SystemExit(q.returncode)
'''
    command = "python3 -c " + shlex.quote("JOB=" + repr(job) + "\n" + code)
    print(call(command, "scheduler_observation").decode(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("upload", "preflight", "submit", "status", "observe"))
    phase = parser.parse_args().phase
    {"upload": upload, "preflight": preflight, "submit": submit, "status": status, "observe": observe}[phase]()
