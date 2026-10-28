"""Recover terminal checkpoints and stored development metrics;no inference."""
import argparse
from datetime import datetime, timezone
import io
import json
import shlex
import subprocess
import tarfile

import yaml

from archive.fe110_training512_gpu0_20261027.collect import extract_returned
from scripts.artifact_io import sha256_file, write_json_exclusive
from .environment import ENV_ROOT
from .prepare import REMOTE
from .probe import OUTPUT, ROOT

RUN = "direct-fe110-scratch512-finetune20-20261028-v1"
PROGRAM = r'''import gc,hashlib,io,json,os,sys,tarfile,torch
from pathlib import Path
root=Path(ROOT);run=root/'finetune/control/output'/RUN
sequence=json.loads((root/'sequence_exit.json').read_bytes())
if sequence['request_sha256']!=EXPECTED:raise ValueError('terminal sequence binding changed')
if torch.cuda.is_initialized():raise ValueError('CPU-only recovery required')
def scalar(value):
 if torch.is_tensor(value):return float(value.detach().cpu()) if value.numel()==1 else {'tensor_shape':list(value.shape)}
 if isinstance(value,dict):return {str(k):scalar(v) for k,v in value.items()}
 if isinstance(value,(str,int,float,bool,type(None))):return value
 return {'python_type':type(value).__name__}
def inspect(path,kind):
 before=path.stat()
 if before.st_size>2*1024**3:raise ValueError('checkpoint exceeds cap')
 payload=torch.load(path,map_location='cpu',weights_only=False)
 state=payload.get('state_dict',payload.get('model_state_dict',{}))
 tensors=[v for v in state.values() if isinstance(v,torch.Tensor)]
 result={'path':str(path.relative_to(root)),'kind':kind,'checkpoint_keys':list(payload),
  'finite_model_tensors':bool(tensors) and all(bool(torch.isfinite(v).all()) and not v.is_cuda for v in tensors),
  'tensor_state_entries':len(tensors),'metadata':{k:scalar(payload[k]) for k in ['epoch','step','global_step','best_val_metric','primary_metric','val_metrics'] if k in payload}}
 if 'callbacks' in payload:result['callbacks']={k:scalar(v) for k,v in payload['callbacks'].items()}
 optimizers=payload.get('optimizer_states',[])
 if isinstance(payload.get('optimizer'),dict):optimizers=[payload['optimizer']]
 steps=[float(item['step']) for optimizer in optimizers for item in optimizer.get('state',{}).values() if 'step' in item]
 result['saved_optimizer_step_range']=[min(steps),max(steps)] if steps else None
 after=path.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('terminal checkpoint changed during read')
 del payload,state,tensors;gc.collect()
 return result
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
paths=['sequence_request.json','sequence_authorization.json','sequence_launch_receipt.json','sequence_exit.json','nequip_stage_exit.json',
 'nequip_v2/training_request.json','nequip_v2/config_reviewed.yaml','nequip_v2/producer_exit_record.json','nequip_v2/output/model_device.json',
 'nequip_v2/output/best.ckpt','nequip_v2/output/last.ckpt','nequip_v2/training.log','finetune/direct_request.json','finetune/direct_started.json',
 'finetune/direct_batch_exit_record.json','finetune/control/training_request.json','finetune/control/config.yml']
paths += [str((run/name).relative_to(root)) for name in ['started.json','execution_device.json','native_two_backward_check.json','producer_exit_record.json','training.log'] if (run/name).is_file()]
inventory=[]
for base in [root/'nequip_v2/output',run]:
 count=0
 for path in base.rglob('*'):
  if path.is_file():
   count+=1
   if count>256:raise ValueError('run output inventory exceeds bound')
   if path.suffix in ['.pt','.ckpt']:inventory.append({'path':str(path.relative_to(root)),'bytes':path.stat().st_size})
best=list(run.rglob('best_checkpoint.pt'))
if len(best)>1:raise ValueError('ambiguous FT best checkpoint')
latest=list(run.rglob('checkpoint.pt'))
if len(latest)>1:raise ValueError('ambiguous FT last checkpoint')
models={'nequip_best':inspect(root/'nequip_v2/output/best.ckpt','normal_exit_development_selected'),
 'nequip_last':inspect(root/'nequip_v2/output/last.ckpt','normal_exit_last_state')}
if best:
 paths.append(str(best[0].relative_to(root)));models['finetune_best']=inspect(best[0],'budget_stopped_partial_development_selected_snapshot')
if latest:models['finetune_last_saved']=inspect(latest[0],'budget_stopped_last_saved_state_not_returned')
missing=[name for name in paths if not (root/name).is_file()]
if missing:raise ValueError('required terminal artifacts missing:'+repr(missing))
files=[];total=0
for name in paths:
 p=root/name;size=p.stat().st_size;total+=size
 if size>512*1024**2 or total>768*1024**2:raise ValueError('reviewed return transfer cap exceeded')
 files.append({'path':name,'bytes':size,'sha256':digest(p)})
result={'status':'TERMINAL_SUCCESS_PLUS_BUDGET_STOP_RECOVERY','sequence':sequence,'models':models,'checkpoint_inventory':inventory,'files':files,
 'CUDA_initialized':torch.cuda.is_initialized(),'new_training_or_inference':False,'checkpoint_promotion':False,'missing_FT_completed_marker':not (run/'training_completed.json').exists()}
if result['CUDA_initialized']:raise ValueError('unexpected CUDA in recovery')
data=json.dumps(result).encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 info=tarfile.TarInfo('__collection_manifest__.json');info.size=len(data);archive.addfile(info,io.BytesIO(data))
 for name in paths:archive.add(root/name,arcname=name,recursive=False)
'''


def collect(attempt=1):
    if not isinstance(attempt, int) or isinstance(attempt, bool) or not 1 <= attempt <= 9:
        raise ValueError("recovery attempt must be an explicit integer from 1 to 9")
    target = OUTPUT / f"terminal_recovery_20261028_v{attempt}"
    target.mkdir(exist_ok=False)
    digest = sha256_file(OUTPUT / "package/sequence_request.json")
    program = "ROOT=" + repr(REMOTE) + "\nRUN=" + repr(RUN) + "\nEXPECTED=" + repr(digest) + "\n" + PROGRAM
    write_json_exclusive(target / "reader.json", {"program": program, "remote_writes": False, "GPU_execution": False})
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    prefix = REMOTE + "/nequip_v2/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    command = shlex.join(["env", "CUDA_VISIBLE_DEVICES=-1", "PYTHONDONTWRITEBYTECODE=1", "OMP_NUM_THREADS=4", "MKL_NUM_THREADS=4",
        "PYTHONPATH=" + prefix, ENV_ROOT + "/venv/bin/python", "-c", "import sys;exec(compile(sys.stdin.buffer.read(),'<terminal-reader>','exec'))"])
    args = ["ssh", "-vv", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "ControlMaster=no", "-o", "ControlPath=none", "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (target / "returned.tar").open("xb") as stdout, (target / "transport.stderr").open("xb") as stderr:
        try:
            process = subprocess.run(args, input=program.encode(), stdout=stdout, stderr=stderr, timeout=600, check=False)
            receipt = {"returncode": process.returncode}
        except subprocess.TimeoutExpired:
            receipt = {"returncode": None, "timeout_seconds": 600}
    receipt["checked_at"] = datetime.now(timezone.utc).isoformat()
    write_json_exclusive(target / "transport.json", receipt)
    if receipt["returncode"] != 0:
        raise RuntimeError("terminal collection failed;preserve archive and inspect transport before any retry")
    with tarfile.open(target / "returned.tar", mode="r:") as archive:
        first = archive.next()
        if first.name != "__collection_manifest__.json" or first.size > 1024**2:
            raise ValueError("invalid terminal manifest")
        manifest = json.loads(archive.extractfile(first).read())
        # The existing safe extractor requires precisely the bound payload files.
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as payload:
            for member in archive:
                if member.name == "__collection_manifest__.json":
                    continue
                payload.addfile(member, archive.extractfile(member))
    write_json_exclusive(target / "manifest.json", manifest)
    extract_returned(stream.getvalue(), manifest, target / "returned")
    write_json_exclusive(target / "collection.json", {"status": "HASH_VERIFIED_TERMINAL_ARTIFACTS_RETURNED", "files": len(manifest["files"]),
        "sequence_sha256": digest, "tar_sha256": sha256_file(target / "returned.tar"), "models": manifest["models"],
        "GPU_execution": False, "partial_FT_not_full20_epoch_candidate": True})
    print({"files_verified": len(manifest["files"]), "models": manifest["models"], "checkpoint_inventory": manifest["checkpoint_inventory"]}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=int, default=1, help="New immutable read-only recovery directory;no automatic retry")
    collect(parser.parse_args().attempt)
