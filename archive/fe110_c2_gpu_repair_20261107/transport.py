"""Task-scoped exact-once repair deployment and native Slurm execution."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

from archive.fe110_c2_dual_gpu_20261106.deploy import connection
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .prepare import OUT, REMOTE, environment

BACKENDS = ("aqcat_gpu", "buct2_gpu")


def logged(argv, base, name, timeout=60):
    base.mkdir(parents=True, exist_ok=True)
    with (base / (name + ".stdout")).open("xb") as stdout, (base / (name + ".stderr")).open("xb") as stderr:
        result = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=timeout)
    write_json_exclusive(base / (name + ".receipt.json"), {"exit_code": result.returncode,
        "checked_at": datetime.now(timezone.utc).isoformat(), "stdout_sha256": sha256_file(base / (name + ".stdout"))})
    if result.returncode:
        raise RuntimeError(f"{name} exited {result.returncode}; inspect preserved evidence before retry")
    return (base / (name + ".stdout")).read_bytes()


def rpc(backend, code, name, timeout=60):
    args, destination = connection(backend)
    return logged(args + ["-T", destination, "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote(code)],
                  OUT / backend, name, timeout)


def runtime(backend):
    _, _, cudart = environment(backend)
    code = '''import hashlib,json,socket
from pathlib import Path
root=Path(ROOT)
root.mkdir(exist_ok=False)
(root/'preflight').mkdir()
path=Path(CUDART)
print(json.dumps({'host':socket.gethostname(),'cudart_path':str(path),'cudart_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
'''
    return json.loads(rpc(backend, "ROOT=" + repr(REMOTE) + "\nCUDART=" + repr(cudart) + "\n" + code, "runtime_identity"))


def diagnostic(backend):
    args, destination = connection(backend, "scp")
    logged(args + [str(Path(__file__).with_name("device.py")), destination + ":" + REMOTE + "/preflight/device_v2.py"],
           OUT / backend, "diagnostic_upload_v2")
    python, env, cudart = environment(backend)
    code = '''import json,os,subprocess
from pathlib import Path
root=Path(ROOT);env=os.environ.copy();env.update(ENV)
args=['srun','--immediate=5','--partition=gpu','--nodes=1','--ntasks=1','--cpus-per-task=1','--gres=gpu:1','--mem=2G','--time=00:00:45',PYTHON,str(root/'preflight/device_v2.py'),'--cudart',CUDART]
p=subprocess.run(args,env=env,capture_output=True,text=True,timeout=65)
for name,value in [('device_v2.stdout',p.stdout),('device_v2.stderr',p.stderr)]:
 with (root/'preflight'/name).open('x') as h:h.write(value)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout[-14000:],'stderr':p.stderr[-4000:],'model_loaded':False}))
'''
    constants = {"ROOT": REMOTE, "ENV": env, "PYTHON": python, "CUDART": cudart}
    raw = rpc(backend, "\n".join(key + "=" + repr(value) for key, value in constants.items()) + "\n" + code,
              "allocated_device_diagnostic_v2", 90)
    print(backend, raw.decode().strip(), flush=True)


def upload(backend):
    base = OUT / backend
    package = base / "package"
    archive = base / "package.tar"
    with tarfile.open(archive, "x") as handle:
        for path in sorted(package.rglob("*")):
            if path.is_symlink():
                raise ValueError("symlink in package")
            if path.is_file():
                handle.add(path, arcname=path.relative_to(package).as_posix(), recursive=False)
    args, destination = connection(backend, "scp")
    logged(args + [str(archive), destination + ":" + REMOTE + "/package.tar"], base, "upload")
    code = '''import hashlib,json,tarfile
from pathlib import Path
root=Path(ROOT);archive=root/'package.tar'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==SHA
with tarfile.open(archive) as handle:
 for item in handle:
  target=(root/item.name).resolve()
  if not item.isfile() or not target.is_relative_to(root.resolve()):raise ValueError('unsafe member')
  target.parent.mkdir(parents=True,exist_ok=True)
  with handle.extractfile(item) as src,target.open('xb') as dst:dst.write(src.read())
print(json.dumps({'status':'UPLOADED','archive_sha256':SHA}))
'''
    print(backend, rpc(backend, "ROOT=" + repr(REMOTE) + "\nSHA=" + repr(sha256_file(archive)) + "\n" + code, "extract").decode().strip())


def preflight(backend):
    python, env, _ = environment(backend)
    digest = sha256_file(OUT / backend / "package/request.json")
    code = '''import json,os,subprocess
from pathlib import Path
root=Path(ROOT);env=os.environ.copy();env.update(ENV)
for key,value in ENV.items():
 if key.endswith('_DIR') or key in ['TMPDIR','MPLCONFIGDIR','XDG_CACHE_HOME','TORCH_HOME','HF_HOME']:Path(value).mkdir(parents=True,exist_ok=True)
subprocess.run(['bash','-n',str(root/'run.sbatch')],check=True)
p=subprocess.run([PYTHON,str(root/'worker.py'),'preflight','--request',str(root/'request.json'),'--sha256',SHA],cwd=root,env=env,capture_output=True,text=True,timeout=150)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout[-3000:],'stderr':p.stderr[-6000:],'model_loaded':False}))
raise SystemExit(p.returncode)
'''
    constants = {"ROOT": REMOTE, "ENV": env, "PYTHON": python, "SHA": digest}
    raw = rpc(backend, "\n".join(key + "=" + repr(value) for key, value in constants.items()) + "\n" + code, "native_preflight", 180)
    print(backend, raw.decode().strip(), flush=True)


def submit(backend):
    base = OUT / backend
    if load_json_object(base / "native_preflight.receipt.json")["exit_code"] != 0:
        raise RuntimeError("native preflight not passed")
    digest = sha256_file(base / "package/request.json")
    code = '''import datetime,json,re,subprocess
from pathlib import Path
root=Path(ROOT)
cancel=None
if BACKEND=='buct2_gpu':
 p=subprocess.run(['scontrol','show','job','-o','1355'],capture_output=True,text=True,timeout=15)
 if p.returncode==0:
  f=dict(re.findall(r'(\\w+)=([^\\s]+)',p.stdout))
  assert f.get('UserId')=='sbq(1024)' and f.get('Comment')=='1fc8b202d293a784a7ed302da3fc57a76c00f3b478029f01f967efc53310ccf8'
  assert f.get('JobState')=='PENDING','obsolete replica started; inspect before cancellation'
  q=subprocess.run(['scancel','1355'],capture_output=True,text=True,timeout=15)
  cancel={'job_id':'1355','before':p.stdout,'exit_code':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
  assert q.returncode==0
  with (root/'obsolete_cancellation.json').open('x') as h:json.dump(cancel,h,indent=2)
 else:
  cancel={'job_id':'1355','query_exit_code':p.returncode,'stderr':p.stderr,'action':'no_cancel_unknown_or_terminal'}
with (root/'submission_attempt.json').open('x') as h:json.dump({'request_sha256':SHA},h)
p=subprocess.run(['sbatch','--parsable','--job-name=fe12-'+SHA[:10],'--comment='+SHA,'--export=ALL,REQUEST_SHA256='+SHA,str(root/'run.sbatch')],capture_output=True,text=True,timeout=20)
job=p.stdout.strip().split(';')[0]
r={'exit_code':p.returncode,'job_id':job if job.isdigit() else None,'request_sha256':SHA,'backend':BACKEND,'submitted_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scheduler':'Slurm','stdout':p.stdout,'stderr':p.stderr,'obsolete_cancellation':cancel,'independent_replica':True,'VASP_submitted':False}
with (root/'submission_receipt.json').open('x') as h:json.dump(r,h,indent=2)
print(json.dumps(r))
if p.returncode or not job.isdigit():raise SystemExit(3)
'''
    raw = rpc(backend, "ROOT=" + repr(REMOTE) + "\nSHA=" + repr(digest) + "\nBACKEND=" + repr(backend) + "\n" + code, "submit")
    write_json_exclusive(base / "submission_receipt.json", json.loads(raw))
    print(backend, raw.decode().strip(), flush=True)


def status(backend):
    base = OUT / backend
    label = "native_status" if not (base / "native_status.json").exists() else "native_status_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    receipt = load_json_object(base / "submission_receipt.json")
    code = '''import datetime,json,re,subprocess
from pathlib import Path
root=Path(ROOT)
p=subprocess.run(['scontrol','show','job','-o',JOB],capture_output=True,text=True,timeout=15)
r={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job_id':JOB,'scheduler_query_exit_code':p.returncode,'scheduler_raw':p.stdout,'scheduler_stderr':p.stderr}
fields=dict(re.findall(r'(\\w+)=([^\\s]+)',p.stdout))
if p.returncode==0:
 assert fields.get('Comment')==SHA and fields.get('UserId')=='sbq(1024)'
r['state']=fields.get('JobState','UNKNOWN');r['reason']=fields.get('Reason');r['request_sha256']=SHA
records=[]
for name in ['gpu_admission.json','model_device.json','producer_exit_record.json','device_commands.json','cases.json']:
 path=root/'output'/name
 if path.is_file() and path.stat().st_size<250000:r[name]=json.loads(path.read_text())
for path in sorted((root/'output/finetune').glob('*/seed/case_record.json')):
 if path.stat().st_size<30000:records.append(json.loads(path.read_text()))
r['case_records']=records
for suffix in ['out','err']:
 path=root/('slurm-'+JOB+'.'+suffix)
 if path.is_file():
  with path.open('rb') as h:h.seek(max(0,path.stat().st_size-5000));r['log_'+suffix]=h.read().decode(errors='replace')
print(json.dumps(r))
'''
    constants = {"ROOT": REMOTE, "JOB": receipt["job_id"], "SHA": receipt["request_sha256"]}
    raw = rpc(backend, "\n".join(key + "=" + repr(value) for key, value in constants.items()) + "\n" + code, label)
    result = json.loads(raw)
    write_json_exclusive(base / (label + ".json"), result)
    print(backend, json.dumps({key: result[key] for key in ("job_id", "state", "reason")}),
          "model_device=", result.get("model_device.json", {}).get("model_devices"),
          "completed_cases=", len(result["case_records"]),
          "exit=", result.get("producer_exit_record.json", {}).get("exit_code"), flush=True)
    return result


def obsolete(backend):
    job = "11396" if backend == "aqcat_gpu" else "1355"
    old_root = "/home/sbq/sbq/fe110_c2_supplement_gpu_20261106_v1" if backend == "aqcat_gpu" else "/home/sbq/sbq/fe110_c2_supplement_buct2_20261106_v1"
    code = '''import datetime,json,re,subprocess
from pathlib import Path
q=subprocess.run(['scontrol','show','job','-o',JOB],capture_output=True,text=True,timeout=15)
r={'job_id':JOB,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scontrol_exit_code':q.returncode,'scheduler_raw':q.stdout,'scheduler_stderr':q.stderr}
config=subprocess.run(['scontrol','show','config'],capture_output=True,text=True,timeout=15)
matches=re.findall(r'^SlurmctldLogFile\\s*=\\s*(\\S+)',config.stdout,re.MULTILINE)
assert config.returncode==0 and len(matches)==1,'controller log path not available'
path=Path(matches[0]);r['controller_log_path']=str(path)
with path.open('rb') as h:
 h.seek(max(0,path.stat().st_size-2097152));lines=h.read().decode(errors='replace').splitlines()
r['controller_lines']=[line for line in lines if re.search(r'JobId='+JOB+r'(?![0-9])',line)][-30:]
path=Path(OLD_ROOT)/'output/producer_exit_record.json'
if path.exists() and path.stat().st_size<10000:r['producer_exit_record']=json.loads(path.read_text())
print(json.dumps(r))
'''
    constants = {"JOB": job, "OLD_ROOT": old_root}
    result = json.loads(rpc(backend, "\n".join(key + "=" + repr(value) for key, value in constants.items()) + "\n" + code, "obsolete_terminal_v2"))
    write_json_exclusive(OUT / backend / "obsolete_terminal.json", result)
    print(backend, job, result["controller_lines"], flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("runtime", "diagnostic", "upload", "preflight", "submit", "status", "obsolete"))
    parser.add_argument("--backend", choices=BACKENDS)
    args = parser.parse_args()
    backends = [args.backend] if args.backend else BACKENDS
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(globals()[args.phase], backends))
    if args.phase == "runtime":
        write_json_exclusive(OUT / "runtime_identity.json", dict(zip(backends, result)))


if __name__ == "__main__":
    main()
