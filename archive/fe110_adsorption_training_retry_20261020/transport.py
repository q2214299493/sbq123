"""One repaired attempt;bounded transport with exclusive local receipts."""
import shlex
import subprocess
from pathlib import Path

import yaml

from scripts.artifact_io import write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v2"
PACKAGE = EVIDENCE / "package"
REMOTE = "/home/sbq/sbq/adsorption_training_comparison_20261020_v2"
RUN_ID = "direct-adsorption-role-ab-20261020-v2"
EXCEPTION = "fe110_adsorption_role_training_retry_20261020"


def call(command, name, data=None, timeout=60):
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    argv = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    EVIDENCE.mkdir(exist_ok=True)
    with (EVIDENCE / (name + ".stdout")).open("xb") as stdout, (EVIDENCE / (name + ".stderr")).open("xb") as stderr:
        result = subprocess.run(argv, input=data, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    write_json_exclusive(EVIDENCE / (name + ".receipt.json"), {"exit_code": result.returncode, "command": command})
    if result.returncode:
        raise RuntimeError(name + " failed;inspect receipt before any further action")
    return (EVIDENCE / (name + ".stdout")).read_bytes()


def remote_module(action, sha):
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    command = "env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONPATH=" + shlex.quote(prefix)
    command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -m scripts.adsorption.direct_force_training "
    command += action + " --request " + shlex.quote(REMOTE + "/direct_request.json") + " --request-sha256 " + sha
    return call(command, action, timeout=660 if action == "preflight" else 60)


def probe():
    program = r'''
import json,subprocess,socket
from pathlib import Path
def cmd(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=12,check=False)
 return {'exit_code':r.returncode,'stdout':r.stdout[:3000],'stderr':r.stderr[:1000]}
root=Path(ROOT)
print(json.dumps({'host':socket.gethostname(),'canonical_boundary':str(Path('/home/sbq/sbq').resolve()),
 'new_root_exists':root.exists(),
 'old_exit':json.loads(Path('/home/sbq/sbq/adsorption_training_comparison_20261019_v1/direct_batch_exit_record.json').read_text()),
 'GPUs':cmd(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits']),
 'processes':cmd(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader']),
 'native_backward_override':[(str(p),[s for s in p.read_text().splitlines() if 'def _backward' in s]) for p in
 [Path('/home/sbq/sbq/aqcat25/vendor/fairchem/core/models/equiformer_v2/trainers/forces_trainer.py')]],
 'remote_files_written':False}))
'''
    raw = call("env PYTHONDONTWRITEBYTECODE=1 python3 -", "probe", ("ROOT=" + repr(REMOTE) + "\n" + program).encode())
    print(raw.decode())


if __name__ == "__main__":
    probe()
