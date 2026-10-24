"""Read-only exact-scope and remote headroom checks before resumed submissions."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import subprocess

from archive.fe110_reico_sampling93_20261022 import inspect_submission_limit as diagnostic
from archive.fe110_reico_sampling93_20261022 import submit as original
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.submission import SUBMISSION_ATTEMPT_FILE, submission_status

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT/"calculations/fe110_reico_pilot300_20261022/remaining_submission_20261024_v1"


def scope():
    ready = original.checked_ready()
    eligible, unknown, successful = [], [], []
    for row in ready:
        state = submission_status(original.DEST/row["sample_id"])
        if state["status"] == "NOT_RESERVED":
            eligible.append(row)
        elif state["status"] == "SUBMITTED":
            successful.append({"sample_id":row["sample_id"], **state})
        else:
            attempt = load_json_object(original.DEST/row["sample_id"]/SUBMISSION_ATTEMPT_FILE)
            unknown.append({**row, "attempt":attempt})
    return eligible, unknown, successful


def main():
    if (OUTPUT/"remote_check.json").exists():
        raise ValueError("preserve completed remote checkpoint; use its evidence or a fresh directory")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    eligible, unknown, successful = scope()
    payload = {"affected":[{"sample_id":r["sample_id"], "remote_dir":r["attempt"]["remote_dir"],
                    "reservation_id":r["attempt"]["reservation_id"], "potcar_sha256":r["potcar_sha256"],
                    "files":load_json_object(original.DEST/r["sample_id"]/"submission_preflight.json")["files"]} for r in unknown],
               "receipted_ids":[r["job_id"] for r in successful]}
    code = "import json,os,subprocess,hashlib\n"+inspect.getsource(diagnostic.command)+"\n"+inspect.getsource(diagnostic.inspect)
    code += "\npayload=json.loads("+repr(json.dumps(payload))+ ")\nresult=inspect(payload)\n"
    code += "result['user']=command(['whoami']);result['account_resource_query']=command(['busers','-w'])\n"
    code += "result['runtime']={'VASP_executable':os.access(os.path.expanduser('~/soft/vasp541vtst/bin/vasp_std'),os.X_OK),'intel_environment_exists':os.path.isfile('/home_gkx/env/intel/intel2016.sh')}\n"
    code += "result['POTCARs']={}\n"
    code += "for path in "+repr(sorted({r["potcar_source"] for r in eligible+unknown}))+":\n result['POTCARs'][path]=subprocess.check_output(['sha256sum',os.path.expanduser(path)]).decode().split()[0]\n"
    targets = [{"sample_id":r["sample_id"],"remote_dir":original.REMOTE+"/"+r["sample_id"]} for r in eligible]
    code += "result['new_targets']=[]\nfor row in "+repr(targets)+":\n d=os.path.expanduser(row['remote_dir']); result['new_targets'].append(dict(row,directory_exists=os.path.lexists(d),lock_exists=os.path.lexists(d+'.submission-reservation')))\n"
    code += "print(json.dumps(result))\n"
    with (OUTPUT/"remote_reader.py").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(code)
    argv=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=15",original.HOST,"python3 -"]
    result = subprocess.run(argv,input=code,capture_output=True,text=True,timeout=120,check=False)
    record = {"checked_at":datetime.now(timezone.utc).isoformat(),"command":argv,"returncode":result.returncode,
              "stdout":result.stdout,"stderr":result.stderr,"reader_sha256":sha256_file(OUTPUT/"remote_reader.py"),
              "source_files":source_file_manifest([Path(__file__), original.DEST/"batch_request.json", original.DEST/"ready_for_submission.json"])}
    write_json_exclusive(OUTPUT/"remote_check.json",record)
    if result.returncode:
        raise RuntimeError("read-only remote preflight failed: "+result.stderr[:1000])
    parsed=json.loads(result.stdout)
    write_json_exclusive(OUTPUT/"remote_check_parsed.json",parsed)
    write_json_exclusive(OUTPUT/"initial_scope.json",{"eligible":eligible,"unknown":unknown,"successful":successful,
        "batch_sha256":original.BATCH_SHA,"counts":{"eligible":len(eligible),"unknown":len(unknown),"submitted":len(successful)}})
    statuses=Counter(line.split()[2] for line in parsed["all_account_bjobs"]["stdout"].splitlines()
                     if line.split() and line.split()[0].isdigit())
    print({"eligible":len(eligible),"unknown":len(unknown),"account_jobs":dict(statuses),
           "resources":parsed["account_resource_query"],"unmatched_recent":parsed["unmatched_recent_job_ids"],
           "target_conflicts":sum(r["directory_exists"] or r["lock_exists"] for r in parsed["new_targets"])})


if __name__ == "__main__":
    main()
