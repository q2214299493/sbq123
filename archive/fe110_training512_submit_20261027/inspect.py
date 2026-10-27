"""Capture bounded native preflight,resource and producer evidence;never launch."""
from __future__ import annotations

import argparse
import json
import re
import shlex

from scripts.artifact_io import sha256_file, source_file_manifest, write_json_exclusive
from .execute import OUTPUT, PACKAGE, REMOTE, RUN_ID, call


def inspect(name):
    if not re.fullmatch(r"status_[a-z0-9_]+", name):
        raise ValueError("unsafe or ambiguous checkpoint name")
    digest = sha256_file(PACKAGE / "direct_request.json")
    program = '''import json,subprocess,re
from pathlib import Path
from scripts.adsorption.direct_force_training import verify
from scripts.adsorption.direct_gpu_batch import gpu_available
request,root,_=verify(Path(REQUEST),SHA,remote=True)
result={'request_sha256':SHA,'records':{}}
for name in ['preflight_control.json','direct_launch_marker.json','direct_launch_receipt.json','direct_started.json','direct_batch_exit_record.json']:
 p=root/name
 if p.is_file():result['records'][name]=json.loads(p.read_text())
directory=root/'control/output'/RUN_ID
result['producer']={}
for name in ['started.json','execution_device.json','native_two_backward_check.json','training_completed.json','producer_exit_record.json']:
 p=directory/name
 if p.is_file():result['producer'][name]=json.loads(p.read_text())
log=directory/'training.log'
if log.is_file():
 with log.open('rb') as f:
  f.seek(max(0,log.stat().st_size-4000));tail=f.read(4000).decode(errors='replace')
 steps=re.findall(r'\\bstep:\\s*([0-9.eE+\\-]+)',tail)
 result['latest_logged_step']=int(float(steps[-1])) if steps else None
 if 'Traceback' in tail:result['error_tail']=tail[-2000:]
result['GPU_processes']=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader'],timeout=12).decode()[:4000]
try:
 gpu_available(request);result['native_GPU_start_check']={'passed':True}
except ValueError as exc:result['native_GPU_start_check']={'passed':False,'reason':str(exc)}
result['scientific_acceptance']=False
print(json.dumps(result),flush=True)
'''
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    source = "REQUEST=" + repr(REMOTE + "/direct_request.json") + "\nSHA=" + repr(digest) + "\nRUN_ID=" + repr(RUN_ID) + "\n" + program
    command = "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=" + shlex.quote(prefix) + " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -c " + shlex.quote(source)
    data = json.loads(call(command, name, timeout=55))
    data["source_files"] = source_file_manifest([OUTPUT / (name + ".stdout"), OUTPUT / (name + ".receipt.json"), PACKAGE / "direct_request.json"])
    write_json_exclusive(OUTPUT / (name + ".json"), data)
    print({k: v for k, v in data.items() if k not in ["source_files", "GPU_processes"]}, flush=True)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    inspect(parser.parse_args().snapshot)
