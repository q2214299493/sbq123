"""BUCT2 exact-once package deployment/preflight/submission; no model launch."""
import argparse
import json
import tarfile

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .deploy import OUT, REMOTE, connection, rpc, run_logged
from .prepare import ENV, PACKAGE, PARENT_SHA, PYTHON


def upload():
    archive = OUT / "input_package_v3.tar"
    with tarfile.open(archive, mode="x") as handle:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_symlink():
                raise ValueError("package symlink forbidden")
            if path.is_file():
                handle.add(path, arcname=path.relative_to(PACKAGE).as_posix(), recursive=False)
    args, dest = connection("buct2_gpu", "scp")
    run_logged(args + [str(archive), dest + ":" + REMOTE + "/input_package_v3.tar"], "input_package_upload_v3")
    code = '''import hashlib,json,socket,tarfile
from pathlib import Path
root=Path(ROOT);assert socket.gethostname()=='pc-G7466-M6'
assert hashlib.sha256((root/'input_package_v3.tar').read_bytes()).hexdigest()==SHA
count=0
with tarfile.open(root/'input_package_v3.tar') as archive:
 for item in archive:
  target=(root/item.name).resolve()
  if not item.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe package member')
  target.parent.mkdir(parents=True,exist_ok=True)
  with archive.extractfile(item) as source,target.open('xb') as output:output.write(source.read())
  count+=1
print(json.dumps({'status':'PACKAGE_UPLOADED','files':count}))
'''
    print(rpc("buct2_gpu", "ROOT=" + repr(REMOTE) + "\nSHA=" + repr(sha256_file(archive)) + "\n" + code,
              "input_package_extract_v3").decode(), flush=True)


def preflight():
    if load_json_object(OUT / "runtime_unpack.receipt.json")["exit_code"] != 0:
        raise ValueError("runtime transfer/extraction has not passed")
    digest = sha256_file(PACKAGE / "request.json")
    code = '''import json,os,subprocess
from pathlib import Path
root=Path(ROOT)
for name in ['cache/matplotlib','cache/xdg','cache/torch','cache/huggingface','tmp']:(root/name).mkdir(parents=True,exist_ok=True)
p=subprocess.run(['bash','-n',str(root/'run.sbatch')],capture_output=True,text=True)
if p.returncode:raise RuntimeError(p.stderr)
env=os.environ.copy();env.update(ENV)
p=subprocess.run([PYTHON,str(root/'worker.py'),'preflight','--request',str(root/'request.json'),'--sha256',SHA],env=env,cwd=root,capture_output=True,text=True)
with (root/'native_preflight_v3.stdout').open('x') as h:h.write(p.stdout)
with (root/'native_preflight_v3.stderr').open('x') as h:h.write(p.stderr)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout[-6000:],'stderr':p.stderr[-6000:],'GPU_model_run':False}))
raise SystemExit(p.returncode)
'''
    constants = "\n".join(key + "=" + repr(value) for key, value in {"ROOT": REMOTE, "ENV": ENV,
        "PYTHON": PYTHON, "SHA": digest}.items())
    print(rpc("buct2_gpu", constants + "\n" + code, "native_preflight_v3", timeout=180).decode(), flush=True)


def submit():
    if load_json_object(OUT / "native_preflight_v3.receipt.json")["exit_code"] != 0:
        raise ValueError("native BUCT2 preflight not passed")
    # Do not add a replica if the original has already started successfully.
    code = r'''import json,re,subprocess
p=subprocess.run(['scontrol','show','job','-o','11396'],capture_output=True,text=True,timeout=15)
if p.returncode:raise RuntimeError(p.stderr)
f=dict(re.findall(r'(\w+)=([^\s]+)',p.stdout))
assert f['Comment']==SHA and f['UserId']=='sbq(1024)'
print(json.dumps({'job_id':'11396','state':f['JobState'],'scheduler_raw':p.stdout}))
'''
    primary = json.loads(rpc("aqcat_gpu", "SHA=" + repr(PARENT_SHA) + "\n" + code, "primary_before_replica"))
    if primary["state"] != "PENDING":
        raise RuntimeError("original no longer pending;review its state before any extra submission")
    digest = sha256_file(PACKAGE / "request.json")
    write_json_exclusive(OUT / "submission_reservation.json", {"request_sha256": digest, "peer_job_id": "11396"})
    code = '''import datetime,json,subprocess
from pathlib import Path
root=Path(ROOT)
with (root/'submission_attempt.json').open('x') as h:json.dump({'request_sha256':SHA},h)
p=subprocess.run(['sbatch','--parsable','--job-name=fe12b-'+SHA[:10],'--comment='+SHA,'--export=ALL,REQUEST_SHA256='+SHA,str(root/'run.sbatch')],capture_output=True,text=True)
with (root/'sbatch.stdout').open('x') as h:h.write(p.stdout)
with (root/'sbatch.stderr').open('x') as h:h.write(p.stderr)
job=p.stdout.strip().split(';')[0]
r={'exit_code':p.returncode,'job_id':job if job.isdigit() else None,'request_sha256':SHA,'submitted_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scheduler':'Slurm','native_stdout':p.stdout,'stderr':p.stderr,'VASP_submitted':False,'single_winner_permit_required':True}
if p.returncode==0 and job.isdigit():
 q=subprocess.run(['squeue','-h','-j',job,'-o','%i|%T|%R|%S'],capture_output=True,text=True)
 r['queue_snapshot']={'exit_code':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
with (root/'submission_receipt.json').open('x') as h:json.dump(r,h,indent=2)
print(json.dumps(r))
if p.returncode or not job.isdigit():raise SystemExit(3)
'''
    raw = rpc("buct2_gpu", "ROOT=" + repr(REMOTE) + "\nSHA=" + repr(digest) + "\n" + code, "submit")
    receipt = json.loads(raw)
    write_json_exclusive(OUT / "submission_receipt.json", receipt)
    print(raw.decode(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("upload", "preflight", "submit"))
    {"upload": upload, "preflight": preflight, "submit": submit}[parser.parse_args().phase]()
