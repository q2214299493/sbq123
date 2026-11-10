"""Return the first GPU producer's preserved artifacts, including failed audit."""
from pathlib import Path
import json
import subprocess
import tarfile

from archive.fe110_c2_dual_gpu_20261106.deploy import connection
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .prepare import OUT, REMOTE
from .transport import command


def main():
    job=load_json_object(OUT/"submission_receipt.json")["job_id"]
    dest=OUT/("return_"+job)
    if dest.exists():
        raise SystemExit("Return exists; inspect its receipt.")
    ssh,host=connection("aqcat_gpu")
    program="""import hashlib,json,subprocess
from pathlib import Path
root=Path(ROOT); files=[]
paths=[p for name in ('output','admission') for p in (root/name).rglob('*') if p.is_file()]
paths += [p for p in root.iterdir() if p.is_file() and p.name!='package.tar.gz']
for p in sorted(paths):
 files.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
s=subprocess.run(['scontrol','show','job','-o','12405'],capture_output=True,text=True)
print(json.dumps({'files':files,'scheduler':{'stdout':s.stdout,'stderr':s.stderr,'returncode':s.returncode}}))
""".replace("ROOT",repr(REMOTE)).replace("'12405'",repr(job))
    inventory=json.loads(command(ssh+[host,"python3 -"],"return_inventory",stdin=program))
    dest.mkdir()
    archive=dest/"return.tar.gz"
    names=[r["path"] for r in inventory["files"]]
    if any(not (Path(name).parts and ".." not in Path(name).parts and not Path(name).is_absolute()) for name in names):
        raise ValueError("Unsafe return scope.")
    with archive.open("xb") as handle:
        result=subprocess.run(ssh+[host,"tar -czf - -C "+REMOTE+" -- "+" ".join(names)],stdout=handle,stderr=subprocess.PIPE,timeout=90)
    if result.returncode:
        raise ValueError("Return transfer failed.")
    expected={r["path"]:r for r in inventory["files"]}
    with tarfile.open(archive,"r:gz") as source:
        for m in source:
            if m.name not in expected or not m.isfile():raise ValueError("Unexpected return member.")
            target=dest/m.name
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as handle:handle.write(source.extractfile(m).read())
            if sha256_file(target)!=expected[m.name]["sha256"]:raise ValueError("Return hash mismatch.")
    exit_record=load_json_object(dest/"worker_exit.json")
    write_json_exclusive(dest/"collection_receipt.json",{"status":"HASH_VERIFIED_PRODUCER_OUTPUTS" if exit_record["exit_code"]==0 else "HASH_VERIFIED_PARTIAL_PRODUCER_FAILURE_PRESERVED",**inventory})
    print("RETURNED",len(names),flush=True)


if __name__=="__main__":
    main()
