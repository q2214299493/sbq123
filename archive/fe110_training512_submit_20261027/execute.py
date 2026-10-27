"""Bind,deploy and inspect the one authorized512-frame trial;never auto-retry."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
from pathlib import Path
import shlex
import subprocess
import tarfile

import yaml

from scripts.adsorption.direct_force_training import verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
PREP = BASE / "training512_20261027_v1"
OUTPUT = BASE / "training512_submit_20261027_v1"
PACKAGE = PREP / "package"
REMOTE = "/home/sbq/sbq/fe110_force_training512_20261027_v1"
AUTH = ROOT / "docs/reviews/fe110_training512_submit_20261027/user_authorization.md"
POLICY = ROOT / "configs/execution_backends.yaml"
EXCEPTION = "fe110_force_training512_20261027"
RUN_ID = "direct-fe110-force512-20261027-v1"
ARM_SHA = "fbc1fb2d7b8753e5429db2253559cff5a68669a0f620eebe515f01ad6c1c84e7"


def bind():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (PACKAGE / "direct_request.json").exists():
        raise FileExistsError("preserve existing binding and inspect its receipt")
    prior = load_json_object(PREP / "preparation_receipt.json")
    if not source_file_manifest_valid(prior) or sha256_file(PACKAGE / "control/training_request.json") != ARM_SHA:
        raise ValueError("frozen preparation changed")
    if "> 提交" not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("human authority missing")
    previous = OUTPUT / "previous_execution_backends.yaml"
    with previous.open("xb") as handle:
        handle.write(POLICY.read_bytes())
    write_json_exclusive(OUTPUT / "prebinding_review.json", {"status": "PASS_BEFORE_AUTHORIZED_POLICY_ADDITION",
        "prepared_source_bindings_valid_at_review": True, "arm_request_sha256": ARM_SHA,
        "previous_policy_sha256": sha256_file(previous), "user_authority_sha256": sha256_file(AUTH),
        "source_files": source_file_manifest([previous, AUTH, PREP / "preparation_receipt.json", PACKAGE / "control/training_request.json"])})
    comparison = {"document_kind": "adsorption_bounded_single_training_review", "arms": {"control": {"sha256": ARM_SHA}},
        "base_checkpoint": load_json_object(PACKAGE / "control/training_request.json")["base_checkpoint"],
        "total_GPU_walltime_minutes_cap": 30, "total_optimizer_steps_cap": 1024,
        "whole_family_splits_and_magnetic_levels_unchanged": True, "heldout_evaluation_authorized": False,
        "source_files": source_file_manifest([AUTH, PREP / "validation_plan.json", OUTPUT / "prebinding_review.json"]) }
    write_json_exclusive(PACKAGE / "comparison_request.json", comparison)
    exception = {"authorized_by": "user_explicit_20261027_submit_one_reviewed512_frame_trial", "authorizing_user_request": "提交",
        "scope": "one_uniform_force_only512_frame_candidate", "arms": ["control"], "remote_root": REMOTE,
        "canonical_remote_boundary": "/home/ubuntu/hdd/sbq/sbq", "gpu_index": 1,
        "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da", "execution_mode": "direct_no_scheduler",
        "executor": "scripts/adsorption/direct_force_training.py", "model_backend": "aqcat25_role_force_training",
        "original_comparison_sha256": sha256_file(PACKAGE / "comparison_request.json"), "arm_request_sha256": {"control": ARM_SHA},
        "max_wall_seconds": 1800, "per_arm_wall_seconds": 1800, "max_epochs": 2,
        "max_optimizer_steps_per_arm": 1024, "CPU_count": 4, "memory_GB": 32, "parallel_arms": 1,
        "automatic_retries": 0, "explicit_authorization_required": True, "producer_exit_record_required": True,
        "scheduler_job_id": None, "slurm_id_emulation": "forbidden", "model_promotion_or_vasp_execution": "forbidden",
        "alter_shared_services_or_other_users_jobs": "forbidden"}
    text = POLICY.read_text(encoding="utf-8")
    if EXCEPTION in yaml.safe_load(text)["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("execution exception already exists;inspect before rebinding")
    marker = "    direct_execution_exceptions:\n"
    if text.count(marker) != 1:
        raise ValueError("backend insertion point ambiguous")
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    text = text.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1)
    POLICY.write_text(text, encoding="utf-8", newline="\n")
    (PACKAGE / "execution_backends.yaml").write_bytes(POLICY.read_bytes())
    (PACKAGE / "scope.md").write_bytes(AUTH.read_bytes())
    write_json_exclusive(PACKAGE / "control/direct_arm_authorization.json", {"user_authorized": True,
        "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE", "request_sha256": ARM_SHA, "user_request": "提交",
        "execution_mode": "direct_no_scheduler", "new_VASP_or_promotion_authorized": False,
        "user_authority_sha256": sha256_file(AUTH)})
    request = {"document_kind": "adsorption_direct_force_training_trial", "run_id": RUN_ID, "exception_id": EXCEPTION,
        "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "remote_root": REMOTE, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "gpu_index": 1, "gpu_uuid": exception["gpu_uuid"], "max_wall_seconds": 1800, "per_arm_wall_seconds": 1800,
        "arms": ["control"], "original_comparison_sha256": exception["original_comparison_sha256"],
        "native_two_backward_check": True,
        "artifacts": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)}
                      for p in sorted(PACKAGE.rglob("*")) if p.is_file()]}
    write_json_exclusive(PACKAGE / "direct_request.json", request)
    digest = sha256_file(PACKAGE / "direct_request.json")
    write_json_exclusive(PACKAGE / "direct_authorization.json", {"user_authorized": True,
        "action": "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT", "user_request": "提交", "request_sha256": digest,
        "source_scope_sha256": sha256_file(PACKAGE / "scope.md"), "checkpoint_promotion_authorized": False})
    verify(PACKAGE / "direct_request.json", digest)
    write_json_exclusive(OUTPUT / "binding_receipt.json", {"status": "AUTHORIZED_BOUND_NOT_LAUNCHED",
        "arm_request_sha256": ARM_SHA, "direct_request_sha256": digest, "training_started": False,
        "source_files": source_file_manifest([Path(__file__), AUTH, OUTPUT / "prebinding_review.json",
            PACKAGE / "direct_request.json", PACKAGE / "direct_authorization.json", PACKAGE / "execution_backends.yaml"])})
    print({"status": "AUTHORIZED_BOUND_NOT_LAUNCHED", "direct_request_sha256": digest}, flush=True)


def call(command, name, data=None, timeout=50):
    settings = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    argv = ["ssh", "-i", settings["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=12", "-p", str(settings["port"]), settings["user"] + "@" + settings["host"], command]
    with (OUTPUT / (name + ".stdout")).open("xb") as stdout, (OUTPUT / (name + ".stderr")).open("xb") as stderr:
        result = subprocess.run(argv, input=data, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    write_json_exclusive(OUTPUT / (name + ".receipt.json"), {"returncode": result.returncode, "command": command,
        "checked_at": datetime.now(timezone.utc).isoformat()})
    if result.returncode:
        raise RuntimeError(name + " failed;inspect saved receipt/state before further action")
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
    program = '''import json,shutil,socket,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!='/home/ubuntu/hdd/sbq/sbq' or not root.resolve().is_relative_to(boundary):raise ValueError('host/boundary mismatch')
if root.exists():raise FileExistsError('preserve existing or partial remote package')
if shutil.disk_usage(root.parent).free<3*1024**3:raise RuntimeError('insufficient checkpoint disk')
root.mkdir();count=0
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe archive member')
  target.parent.mkdir(parents=True,exist_ok=True)
  with archive.extractfile(member) as source,target.open('xb') as dest:shutil.copyfileobj(source,dest)
  count+=1
print(json.dumps({'status':'UPLOAD_COMPLETE','files':count,'root':str(root)}))
'''
    write_json_exclusive(OUTPUT / "upload_reservation.json", {"request_sha256": sha, "remote_root": REMOTE})
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\n" + program)
    print(call(command, "upload", stream.getvalue(), timeout=120).decode(), flush=True)


def remote_command(action):
    sha = sha256_file(PACKAGE / "direct_request.json")
    verify(PACKAGE / "direct_request.json", sha)
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    env = "env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONPATH=" + shlex.quote(prefix)
    python = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"
    if action == "cpu-preflight":
        code = """import subprocess
from pathlib import Path
from scripts.adsorption.direct_force_training import verify,arm_environment,make_runtime_directories,arm_command
path=Path(REQUEST);request,root,_=verify(path,SHA,remote=True)
env=arm_environment(root,request,'control');make_runtime_directories(root,env)
subprocess.run(arm_command(path,SHA,'control','preflight'),env=env,cwd=root,stdin=subprocess.DEVNULL,check=True,timeout=300)
print('PASS_NATIVE_CPU_PREFLIGHT_GPU_AVAILABILITY_STILL_REQUIRED',flush=True)
"""
        command = env + " " + python + " -c " + shlex.quote("REQUEST=" + repr(REMOTE + "/direct_request.json") + "\nSHA=" + repr(sha) + "\n" + code)
        print(call(command, "cpu_preflight", timeout=330).decode(), flush=True)
    elif action == "launch":
        write_json_exclusive(OUTPUT / "launch_reservation.json", {"request_sha256": sha, "automatic_retry": False})
        command = env + " " + python + " -m scripts.adsorption.direct_force_training launch --request " + shlex.quote(REMOTE + "/direct_request.json") + " --request-sha256 " + sha
        print(call(command, "launch", timeout=55).decode(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bind", "upload", "cpu-preflight", "launch"])
    args = parser.parse_args()
    if args.action == "bind":
        bind()
    elif args.action == "upload":
        upload()
    else:
        remote_command(args.action)
