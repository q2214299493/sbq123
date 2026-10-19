"""Exact reviewed comparison authorization and read-only preflight; no fallback execution."""
import argparse
import json
import subprocess
from datetime import datetime, timezone

import yaml

from scripts.artifact_io import sha256_file, write_json_exclusive

from .prepare import OUTPUT, REMOTE, ROOT

EXPECTED = "f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987"
ARMS = {"control": "dbad960b964805277333d21bce0a1669e38085c9ab742f5ed53a88a9a5b2d026",
        "treatment": "8b740e698d2bac32bb9f918012372a1aaf4e410d9bfef61397bb55ce95ab69ca"}
EVIDENCE = OUTPUT.parent / "adsorption_training_execution_20261019_v1"
PROBE = r'''
import hashlib,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
def command(args):
 try:
  r=subprocess.run(args,capture_output=True,text=True,timeout=12,check=False)
  return {'argv':args,'exit_code':r.returncode,'stdout':r.stdout[:6000],'stderr':r.stderr[:2000]}
 except (OSError,subprocess.TimeoutExpired) as error:
  return {'argv':args,'exit_code':None,'error':str(error)[:1000]}
root=Path('/home/sbq/sbq')
checkpoint=Path('/home/sbq/sbq/aqcat25/demo_single/model.pt')
hasher=hashlib.sha256()
with checkpoint.open('rb') as handle:
 for data in iter(lambda:handle.read(1048576),b''):hasher.update(data)
commands={
 'hostname':command(['hostname']),
 'services':command(['systemctl','is-active','slurmctld','slurmd']),
 'sinfo':command(['sinfo','--noheader','--format=%P|%a|%D|%t|%G']),
 'squeue':command(['squeue','--user=sbq','--noheader','--format=%i|%T|%j']),
 'GPUs':command(['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu','--format=csv,noheader'])}
result={'observed_at':datetime.now(timezone.utc).isoformat(),'commands':commands,
 'sbatch_path':shutil.which('sbatch'),'declared_write_boundary':str(root),'canonical_write_boundary':str(root.resolve()),
 'frozen_helper_boundary_compatible':str(root.resolve())==str(root),
 'target_package_exists':Path(TARGET).exists(),'checkpoint_sha256':hasher.hexdigest(),
 'checkpoint_bytes':checkpoint.stat().st_size,'remote_files_written':False,'training_or_inference_run':False}
result['scheduler_available']=bool(result['sbatch_path']) and all(commands[k]['exit_code']==0 for k in ('sinfo','squeue'))
print(json.dumps(result))
'''


def checked_request():
    path = OUTPUT / "comparison_request.json"
    if sha256_file(path) != EXPECTED:
        raise ValueError("reviewed comparison changed")
    document = json.loads(path.read_text(encoding="utf-8"))
    for arm, sha in ARMS.items():
        request_path = OUTPUT / arm / "training_request.json"
        if sha256_file(request_path) != sha or document["arms"][arm]["sha256"] != sha:
            raise ValueError("reviewed arm changed")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        for item in request["artifacts"]:
            if sha256_file(request_path.parent / item["path"]) != item["sha256"]:
                raise ValueError("bound artifact changed: " + item["path"])
    return document


def authorize():
    checked_request()
    EVIDENCE.mkdir(exist_ok=False)
    now = datetime.now(timezone.utc).isoformat()
    approval = {"document_kind": "user_authorized_adsorption_training_comparison",
        "authorizing_user_request": "运行", "observed_at": now, "user_authorized": True,
        "comparison_request_sha256": EXPECTED, "arm_request_sha256": ARMS,
        "scope": "deploy/preflight and sequential control then treatment under reviewed Slurm package",
        "max_concurrent_GPUs": 1, "total_GPU_walltime_minutes_cap": 60,
        "per_arm_optimizer_steps_cap": 496, "per_arm_epochs_cap": 2,
        "direct_execution_authorized": False, "automatic_retry_authorized": False,
        "VASP_or_model_promotion_authorized": False}
    path = EVIDENCE / "comparison_authorization.json"
    write_json_exclusive(path, approval)
    for arm, sha in ARMS.items():
        write_json_exclusive(EVIDENCE / f"{arm}_authorization.json", {"user_authorized": True,
            "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE", "request_sha256": sha,
            "comparison_authorization_sha256": sha256_file(path), "authorizing_user_request": "运行",
            "observed_at": now, "arm": arm, "execution_mode": "Slurm_sequential_only"})
    print(json.dumps({"status": "EXACT_REQUESTS_AUTHORIZED_NOT_SUBMITTED", "comparison_sha256": EXPECTED}))


def probe():
    checked_request()
    approval = json.loads((EVIDENCE / "comparison_authorization.json").read_text(encoding="utf-8"))
    if not approval["user_authorized"] or approval["comparison_request_sha256"] != EXPECTED:
        raise ValueError("missing exact comparison authorization")
    backend = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]
    ssh = backend["ssh"]
    command = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15", "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"],
        "env PYTHONDONTWRITEBYTECODE=1 python3 -"]
    with (EVIDENCE / "live_preflight.json").open("xb") as stdout, (EVIDENCE / "live_preflight.stderr.txt").open("xb") as stderr:
        result = subprocess.run(command, input=("TARGET=" + repr(REMOTE) + "\n" + PROBE).encode(),
                                stdout=stdout, stderr=stderr, timeout=75, check=False)
    write_json_exclusive(EVIDENCE / "live_preflight_receipt.json", {"ssh_exit_code": result.returncode,
        "remote_files_written": False, "training_or_inference_run": False, "GPU_submission_attempted": False})
    if result.returncode:
        raise RuntimeError("read-only preflight failed;inspect receipt before retry")
    data = json.loads((EVIDENCE / "live_preflight.json").read_text(encoding="utf-8"))
    print(json.dumps(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("authorize", "probe"))
    action = parser.parse_args().action
    (authorize if action == "authorize" else probe)()


if __name__ == "__main__":
    main()
