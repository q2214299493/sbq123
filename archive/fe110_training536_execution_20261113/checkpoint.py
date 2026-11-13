"""Read one exact Slurm job and preserve its raw scheduler/producer checkpoint."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone

import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .submit import ROOT

OUT = ROOT / "calculations/fe110_reico_pilot300_20261022/training536_execution_20261113_v4"
REMOTE = "/home/sbq/sbq/fe110_force_training536_execution_20261113_v4"

PROGRAM = r'''
import hashlib,json
from pathlib import Path
root=Path(ROOT);output=root/'output'/('job_'+JOB)
records={};hashes={}
for name in ['allocation_preflight.json','execution_device.json','native_two_backward_check.json','training_completed.json','candidate_binding.json','job_exit_record.json']:
 path=output/name
 if path.is_file():
  data=path.read_bytes();record=json.loads(data)
  records[name]={k:v for k,v in record.items() if k not in ['package','native_cli']}
  hashes[name]=hashlib.sha256(data).hexdigest()
log=root/('slurm-'+JOB+'.log');tail=''
if log.is_file():
 with log.open('rb') as handle:handle.seek(max(0,log.stat().st_size-4500));tail=handle.read().decode(errors='replace')
print(json.dumps({'job_id':JOB,'records':records,'record_sha256':hashes,'log_tail':tail}))
'''


def run():
    submission = load_json_object(OUT / "submission_return/submission_receipt.json")
    job = submission["scheduler_job_id"]
    if not job.isdigit():
        raise ValueError("native numeric job ID required")
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-o", "IdentitiesOnly=yes", "-i", ssh["identity_file"], "-p", str(ssh["port"]), "--", ssh["user"] + "@" + ssh["host"]]
    saved = OUT / ("checkpoint_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    saved.mkdir()
    with (saved / "scheduler.stdout").open("xb") as stdout, (saved / "scheduler.stderr").open("xb") as stderr:
        scheduler = subprocess.run([*argv, "scontrol show job -o " + job], stdout=stdout, stderr=stderr, timeout=20)
    program = "ROOT=" + repr(REMOTE) + "\nJOB=" + repr(job) + "\n" + PROGRAM
    with (saved / "producer.stdout").open("xb") as stdout, (saved / "producer.stderr").open("xb") as stderr:
        producer = subprocess.run([*argv, "python3 -B -"], input=program.encode(), stdout=stdout, stderr=stderr, timeout=20)
    fields = {token.split("=", 1)[0]: token.split("=", 1)[1] for token in
              (saved / "scheduler.stdout").read_text(encoding="utf-8").split() if "=" in token}
    write_json_exclusive(saved / "receipt.json", {
        "scheduler_exit_code": scheduler.returncode, "producer_read_exit_code": producer.returncode,
        "scheduler_job_id": job, "source_files": source_file_manifest([saved / n for n in
                                                                       ["scheduler.stdout", "scheduler.stderr", "producer.stdout", "producer.stderr"]])})
    print({key: fields.get(key) for key in ["JobId", "JobState", "Reason", "ExitCode", "RunTime", "TimeLimit", "StartTime", "EndTime"]})
    if producer.returncode == 0:
        progress = load_json_object(saved / "producer.stdout")
        print(progress["records"])
        print(progress["log_tail"][-2500:])
    print({"canonical_checkpoint": str(saved), "scheduler_stdout_sha256": sha256_file(saved / "scheduler.stdout")})


if __name__ == "__main__":
    run()
