"""Read MZ73 model hashes and runtime availability without running models/jobs."""
import subprocess
from pathlib import Path

from scripts.artifact_io import load_json_object, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_to_mid_gpu_20260910'
REMOTE_CODE = r'''
import hashlib, json, socket, subprocess
from pathlib import Path
from datetime import datetime, timezone
paths = {
 'matris': '/home/sbq/sbq/mlip_same_structure_benchmark_20260825/MatRIS_4M_FeCOH_compliant.pth.tar',
 'aqcat25': '/home/sbq/sbq/aqcat25/demo_single/model.pt',
}
models = {}
for name, value in paths.items():
 p = Path(value)
 hasher = hashlib.sha256()
 with p.open('rb') as handle:
  for block in iter(lambda: handle.read(1024*1024), b''):
   hasher.update(block)
 digest = hasher.hexdigest()
 models[name] = {'path':value, 'bytes':p.stat().st_size, 'sha256':digest}
queries = {}
for name, args in {
 'gpu_inventory':['nvidia-smi','--query-gpu=index,name,memory.free','--format=csv,noheader,nounits'],
 'queue':['squeue','-h','-u','sbq','-o','%A|%j|%T|%R'],
}.items():
 r = subprocess.run(args, capture_output=True, text=True, timeout=20)
 queries[name] = {'exit_code':r.returncode,'stdout':r.stdout[:5000],'stderr':r.stderr[:1000]}
print(json.dumps({'hostname':socket.gethostname(),'observed_at':datetime.now(timezone.utc).isoformat(),
 'models':models, 'queries':queries,
 'matris_source_available':Path('/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS/matris').is_dir(),
 'runtime_python_available':Path('/home/sbq/sbq/ml_ts_acceleration/venv/bin/python').is_file(),
 'model_execution_performed':False,'scheduler_submission_performed':False}))
'''


def main() -> None:
    BASE.mkdir(exist_ok=True)
    command = ['ssh','-p','36039','-i','C:/Users/86177/.ssh/id_ed25519_fe_agent',
               '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15',
               'sbq@10sx4jr711576.vicp.fun', '/home/sbq/sbq/ml_ts_acceleration/venv/bin/python -']
    result = subprocess.run(command,input=REMOTE_CODE.encode(),capture_output=True,timeout=55)
    with (BASE/'remote_inventory_v2.stdout').open('xb') as handle:
        handle.write(result.stdout)
    with (BASE/'remote_inventory_v2.stderr').open('xb') as handle:
        handle.write(result.stderr)
    write_json_exclusive(BASE/'remote_inventory_v2_receipt.json',{'exit_code':result.returncode,'read_only':True})
    result.check_returncode()
    inventory = load_json_object(BASE/'remote_inventory_v2.stdout')
    assert inventory['hostname'] == 'MZ73'
    write_json_exclusive(BASE/'remote_inventory.json', inventory)
    print({'hostname':inventory['hostname'],'models':inventory['models'],
           'runtime_python_available':inventory['runtime_python_available'],
           'matris_source_available':inventory['matris_source_available'],
           'queries':inventory['queries']})


if __name__ == '__main__':
    main()
