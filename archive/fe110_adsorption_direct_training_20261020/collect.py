"""Return original producer files byte-for-byte; no model run or JSON reserialization."""
import hashlib
import io
import json
import tarfile

from scripts.artifact_io import write_json_exclusive

from .transport import EVIDENCE, REMOTE, call

PROGRAM = r'''
import hashlib,io,json,sys,tarfile
from pathlib import Path
root=Path(ROOT)
run='control/output/direct-adsorption-role-ab-20261020-v1/'
names=['direct_launch_receipt.json','direct_started.json','direct_batch_exit_record.json',
 'preflight_control.json','preflight_treatment.json','ddp_parameter_diagnostic.json','ddp_cpu_regression.json',
 run+'started.json',run+'execution_device.json',run+'producer_exit_record.json',run+'training.log']
hashes={}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for name in names:
  path=root/name
  if not path.is_file() or path.stat().st_size>262144:raise ValueError('missing/oversized expected producer evidence')
  hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest();archive.add(path,arcname=name,recursive=False)
 payload={'files_sha256':hashes,'candidate_exists':(root/run/'candidate.pt').exists(),
  'treatment_output_exists':(root/'treatment/output/direct-adsorption-role-ab-20261020-v1').exists()}
 data=(json.dumps(payload,indent=2)+'\n').encode();entry=tarfile.TarInfo('source_hashes.json');entry.size=len(data)
 archive.addfile(entry,io.BytesIO(data))
'''


def main():
    raw = call("env PYTHONDONTWRITEBYTECODE=1 python3 -", "canonical_results", ("ROOT=" + repr(REMOTE) + "\n" + PROGRAM).encode())
    output = EVIDENCE / "returned"
    output.mkdir(exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            target = (output / member.name).resolve()
            if not member.isfile() or not target.is_relative_to(output.resolve()):
                raise ValueError("unsafe returned artifact")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as destination:
                destination.write(source.read())
    hashes = json.loads((output / "source_hashes.json").read_text(encoding="utf-8"))
    if any(hashlib.sha256((output / name).read_bytes()).hexdigest() != sha for name, sha in hashes["files_sha256"].items()):
        raise ValueError("returned source bytes changed")
    write_json_exclusive(EVIDENCE / "collection_receipt.json", {"source_files": hashes, "verified_byte_copies": True,
        "scientific_acceptance": False, "GPU_retry_performed": False})
    print(json.dumps({"verified_files": len(hashes["files_sha256"]), "candidate_exists": hashes["candidate_exists"],
                      "treatment_started": hashes["treatment_output_exists"]}))


if __name__ == "__main__":
    main()
