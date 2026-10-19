"""Bounded SSH transport; source bytes preserved and all attempts recorded locally."""
import json
import shlex
import subprocess
from pathlib import Path

import yaml

from scripts.artifact_io import write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v1"
PACKAGE = EVIDENCE / "package"
REMOTE = "/home/sbq/sbq/adsorption_training_comparison_20261019_v1"


def call(command, name, data=None, timeout=60):
    backend = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]
    ssh = backend["ssh"]
    argv = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    EVIDENCE.mkdir(exist_ok=True)
    with (EVIDENCE / (name + ".stdout")).open("xb") as stdout, (EVIDENCE / (name + ".stderr")).open("xb") as stderr:
        result = subprocess.run(argv, input=data, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    write_json_exclusive(EVIDENCE / (name + ".receipt.json"), {"exit_code": result.returncode, "command": command})
    if result.returncode:
        raise RuntimeError(name + " failed;inspect preserved result,do not repeat unchanged")
    return (EVIDENCE / (name + ".stdout")).read_bytes()


def probe(name="initial_probe"):
    program = r'''
import json,subprocess
from pathlib import Path
def cmd(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=12,check=False)
 return {'exit_code':r.returncode,'stdout':r.stdout[:6000],'stderr':r.stderr[:2000]}
path=Path('/home/sbq/sbq/aqcat25/vendor/fairchem/core/trainers/ocp_trainer.py')
lines=path.read_text().splitlines()
print(json.dumps({'host':cmd(['hostname']),'root':str(Path('/home/sbq/sbq').resolve()),
 'package_exists':Path(TARGET).exists(),
 'GPUs':cmd(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits']),
 'processes':cmd(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader']),
 'native_train_lines_148_216':'\n'.join(lines[147:216]),'remote_files_written':False}))
'''
    raw = call("env PYTHONDONTWRITEBYTECODE=1 python3 -", name, ("TARGET=" + repr(REMOTE) + "\n" + program).encode())
    print(json.dumps(json.loads(raw)))


def remote_module(action, sha):
    prefix = REMOTE + "/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    command = "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=" + shlex.quote(prefix)
    command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -m scripts.adsorption.direct_force_training "
    command += action + " --request " + shlex.quote(REMOTE + "/direct_request.json") + " --request-sha256 " + sha
    return call(command, action, timeout=660 if action == "preflight" else 60)


if __name__ == "__main__":
    probe()
