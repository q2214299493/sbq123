"""Return and hash-check the successful candidate;no GPU inference or promotion."""
from __future__ import annotations

import io
import json
from pathlib import Path
import shlex
import shutil
import tarfile

from scripts.artifact_io import sha256_file, source_file_manifest, write_json_exclusive
from .prepare import OUTPUT, PACKAGE, REMOTE, RUN_ID
from .transport import call


def extract_returned(blob, manifest, destination):
    expected = {row["path"]: row for row in manifest["files"]}
    destination.mkdir(exist_ok=False)
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as archive:
        for member in archive:
            target = (destination / member.name).resolve()
            if (not member.isfile() or member.name not in expected or member.name in seen
                    or not target.is_relative_to(destination.resolve()) or member.size != expected[member.name]["bytes"]):
                raise ValueError("unsafe or unexpected returned archive member")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if sha256_file(target) != expected[member.name]["sha256"]:
                raise ValueError("returned file hash differs from remote manifest")
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("returned archive is incomplete")


def collect():
    digest = sha256_file(PACKAGE / "direct_request.json")
    directory = "control/output/" + RUN_ID + "/"
    paths = ["preflight_control.json", "direct_launch_marker.json", "direct_launch_receipt.json", "direct_started.json", "direct_batch_exit_record.json"]
    paths += [directory + name for name in ["started.json", "execution_device.json", "cuda_allocator_budget.json",
        "native_two_backward_check.json", "training_completed.json", "producer_exit_record.json", "candidate.pt", "training.log"]]
    program = '''import hashlib,json,torch
from pathlib import Path
root=Path(ROOT)
batch=json.loads((root/'direct_batch_exit_record.json').read_text());producer=json.loads((root/DIR/'producer_exit_record.json').read_text());completed=json.loads((root/DIR/'training_completed.json').read_text())
if batch['request_sha256']!=SHA or batch['exit_code']!=0 or producer['exit_code']!=0 or completed['optimizer_steps']!=1024:raise ValueError('successful native terminal receipts required')
files=[]
for name in FILES:
 p=root/name;size=p.stat().st_size
 if size>2*1024**3:raise ValueError('return file exceeds reviewed transfer cap')
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 files.append({'path':name,'bytes':size,'sha256':h.hexdigest()})
payload=torch.load(root/DIR/'candidate.pt',map_location='cpu',weights_only=False)
metadata={key:payload[key] for key in ['epoch','step','best_val_metric','primary_metric'] if key in payload and isinstance(payload[key],(str,int,float,bool,type(None)))}
print(json.dumps({'status':'NATIVE_SUCCESS_READY_TO_RETURN','request_sha256':SHA,'files':files,'checkpoint_keys':list(payload),'candidate_metadata':metadata,'CUDA_initialized':torch.cuda.is_initialized(),'heldout_inference_run':False}),flush=True)
'''
    source = "ROOT=" + repr(REMOTE) + "\nDIR=" + repr(directory) + "\nSHA=" + repr(digest) + "\nFILES=" + repr(paths) + "\n" + program
    prefix = "env PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= PYTHONPATH=/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -c "
    manifest = json.loads(call(prefix + shlex.quote(source), "collection_manifest", timeout=55))
    if manifest["CUDA_initialized"]:
        raise ValueError("candidate metadata extraction unexpectedly initialized CUDA")
    write_json_exclusive(OUTPUT / "collection_manifest.json", manifest)
    program = "import sys,tarfile\nfrom pathlib import Path\nwith tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:\n for name in FILES:archive.add(Path(ROOT)/name,arcname=name,recursive=False)\n"
    blob = call("env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\nFILES=" + repr(paths) + "\n" + program), "collection_archive", timeout=180)
    extract_returned(blob, manifest, OUTPUT / "returned")
    candidate = OUTPUT / "returned" / directory / "candidate.pt"
    result = {"status": "SUCCESSFUL_CANDIDATE_COLLECTED_NOT_PROMOTED", "candidate_path": str(candidate),
        "candidate_sha256": sha256_file(candidate), "files_verified": len(paths), "candidate_metadata": manifest["candidate_metadata"],
        "heldout_inference_run": False, "accuracy_or_speedup_established": False,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "collection_manifest.json", candidate,
            OUTPUT / "returned/direct_batch_exit_record.json", OUTPUT / "returned" / directory / "producer_exit_record.json"])}
    write_json_exclusive(OUTPUT / "collection_receipt.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    collect()
