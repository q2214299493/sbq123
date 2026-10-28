"""Reuse successful CPU runs;fix scalar inspection of non-tensor extra state."""
import base64
import shlex
import subprocess

import yaml

from scripts.artifact_io import load_json_object, write_json_exclusive
from .environment import ENV_ROOT
from .native_preflight import REMOTE
from .probe import OUTPUT, ROOT

PROGRAM = '''import hashlib,json,torch
from pathlib import Path
root=Path(ROOT);p=root/'nequip/output/best.ckpt'
v=torch.load(p,map_location='cpu',weights_only=False)
steps=[float(x['step']) for x in v['optimizer_states'][0]['state'].values() if 'step' in x]
tensors=[t for t in v['state_dict'].values() if isinstance(t,torch.Tensor)]
assert v['global_step']==2 and steps and min(steps)==max(steps)==2
assert tensors and all(bool(torch.isfinite(t).all()) and not t.is_cuda for t in tensors)
assert not torch.cuda.is_initialized()
ft=json.loads((root/'finetune_cpu.stdout').read_bytes())
assert ft['native_cli']['status']=='PASS_NATIVE_CLI_NO_MODEL' and ft['counts']=={'train':512,'development':78,'heldout':53}
print(json.dumps({'status':'BOTH_NATIVE_CPU_PREFLIGHTS_PASS_NO_GPU_TRAINING','root':str(root),'GPU_training_started':False,
 'native_checkpoint':{'global_step':2,'optimizer_state_step_min':min(steps),'optimizer_state_step_max':max(steps),'CUDA_initialized':False,
 'tensor_state_entries_checked':len(tensors),'non_tensor_entries':[k for k,t in v['state_dict'].items() if not isinstance(t,torch.Tensor)],
 'checkpoint_sha256':hashlib.sha256(p.read_bytes()).hexdigest()},'finetune':ft}),flush=True)
'''


def run():
    program = "ROOT=" + repr(REMOTE) + "\n" + PROGRAM
    write_json_exclusive(OUTPUT / "native_postcheck_program.json", {"program": program, "model_rerun": False})
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    code = "import os;os.environ['CUDA_VISIBLE_DEVICES']='-1';os.environ['PYTHONDONTWRITEBYTECODE']='1';exec(__import__('base64').b64decode('" + base64.b64encode(program.encode()).decode() + "'))"
    args = ["ssh", "-n", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], shlex.join([ENV_ROOT + "/venv/bin/python", "-c", code])]
    process = subprocess.run(args, capture_output=True, timeout=55, check=False)
    for suffix, data in [("stdout", process.stdout), ("stderr", process.stderr)]:
        with (OUTPUT / ("native_postcheck." + suffix)).open("xb") as target:
            target.write(data)
    write_json_exclusive(OUTPUT / "native_postcheck_receipt.json", {"returncode": process.returncode, "model_rerun": False})
    if process.returncode:
        raise RuntimeError("read-only postcheck failed;preserve successful run outputs")
    result = load_json_object(OUTPUT / "native_postcheck.stdout")
    write_json_exclusive(OUTPUT / "native_cpu_v2.json", result)
    print(result)


if __name__ == "__main__":
    run()
