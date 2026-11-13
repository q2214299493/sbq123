"""Stage only new executor files and submit one conditional Slurm trial once."""
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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_reico_pilot300_20261022/training536_execution_20261113_v1"
ARM = ROOT / "calculations/fe110_reico_pilot300_20261022/training536_smoke_20261113_v1/package/control"
REMOTE = "/home/sbq/sbq/fe110_force_training536_execution_20261113_v1"
PACKAGE = "/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control"

PROGRAM = r'''
import hashlib,json,re,shlex,socket,subprocess,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(boundary):raise ValueError('host/write boundary changed')
if root.exists():raise FileExistsError('preserve previous staging/submission; never retry blindly')
root.mkdir();seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or member.name not in FILES or member.name in seen or not target.is_relative_to(root.resolve()):raise ValueError('unbound/unsafe member')
  data=archive.extractfile(member).read()
  if len(data)!=FILES[member.name]['bytes'] or hashlib.sha256(data).hexdigest()!=FILES[member.name]['sha256']:raise ValueError('staged bytes changed')
  with target.open('xb') as handle:handle.write(data)
  seen.add(member.name)
if seen!=set(FILES):raise ValueError('incomplete staging')
def write(name,value):
 with (root/name).open('x') as handle:json.dump(value,handle,indent=2)
write('staging_receipt.json',{'files':FILES,'training_data_copied':False,'scheduler_submission_attempts':0})
check=subprocess.run(['bash','-n',str(root/'job.sh')],capture_output=True)
write('shell_syntax_receipt.json',{'exit_code':check.returncode})
if check.returncode:raise RuntimeError('new shell entry syntax failed before submission')
contract=json.loads((root/'execution_contract.json').read_text())
if hashlib.sha256(Path(contract['package_root'],'training_request.json').read_bytes()).hexdigest()!=contract['training_request_sha256']:raise ValueError('remote prepared request changed')
args=['sbatch','--parsable','--export=EXEC_CONTRACT_SHA='+CONTRACT_SHA,'--chdir='+str(root),'--output='+str(root/'slurm-%j.log'),'--error='+str(root/'slurm-%j.log'),str(root/'job.sh')]
write('submission_reservation.json',{'argv':args,'automatic_retry':False,'execution_contract_sha256':CONTRACT_SHA})
result=subprocess.run(args,capture_output=True)
with (root/'sbatch.stdout').open('xb') as handle:handle.write(result.stdout)
with (root/'sbatch.stderr').open('xb') as handle:handle.write(result.stderr)
text=result.stdout.decode().strip();job=text.split(';')[0] if result.returncode==0 else None
if job is not None and not re.fullmatch(r'[0-9]+',job):job=None
write('submission_receipt.json',{'sbatch_exit_code':result.returncode,'scheduler_job_id':job,'execution_contract_sha256':CONTRACT_SHA,'training_request_sha256':contract['training_request_sha256'],'native_submission_attempts':1,'training_starts_only_after_allocation_preflight':True,'new_DFT':False})
print(json.dumps({'sbatch_exit_code':result.returncode,'scheduler_job_id':job}),flush=True)
if result.returncode or job is None:raise RuntimeError('submission result requires receipt review; no retry')
'''


def run():
    if (OUT / "submission_reservation.json").exists():
        raise FileExistsError("existing submission reservation; inspect rather than repeat")
    context = load_json_object(OUT / "request_context.json")
    request_sha = sha256_file(ARM / "training_request.json")
    if request_sha != context["training536_request_sha256"]:
        raise ValueError("prepared request changed")
    stage = OUT / "executor"
    stage.mkdir()
    for name in ("entry.py", "job.sh"):
        with (stage / name).open("xb") as handle:
            handle.write(Path(__file__).with_name(name).read_bytes())
    with (stage / "execution_backends.yaml").open("xb") as handle:
        handle.write((ROOT / "configs/execution_backends.yaml").read_bytes())
    instruction = context["user_instruction"]
    approval = {"user_authorized": True, "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE",
                "request_sha256": request_sha, "user_request": instruction,
                "source": "explicit current user instruction", "automatic_retries": 0}
    write_json_exclusive(stage / "training_authorization.json", approval)
    contract = {"user_instruction": instruction, "package_root": PACKAGE, "training_request_sha256": request_sha,
                "execution_mode": "Slurm", "GPU_count": 1, "GPU_binding": "native scheduler assignment; verify UUID before training",
                "scheduler_seconds": 1740, "scheduler_killwait_seconds": 30,
                "watchdog_seconds": 1700, "watchdog_kill_after_seconds": 10,
                "frozen_original_data_untouched": True, "new_DFT": False,
                "execution_files": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(stage.iterdir())]}
    validate_contract(contract, load_json_object(ARM / "training_request.json"),
                      yaml.safe_load((ARM / "config.yml").read_text(encoding="utf-8")), approval)
    write_json_exclusive(stage / "execution_contract.json", contract)
    inventory = {p.name: {"bytes": p.stat().st_size, "sha256": sha256_file(p)} for p in stage.iterdir()}
    contract_sha = sha256_file(stage / "execution_contract.json")
    write_json_exclusive(OUT / "execution_preparation_receipt.json", {
        "status": "PASS_LOCAL_EXACT_SCOPE", "execution_contract_sha256": contract_sha,
        "training_request_sha256": request_sha, "deployment_files": inventory,
        "source_files": source_file_manifest([Path(__file__), *stage.iterdir()])})
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w") as archive:
        for name in inventory:
            archive.add(stage / name, arcname=name, recursive=False)
    program = ("ROOT=" + repr(REMOTE) + "\nFILES=" + repr(inventory)
               + "\nCONTRACT_SHA=" + repr(contract_sha) + "\n" + PROGRAM).encode()
    bootstrap = "import sys;n=int(sys.stdin.buffer.readline());exec(compile(sys.stdin.buffer.read(n),'<536-native-slurm-executor>','exec'))"
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    options = ["-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=12"]
    destination = ssh["user"] + "@" + ssh["host"]
    write_json_exclusive(OUT / "submission_reservation.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "remote_root": REMOTE,
        "execution_contract_sha256": contract_sha, "automatic_retry": False})
    with (OUT / "submission_transport.stdout").open("xb") as stdout, (OUT / "submission_transport.stderr").open("xb") as stderr:
        result = subprocess.run(["ssh", "-T", *options, "-p", str(ssh["port"]), destination,
                                 "python3 -B -c " + shlex.quote(bootstrap)],
                                input=str(len(program)).encode() + b"\n" + program + archive_bytes.getvalue(),
                                stdout=stdout, stderr=stderr, timeout=60)
    write_json_exclusive(OUT / "submission_transport_receipt.json", {"exit_code": result.returncode})
    # Return canonical receipt bytes even if the transport reported an error.
    returned = OUT / "submission_return"
    returned.mkdir()
    names = ["submission_receipt.json", "submission_reservation.json", "staging_receipt.json", "shell_syntax_receipt.json", "sbatch.stdout", "sbatch.stderr"]
    receive = subprocess.run(["scp", "-q", *options, "-P", str(ssh["port"]),
                              *[destination + ":" + REMOTE + "/" + n for n in names], str(returned)],
                             capture_output=True, timeout=30)
    write_json_exclusive(OUT / "submission_receipt_return.json", {"exit_code": receive.returncode,
                                                                 "returned_files": source_file_manifest(list(returned.iterdir()))})
    if receive.returncode or result.returncode:
        raise RuntimeError("inspect submission receipts/state before any further action; no automatic retry")
    receipt = load_json_object(returned / "submission_receipt.json")
    if receipt["execution_contract_sha256"] != contract_sha or not receipt["scheduler_job_id"]:
        raise ValueError("native submission binding failed")
    print(receipt)


if __name__ == "__main__":
    run()
