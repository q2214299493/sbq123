"""One exact upload and native Slurm submission, with immutable receipts."""
from pathlib import Path
from datetime import datetime, timezone
import json
import shlex
import subprocess
import tarfile

from archive.fe110_c2_dual_gpu_20261106.deploy import connection
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .prepare import OUT, REMOTE, PYTHON, MATRIS_SOURCE


def command(argv, label, *, stdin=None, timeout=90):
    result = subprocess.run(argv,input=stdin,capture_output=True,text=True,timeout=timeout)
    write_json_exclusive(OUT/(label+".json"),{"argv":argv,"returncode":result.returncode,"stdout":result.stdout,
        "stderr":result.stderr,"checked_at":datetime.now(timezone.utc).isoformat()})
    if result.returncode:
        raise ValueError(label+" failed; inspect the exact saved receipt before any retry.")
    return result.stdout


def main():
    if (OUT/"submission_receipt.json").exists():
        raise SystemExit("Already submitted; do not duplicate.")
    package=OUT/"package"
    prep=load_json_object(OUT/"preparation_receipt.json")
    if sha256_file(package/"request.json")!=prep["request_sha256"]:
        raise ValueError("Request changed.")
    bundle=load_json_object(package/"bundle.json")
    for row in bundle["artifacts"]:
        if sha256_file(package/row["path"])!=row["sha256"]:
            raise ValueError("Package changed.")
    archive=OUT/"package.tar.gz"
    with tarfile.open(archive,"x:gz") as target:
        for name in [r["path"] for r in bundle["artifacts"]]+["bundle.json"]:
            target.add(package/name,arcname=name,recursive=False)
    ssh,host=connection("aqcat_gpu")
    command(ssh+[host,"mkdir "+shlex.quote(REMOTE)],"remote_create")
    scp,destination=connection("aqcat_gpu","scp")
    command(scp+[str(archive),destination+":"+REMOTE+"/package.tar.gz"],"upload",timeout=120)
    preflight=r'''import hashlib,json,os,subprocess,tarfile
from pathlib import Path
root=Path(ROOT)
assert hashlib.sha256((root/'package.tar.gz').read_bytes()).hexdigest()==ARCHIVE_SHA
with tarfile.open(root/'package.tar.gz','r:gz') as t:
 for m in t:
  assert m.isfile() and (root/m.name).resolve().is_relative_to(root.resolve())
  target=root/m.name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as f:f.write(t.extractfile(m).read())
b=json.loads((root/'bundle.json').read_text())
for x in b['artifacts']:assert hashlib.sha256((root/x['path']).read_bytes()).hexdigest()==x['sha256']
subprocess.run(['bash','-n',str(root/'run.sbatch')],check=True)
env=dict(os.environ,PYTHONPATH=str(root)+':'+MATRIS_SOURCE+':/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
script="import dual_model_ml_neb; from matris.model.model import MatRIS; from fairchem.core.common.relaxation.ase_utils import patched_calc; import torch; print('IMPORTS_PASS', torch.__version__)"
p=subprocess.run([PYTHON,'-c',script],env=env,capture_output=True,text=True,timeout=60)
print(json.dumps({'imports_returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'bash_syntax':'PASS','artifact_count':len(b['artifacts'])}))
raise SystemExit(p.returncode)
'''
    program="ROOT="+repr(REMOTE)+"\nARCHIVE_SHA="+repr(sha256_file(archive))+"\nPYTHON="+repr(PYTHON)+"\nMATRIS_SOURCE="+repr(MATRIS_SOURCE)+"\n"+preflight
    output=command(ssh+[host,"python3 -"],"remote_preflight",stdin=program,timeout=90)
    check=json.loads(output)
    if check["imports_returncode"]:
        raise ValueError("No-model imports failed; no job submitted.")
    request_sha=prep["request_sha256"]
    submit="cd "+shlex.quote(REMOTE)+" && sbatch --parsable --comment="+request_sha+" --output="+REMOTE+"/slurm-%j.out --error="+REMOTE+"/slurm-%j.err run.sbatch"
    raw=command(ssh+[host,submit],"native_submission")
    job=raw.strip().split(";")[0]
    if not job.isdigit():
        raise ValueError("Unexpected sbatch response; reconcile actual queue before retry.")
    request=load_json_object(package/"request.json")
    write_json_exclusive(OUT/"submission_receipt.json",{"status":"SUBMITTED","job_id":job,"backend":"aqcat_gpu",
        "remote_root":REMOTE,"request_sha256":request_sha,"bundle_sha256":sha256_file(package/"bundle.json"),
        "gpu_count":1,"max_steps":request["ordinary_ml_neb"]["max_steps"],"wall_seconds":request["resources"]["wall_seconds"],"native_stdout":raw,
        "submitted_at":datetime.now(timezone.utc).isoformat(),"automatic_retry":False})
    print("GPU_SUBMITTED",job,flush=True)


if __name__=="__main__":
    main()
