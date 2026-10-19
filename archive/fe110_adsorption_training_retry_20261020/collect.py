"""Return original producer bytes and verify per-file transport hashes."""
import io
import json
import tarfile

from scripts.artifact_io import sha256_bytes, sha256_file, write_json_exclusive

from .transport import EVIDENCE, REMOTE, RUN_ID, call


def main():
    program = r'''
import hashlib,io,json,sys,tarfile
from pathlib import Path
root=Path(ROOT)
names=['direct_launch_receipt.json','direct_started.json','direct_batch_exit_record.json',
 'preflight_control.json','preflight_treatment.json','preflight_control.log','preflight_treatment.log','direct_controller.log']
for arm in ('control','treatment'):
 for name in ('started.json','execution_device.json','native_two_backward_check.json','training_completed.json','producer_exit_record.json','training.log'):
  names.append(arm+'/output/'+RUN_ID+'/'+name)
files={}
candidates={}
for arm in ('control','treatment'):
 p=root/arm/'output'/RUN_ID/'candidate.pt'
 if p.is_file():
  hasher=hashlib.sha256()
  with p.open('rb') as handle:
   for chunk in iter(lambda:handle.read(1048576),b''):hasher.update(chunk)
  candidates[arm]={'path':str(p),'sha256':hasher.hexdigest(),'bytes':p.stat().st_size,'promoted':False}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for name in names:
  p=root/name
  if not p.is_file():continue
  if p.stat().st_size>2*1024**2:raise ValueError('unexpectedly large selected evidence')
  data=p.read_bytes();files[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
 data=json.dumps({'files':files,'candidates':candidates,'logs_are_point_in_time_snapshots':True}).encode()
 info=tarfile.TarInfo('remote_collection_manifest.json');info.size=len(data);archive.addfile(info,io.BytesIO(data))
'''
    raw = call("env PYTHONDONTWRITEBYTECODE=1 python3 -", "collect", ("ROOT=" + repr(REMOTE) + "\nRUN_ID=" + repr(RUN_ID) + "\n" + program).encode(), timeout=60)
    target = EVIDENCE / "returned"
    target.mkdir(exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            path = (target / member.name).resolve()
            if not member.isfile() or not path.is_relative_to(target.resolve()):
                raise ValueError("unsafe returned archive")
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, path.open("xb") as output:
                output.write(source.read())
    manifest = json.loads((target / "remote_collection_manifest.json").read_text())
    for name, item in manifest["files"].items():
        if sha256_file(target / name) != item["sha256"]:
            raise ValueError("returned source differs: " + name)
    write_json_exclusive(EVIDENCE / "collection_receipt.json", {"status": "PASS_ORIGINAL_BYTES_VERIFIED",
        "remote_root": REMOTE, "tar_sha256": sha256_bytes(raw), "files": manifest["files"],
        "candidates": manifest["candidates"], "point_in_time": True})
    print(json.dumps({"status": "PASS_ORIGINAL_BYTES_VERIFIED", "file_count": len(manifest["files"])}))


if __name__ == "__main__":
    main()
