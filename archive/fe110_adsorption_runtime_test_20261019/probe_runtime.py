"""Read only the deployed Fairchem interfaces; no model imports or remote writes."""
import subprocess
from pathlib import Path

from scripts.artifact_io import write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_runtime_test_20261019_v1"
REMOTE = r'''
import ast,hashlib,json
from pathlib import Path
root=Path('/home/sbq/sbq/aqcat25/vendor/fairchem/core')
names={'_compute_loss','load_datasets','get_sampler','get_dataloader','get_dataset',
       '__getitem__','get_atoms','setup_imports','get_trainer_class','get_dataset_class','_get_class'}
paths=[root/p for p in ('trainers/base_trainer.py','trainers/ocp_trainer.py',
       'datasets/ase_datasets.py','common/data_parallel.py','common/registry.py','common/utils.py')]
for p in (root/'models/equiformer_v2').rglob('*.py'):
 if p.stat().st_size>100000: continue
 if b'equiformerv2_forces' in p.read_bytes(): paths.append(p)
result=[]
for path in dict.fromkeys(paths):
 raw=path.read_bytes()
 if len(raw)>100000: raise ValueError('source inspection budget')
 source=raw.decode(); tree=ast.parse(source); nodes=[]
 for node in ast.walk(tree):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
   nodes.append({'name':node.name,'line':node.lineno,'source':'\n'.join(source.splitlines()[node.lineno-1:node.end_lineno])})
 if b'equiformerv2_forces' in raw:
  nodes.append({'name':'registered_equiformerv2_source','source':source})
 result.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'selected_nodes':nodes,
                'class_names':[n.name for n in ast.walk(tree) if isinstance(n,ast.ClassDef)]})
print(json.dumps({'model_imported':False,'remote_files_written':False,'interfaces':result}))
'''


def main():
    OUTPUT.mkdir(exist_ok=True)
    output = OUTPUT / "runtime_interfaces.json"
    errors = OUTPUT / "runtime_interfaces.stderr.txt"
    if output.exists() or errors.exists():
        raise FileExistsError("preserve existing diagnostic")
    with output.open("xb") as stdout, errors.open("xb") as stderr:
        result = subprocess.run(["ssh", "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent",
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-p", "36039", "sbq@10sx4jr711576.vicp.fun", "env PYTHONDONTWRITEBYTECODE=1 python3 -"],
            input=REMOTE.encode(), stdout=stdout, stderr=stderr, timeout=45, check=False)
    write_json_exclusive(OUTPUT / "interface_probe_receipt.json", {"exit_code": result.returncode,
        "model_imported": False, "remote_files_written": False})
    if result.returncode:
        raise RuntimeError("interface probe failed; inspect preserved stderr")
    print("READ_ONLY_INTERFACE_CAPTURED", output.stat().st_size)


if __name__ == "__main__":
    main()
