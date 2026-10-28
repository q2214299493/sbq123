"""Read-only native package/GPU inventory before a separate training proposal."""
from datetime import datetime, timezone
from pathlib import Path
import base64
import json
import shlex
import subprocess

import yaml

from scripts.artifact_io import write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "calculations/fe110_reico_pilot300_20261022/scratch512_20261028_v1"
PYTHON = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"
PROGRAM = '''import importlib.metadata as m,importlib.util,json,socket,subprocess,sys
from pathlib import Path
result={'hostname':socket.gethostname(),'python':sys.executable,'python_version':sys.version,'packages':{}}
for name in ['torch','ase','nequip','e3nn','lightning','pytorch-lightning','hydra-core','omegaconf','torchmetrics']:
 try:result['packages'][name]=m.version(name)
 except m.PackageNotFoundError:result['packages'][name]=None
for name,args in {'gpus':['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu','--format=csv,noheader'],
 'compute_processes':['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader']}.items():
 p=subprocess.run(args,capture_output=True,text=True,timeout=15)
 result[name]={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
result['allowed_write_boundary_resolved']=str(Path('/home/sbq/sbq').resolve())
print(json.dumps(result),flush=True)
'''


def probe():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    policy = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))
    ssh = policy["backends"]["aqcat_gpu"]["ssh"]
    command = shlex.join([PYTHON, "-c", "exec(__import__('base64').b64decode('" + base64.b64encode(PROGRAM.encode()).decode() + "'))"])
    args = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUTPUT / "native_probe.stdout").open("xb") as stdout, (OUTPUT / "native_probe.stderr").open("xb") as stderr:
        try:
            result = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=55, check=False)
            status = {"returncode": result.returncode}
        except subprocess.TimeoutExpired:
            status = {"returncode": None, "timeout_seconds": 55}
    status.update(checked_at=datetime.now(timezone.utc).isoformat(), remote_writes=False, GPU_model_execution=False)
    write_json_exclusive(OUTPUT / "native_probe_receipt.json", status)
    if status["returncode"] != 0:
        raise RuntimeError("read-only native probe failed;inspect retained receipt")
    payload = json.loads((OUTPUT / "native_probe.stdout").read_bytes())
    write_json_exclusive(OUTPUT / "native_probe.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    probe()
