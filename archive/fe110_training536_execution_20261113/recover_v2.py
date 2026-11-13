"""Recover the existing development best after a post-training export failure."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .checkpoint import OUT, REMOTE
from .submit import ROOT

PROGRAM = r'''
import hashlib,json,os,shutil,socket,time
from pathlib import Path
import torch
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
root=Path(ROOT).resolve();output=root/'output/job_14505';recovery=root/'recovery_v2'
if socket.gethostname()!='MZ73' or not root.is_relative_to(Path('/home/sbq/sbq').resolve()):raise ValueError('host/write boundary changed')
completed=json.loads((output/'training_completed.json').read_text())
if completed['native_iterations']!=1072 or completed['actual_optimizer_updates']!=1072 or completed['epochs']!=2:raise ValueError('native training incomplete')
if Path('/proc/1346701').exists():raise RuntimeError('training process still exists; do not recover concurrently')
candidates=list(root.rglob('best_checkpoint.pt'))
if len(candidates)!=1:raise RuntimeError('unique native best required; no last-checkpoint fallback')
best=candidates[0]
if not best.resolve().is_relative_to(root):raise ValueError('native best escapes execution root')
before=digest(best);payload=torch.load(best,map_location='cpu',weights_only=False)
state=payload['state_dict'];finite=all(bool(torch.isfinite(t).all()) for t in state.values() if torch.is_tensor(t))
if not finite or torch.cuda.is_initialized():raise ValueError('nonfinite checkpoint or unexpected CUDA')
primary=payload.get('config',{}).get('evaluation_metrics',{}).get('primary_metric');info=payload.get('val_metrics',{}).get(primary,{});metric=info.get('metric')
if info.get('numel')!=78:raise ValueError('native best must carry the original 78 development metrics')
if primary!='forces_role_vector_mae' or not isinstance(metric,(int,float)):raise ValueError('native development selection metadata missing')
if digest(best)!=before:raise ValueError('native best changed during read')
with best.open('rb') as source,(output/'candidate.pt').open('xb') as target:shutil.copyfileobj(source,target)
candidate=digest(output/'candidate.pt')
if candidate!=before:raise ValueError('candidate copy differs from native best')
pretrained=Path('/home/sbq/sbq/aqcat25/demo_single/model.pt')
if digest(pretrained)!='e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50':raise ValueError('pretrained checkpoint hash changed')
record={'status':'RECOVERED_EXISTING_NATIVE_DEVELOPMENT_BEST_NO_RETRAINING',
 'native_best_path':str(best),'candidate_path':str(output/'candidate.pt'),'candidate_bytes':(output/'candidate.pt').stat().st_size,
 'native_best_sha256':before,'candidate_sha256':candidate,'best_val_metric':metric,'primary_metric':primary,
 'checkpoint_epoch':payload.get('epoch'),'checkpoint_step':payload.get('step'),
 'native_payload_keys':list(payload),'all_state_tensors_finite':finite,'CUDA_initialized':torch.cuda.is_initialized(),
 'model_forward_backward_optimizer_updates_in_recovery':0,'original_job_exit_code_preserved':1,
 'heldout_used':False,'model_promoted':False,'pretrained_sha256_unchanged':True}
with (recovery/'candidate_recovery.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps({k:v for k,v in record.items() if k!='native_payload_keys'}),flush=True)
'''


def run():
    if (OUT / "recovery_v2_reservation.json").exists():
        raise FileExistsError("inspect existing recovery receipt; do not overwrite a candidate")
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    options = ["-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=12"]
    destination = ssh["user"] + "@" + ssh["host"]
    write_json_exclusive(OUT / "recovery_v2_reservation.json", {"scheduler_job_id": "14505", "training_retry": False,
                                                           "source_files": source_file_manifest([Path(__file__)])})
    setup = r'''
import os,subprocess,sys
from pathlib import Path
root=Path(ROOT);recovery=root/'recovery_v2'
recovery.mkdir()
env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES='-1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',WANDB_MODE='disabled')
for key,name in [('TMPDIR','tmp'),('XDG_CACHE_HOME','cache'),('TORCH_HOME','cache/torch'),('HF_HOME','cache/hf'),('MPLCONFIGDIR','cache/mpl'),('TORCH_EXTENSIONS_DIR','cache/extensions')]:
 path=recovery/name;path.mkdir(parents=True,exist_ok=True);env[key]=str(path)
env['PYTHONPATH']='/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor'
cmd=['/home/sbq/sbq/ml_ts_acceleration/venv/bin/python','-B','-c','ROOT='+repr(ROOT)+chr(10)+PROGRAM]
result=subprocess.run(cmd,env=env,cwd=recovery,timeout=120)
sys.exit(result.returncode)
'''
    compile(setup, "<CPU-only-recovery-bootstrap>", "exec")
    compile(PROGRAM, "<native-best-recovery>", "exec")
    program = "ROOT=" + repr(REMOTE) + "\nPROGRAM=" + repr(PROGRAM) + "\n" + setup
    with (OUT / "recovery_v2.stdout").open("xb") as stdout, (OUT / "recovery_v2.stderr").open("xb") as stderr:
        result = subprocess.run(["ssh", "-T", *options, "-p", str(ssh["port"]), destination,
                                 "python3 -B -c " + shlex.quote(program)],
                                stdout=stdout, stderr=stderr, timeout=150)
    write_json_exclusive(OUT / "recovery_v2_process_receipt.json", {"exit_code": result.returncode})
    if result.returncode:
        raise RuntimeError("inspect canonical recovery evidence before further action; no retraining")
    returned = OUT / "returned"
    returned.mkdir()
    names = ["recovery_v2/candidate_recovery.json", "slurm-14505.log", *["output/job_14505/" + n for n in [
        "allocation_preflight.json", "execution_device.json", "native_two_backward_check.json",
        "training_completed.json", "job_exit_record.json", "candidate.pt"]]]
    copy = subprocess.run(["scp", "-q", *options, "-P", str(ssh["port"]),
                           *[destination + ":" + REMOTE + "/" + n for n in names], str(returned)],
                          capture_output=True, timeout=240)
    write_json_exclusive(OUT / "recovery_return_receipt.json", {"exit_code": copy.returncode,
                                                              "returned_files": source_file_manifest(list(returned.iterdir()))})
    if copy.returncode:
        raise RuntimeError("inspect partial return before copying again")
    receipt = load_json_object(returned / "candidate_recovery.json")
    if sha256_file(returned / "candidate.pt") != receipt["candidate_sha256"]:
        raise ValueError("returned candidate hash mismatch")
    print(receipt)


if __name__ == "__main__":
    run()
