"""Correct a zero-training bootstrap failure; preflight before the single trial."""
from __future__ import annotations

import io
import shlex
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .entry import validate_contract
from .submit import ARM, ROOT

OUT = ROOT / "calculations/fe110_reico_pilot300_20261022/training536_execution_20261113_v4"
PREVIOUS = OUT.with_name("training536_execution_20261113_v1")
REMOTE = "/home/sbq/sbq/fe110_force_training536_execution_20261113_v4"
PACKAGE = "/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control"

PROGRAM = r'''
import hashlib,json,os,re,socket,subprocess,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!='/home/ubuntu/hdd/sbq/sbq' or not root.resolve().is_relative_to(boundary):raise ValueError('exact observed canonical boundary changed')
if root.exists():raise FileExistsError('preserve previous preparation/submission')
root.mkdir();seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or member.name not in FILES or member.name in seen or not target.is_relative_to(root.resolve()):raise ValueError('unbound archive member')
  data=archive.extractfile(member).read()
  if len(data)!=FILES[member.name]['bytes'] or hashlib.sha256(data).hexdigest()!=FILES[member.name]['sha256']:raise ValueError('staging hash mismatch')
  with target.open('xb') as handle:handle.write(data)
  seen.add(member.name)
if seen!=set(FILES):raise ValueError('incomplete staging')
def write(name,payload):
 with (root/name).open('x') as handle:json.dump(payload,handle,indent=2)
write('staging_receipt.json',{'files':FILES,'training_data_copied':False})
check=subprocess.run(['bash','-n',str(root/'job.sh')],capture_output=True)
write('shell_syntax_receipt.json',{'exit_code':check.returncode})
if check.returncode:raise RuntimeError('shell syntax check failed')
env=os.environ.copy();env['EXEC_CONTRACT_SHA']=CONTRACT_SHA
with (root/'environment_preflight.stdout').open('xb') as stdout,(root/'environment_preflight.stderr').open('xb') as stderr:
 check=subprocess.run(['bash',str(root/'job.sh'),'--environment-preflight-only'],env=env,stdout=stdout,stderr=stderr,timeout=180)
write('environment_preflight_receipt.json',{'exit_code':check.returncode,'CUDA_visible_devices':'-1','training_started':False,'GPU_allocation':False,'sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['environment_preflight.stdout','environment_preflight.stderr']}})
if check.returncode:raise RuntimeError('CPU namespace/path/package preflight failed; no scheduler submission')
args=['sbatch','--parsable','--export=EXEC_CONTRACT_SHA='+CONTRACT_SHA,'--chdir='+str(root),'--output='+str(root/'slurm-%j.log'),'--error='+str(root/'slurm-%j.log'),str(root/'job.sh')]
write('submission_reservation.json',{'argv':args,'automatic_training_retry':False,'previous_preflight_job':'14496','previous_training_started':False})
result=subprocess.run(args,capture_output=True)
for name,data in [('sbatch.stdout',result.stdout),('sbatch.stderr',result.stderr)]:
 with (root/name).open('xb') as handle:handle.write(data)
job=result.stdout.decode().strip().split(';')[0] if result.returncode==0 else None
if job is not None and not re.fullmatch(r'[0-9]+',job):job=None
write('submission_receipt.json',{'sbatch_exit_code':result.returncode,'scheduler_job_id':job,'execution_contract_sha256':CONTRACT_SHA,'training_starts_only_after_allocation_preflight':True,'previous_preflight_job':'14496','previous_training_started':False,'new_DFT':False})
print(json.dumps({'sbatch_exit_code':result.returncode,'scheduler_job_id':job}),flush=True)
if result.returncode or not job:raise RuntimeError('inspect receipts; no automatic resubmission')
'''


def run():
    if OUT.exists():
        raise FileExistsError("preserve existing v4 evidence; inspect before any further action")
    context = load_json_object(PREVIOUS / "request_context.json")
    if sha256_file(ARM / "training_request.json") != context["training536_request_sha256"]:
        raise ValueError("frozen request changed")
    OUT.mkdir()
    stage = OUT / "executor"
    stage.mkdir()
    for target, source in [("entry.py", Path(__file__).with_name("entry.py")),
                           ("job.sh", Path(__file__).with_name("job_v4.sh")),
                           ("execution_backends.yaml", ROOT / "configs/execution_backends.yaml")]:
        with (stage / target).open("xb") as handle:
            handle.write(source.read_bytes())
    approval = {"user_authorized": True, "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE",
                "request_sha256": context["training536_request_sha256"], "user_request": context["user_instruction"],
                "source": "same explicit user instruction; no previous model training started"}
    write_json_exclusive(stage / "training_authorization.json", approval)
    contract = {"user_instruction": context["user_instruction"], "package_root": PACKAGE,
                "training_request_sha256": context["training536_request_sha256"], "execution_mode": "Slurm",
                "scheduler_seconds": 1740, "scheduler_killwait_seconds": 30,
                "watchdog_seconds": 1700, "watchdog_kill_after_seconds": 10,
                "canonical_remote_boundary_observed": "/home/ubuntu/hdd/sbq/sbq",
                "previous_preflight_job": "14496", "previous_allocated_seconds": 10,
                "previous_training_started": False, "training_retry_allowed": False,
                "new_DFT": False, "frozen_original_data_untouched": True,
                "execution_files": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(stage.iterdir())]}
    if contract["previous_allocated_seconds"] + contract["scheduler_seconds"] + contract["scheduler_killwait_seconds"] > 1800:
        raise ValueError("cumulative allocated GPU walltime could exceed user budget")
    validate_contract(contract, load_json_object(ARM / "training_request.json"),
                      yaml.safe_load((ARM / "config.yml").read_text(encoding="utf-8")), approval)
    write_json_exclusive(stage / "execution_contract.json", contract)
    contract_sha = sha256_file(stage / "execution_contract.json")
    files = {p.name: {"sha256": sha256_file(p), "bytes": p.stat().st_size} for p in stage.iterdir()}
    write_json_exclusive(OUT / "preparation_receipt.json", {
        "status": "CORRECTED_BOOTSTRAP_SCOPE_NO_TRAINING_RETRY", "execution_contract_sha256": contract_sha,
        "source_files": source_file_manifest([Path(__file__), *stage.iterdir(), PREVIOUS / "request_context.json"])})
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name in files:
            archive.add(stage / name, arcname=name, recursive=False)
    program = ("ROOT=" + repr(REMOTE) + "\nFILES=" + repr(files) + "\nCONTRACT_SHA=" + repr(contract_sha) + "\n" + PROGRAM).encode()
    bootstrap = "import sys;n=int(sys.stdin.buffer.readline());exec(compile(sys.stdin.buffer.read(n),'<536-corrected-slurm-bootstrap>','exec'))"
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    options = ["-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=12"]
    destination = ssh["user"] + "@" + ssh["host"]
    write_json_exclusive(OUT / "submission_reservation.json", {"created_at": datetime.now(timezone.utc).isoformat(),
                                                              "execution_contract_sha256": contract_sha, "training_retry_allowed": False})
    with (OUT / "transport.stdout").open("xb") as stdout, (OUT / "transport.stderr").open("xb") as stderr:
        result = subprocess.run(["ssh", "-T", *options, "-p", str(ssh["port"]), destination,
                                 "python3 -B -c " + shlex.quote(bootstrap)],
                                input=str(len(program)).encode() + b"\n" + program + stream.getvalue(),
                                stdout=stdout, stderr=stderr, timeout=240)
    write_json_exclusive(OUT / "transport_receipt.json", {"exit_code": result.returncode})
    returned = OUT / "submission_return"
    returned.mkdir()
    names = ["submission_receipt.json", "submission_reservation.json", "staging_receipt.json", "shell_syntax_receipt.json", "environment_preflight_receipt.json", "environment_preflight.stdout", "environment_preflight.stderr", "sbatch.stdout", "sbatch.stderr"]
    copied = subprocess.run(["scp", "-q", *options, "-P", str(ssh["port"]),
                             *[destination + ":" + REMOTE + "/" + n for n in names], str(returned)],
                            capture_output=True, timeout=30)
    write_json_exclusive(OUT / "receipt_return.json", {"exit_code": copied.returncode, "source_files": source_file_manifest(list(returned.iterdir()))})
    if copied.returncode or result.returncode:
        raise RuntimeError("inspect preserved receipts; no automatic retry")
    receipt = load_json_object(returned / "submission_receipt.json")
    if receipt["execution_contract_sha256"] != contract_sha:
        raise ValueError("submission binding changed")
    print(receipt)


if __name__ == "__main__":
    run()
