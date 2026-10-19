"""Read deployed training cadence/CLI sources without importing a model or writing remotely."""
import json
import subprocess
from pathlib import Path

from scripts.artifact_io import write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_comparison_20261019_v1"
REMOTE = r'''
import hashlib,json
from pathlib import Path
root=Path('/home/sbq/sbq/aqcat25/vendor/fairchem/core')
result=[]
for name in ('trainers/ocp_trainer.py','common/flags.py','_cli.py'):
 p=root/name; raw=p.read_bytes(); lines=raw.decode().splitlines()
 hits=[i for i,line in enumerate(lines) if any(k in line for k in ('eval_every','checkpoint_every','best_val_metric','max_epochs','config-yml','world-size'))]
 result.append({'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),
  'excerpts':[{'line':i+1,'source':'\n'.join(lines[max(0,i-2):i+5])} for i in hits]})
print(json.dumps({'sources':result,'model_loaded':False,'remote_files_written':False}))
'''


def main():
    OUTPUT.mkdir(exist_ok=False)
    with (OUTPUT / "native_cadence.json").open("xb") as stdout, (OUTPUT / "native_cadence.stderr.txt").open("xb") as stderr:
        result = subprocess.run(["ssh", "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-p", "36039", "sbq@10sx4jr711576.vicp.fun",
            "env PYTHONDONTWRITEBYTECODE=1 python3 -"], input=REMOTE.encode(), stdout=stdout, stderr=stderr, timeout=45, check=False)
    write_json_exclusive(OUTPUT / "native_cadence_receipt.json", {"exit_code": result.returncode,
        "model_loaded": False, "GPU_used": False, "remote_files_written": False})
    if result.returncode:
        raise RuntimeError("read-only interface capture failed; preserved output requires inspection")
    data = json.loads((OUTPUT / "native_cadence.json").read_text())
    print(json.dumps(data))


if __name__ == "__main__":
    main()
