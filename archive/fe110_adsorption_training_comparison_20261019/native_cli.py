"""Exercise reviewed CLI/configs in deployed Fairchem using RAM-only modules,not a model."""
import subprocess

from scripts.artifact_io import sha256_file, write_json_exclusive

from .prepare import OUTPUT, REMOTE

REMOTE_CHECK = r'''
import builtins,io,json,os,sys,types
from pathlib import Path
from unittest.mock import patch
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['PYTHONDONTWRITEBYTECODE']='1'
for name in ('scripts','scripts.adsorption'):
 module=types.ModuleType(name);module.__path__=[];sys.modules[name]=module
results={}
original_read=Path.read_text;original_open=builtins.open
for arm,item in PAYLOAD['arms'].items():
 root=Path(PAYLOAD['remote'])/arm
 for name,source in PAYLOAD['sources'].items():
  module=types.ModuleType(name);module.__file__=str(root/'runtime'/Path(*name.split('.')).with_suffix('.py'))
  sys.modules[name]=module;exec(compile(source,module.__file__,'exec'),module.__dict__)
 files={str(root/'config.yml'):item['config'],str(root/'runtime/role_training_job.sh'):PAYLOAD['wrapper'],
  str(root/'training_request.json'):json.dumps({'config_path':'config.yml'})}
 def read_text(path,*args,**kwargs):
  return files[str(path)] if str(path) in files else original_read(path,*args,**kwargs)
 def open_config(path,*args,**kwargs):
  return io.StringIO(files[str(path)]) if str(path) in files else original_open(path,*args,**kwargs)
 with patch.object(Path,'read_text',read_text),patch('builtins.open',open_config):
  result=sys.modules['scripts.adsorption.force_training_preflight'].check_native_cli(root)
 results[arm]=result
import torch
assert not torch.cuda.is_initialized()
print(json.dumps({'status':'PASS_NATIVE_CLI_RAM_ONLY','arms':results,'CUDA_initialized':False,
 'model_instantiated':False,'checkpoint_loaded':False,'remote_files_written':False,
 'private_geometries_or_labels_sent':False,'on_disk_deployment_namespace_verified':False}))
'''


def main():
    names = ("force_finetune", "force_role_data", "force_role_runtime", "role_force_trainer", "force_training_preflight")
    runtime = OUTPUT / "control/runtime/scripts/adsorption"
    sources = {"scripts.adsorption." + name: (runtime / f"{name}.py").read_text(encoding="utf-8") for name in names}
    wrapper = OUTPUT / "control/runtime/role_training_job.sh"
    payload = {"remote": REMOTE, "sources": sources, "wrapper": wrapper.read_text(encoding="utf-8"),
               "arms": {name: {"config": (OUTPUT / name / "config.yml").read_text(encoding="utf-8")}
                        for name in ("control", "treatment")}}
    program = "PAYLOAD=" + repr(payload) + "\n" + REMOTE_CHECK
    with (OUTPUT / "native_cli.json").open("xb") as stdout, (OUTPUT / "native_cli.stderr.txt").open("xb") as stderr:
        result = subprocess.run(["ssh", "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-p", "36039", "sbq@10sx4jr711576.vicp.fun",
            "env CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/sbq/sbq/aqcat25_ts_pilot:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -"],
            input=program.encode(), stdout=stdout, stderr=stderr, timeout=60, check=False)
    write_json_exclusive(OUTPUT / "native_cli_receipt.json", {"exit_code": result.returncode,
        "wrapper_sha256": sha256_file(wrapper), "runtime_sha256": {name: sha256_file(runtime / f"{name}.py") for name in names},
        "config_sha256": {name: sha256_file(OUTPUT / name / "config.yml") for name in payload["arms"]},
        "model_run": False, "GPU_used": False, "remote_files_written": False})
    if result.returncode:
        raise RuntimeError("native CLI check failed; inspect preserved stderr,do not rerun unchanged")
    print((OUTPUT / "native_cli.json").read_text())


if __name__ == "__main__":
    main()
