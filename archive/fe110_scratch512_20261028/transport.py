"""Exclusive framed transport and one native sequential training launch."""
import argparse
import io
import shlex
import subprocess
import tarfile

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .prepare import REMOTE
from .probe import OUTPUT, PYTHON, ROOT


def call(command, name, data=None, timeout=55):
    ssh = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["ssh"]
    args = ["ssh", "-i", ssh["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "-p", str(ssh["port"]), ssh["user"] + "@" + ssh["host"], command]
    with (OUTPUT / (name + ".stdout")).open("xb") as stdout, (OUTPUT / (name + ".stderr")).open("xb") as stderr:
        try:
            process = subprocess.run(args, input=data, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
            result = {"returncode": process.returncode}
        except subprocess.TimeoutExpired:
            result = {"returncode": None, "timeout_seconds": timeout}
    write_json_exclusive(OUTPUT / (name + ".receipt.json"), result)
    if result["returncode"] != 0:
        raise RuntimeError(name + " failed;inspect remote marker and retained receipt before any retry")
    return (OUTPUT / (name + ".stdout")).read_bytes()


def module_command(action):
    package = OUTPUT / "package"
    sha = sha256_file(package / "sequence_request.json")
    prefix = REMOTE + "/finetune/control/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
    return shlex.join(["env", "PYTHONDONTWRITEBYTECODE=1", "PYTHONUTF8=1", "PYTHONPATH=" + prefix, PYTHON,
        REMOTE + "/sequence_driver.py", action, "--request", REMOTE + "/sequence_request.json", "--sha256", sha])


def upload():
    package = OUTPUT / "package"
    seq = load_json_object(package / "sequence_request.json")
    paths = [r["path"] for r in seq["artifacts"]] + ["sequence_request.json", "sequence_authorization.json"]
    files = {name: sha256_file(package / name) for name in paths}
    for row in seq["artifacts"]:
        if files[row["path"]] != row["sha256"]:
            raise ValueError("authorized source artifact changed")
    write_json_exclusive(OUTPUT / "upload_reservation.json", {"sequence_request_sha256": files["sequence_request.json"], "remote_root": REMOTE, "files": len(files)})
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name in paths:
            archive.add(package / name, arcname=name, recursive=False)
    program = '''import hashlib,json,socket,sys,tarfile
from pathlib import Path
root=Path(ROOT);boundary=Path('/home/sbq/sbq').resolve()
if socket.gethostname()!='MZ73' or str(boundary)!='/home/ubuntu/hdd/sbq/sbq' or not root.resolve().is_relative_to(boundary):raise ValueError('host/write boundary mismatch')
if root.exists():raise FileExistsError('preserve existing production target')
root.mkdir();seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or member.name not in FILES or member.name in seen or not target.is_relative_to(root.resolve()) or member.size>20*1024**2:raise ValueError('invalid bound input')
  data=archive.extractfile(member).read()
  if hashlib.sha256(data).hexdigest()!=FILES[member.name]:raise ValueError('uploaded hash mismatch')
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as out:out.write(data)
  seen.add(member.name)
if seen!=set(FILES):raise ValueError('incomplete upload')
with (root/'upload_receipt.json').open('x') as out:json.dump({'file_count':len(seen),'all_hashes_verified':True,'model_started':False},out)
print(json.dumps({'file_count':len(seen),'all_hashes_verified':True,'model_started':False}),flush=True)
'''
    source = ("ROOT=" + repr(REMOTE) + "\nFILES=" + repr(files) + "\n" + program).encode()
    bootstrap = "import sys;n=int(sys.stdin.buffer.readline());exec(compile(sys.stdin.buffer.read(n),'<authorized-upload>','exec'))"
    print(call(shlex.join([PYTHON, "-c", bootstrap]), "production_upload", str(len(source)).encode() + b"\n" + source + stream.getvalue(), timeout=180).decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload", "preflight", "launch"])
    args = parser.parse_args()
    if args.action == "upload":
        upload()
    else:
        if args.action == "launch":
            if load_json_object(OUTPUT / "production_preflight.receipt.json")["returncode"] != 0:
                raise ValueError("native current preflight required")
            write_json_exclusive(OUTPUT / "launch_reservation.json", {"sequence_request_sha256": sha256_file(OUTPUT / "package/sequence_request.json"), "automatic_retry": False})
        print(call(module_command(args.action), "production_" + args.action, timeout=330 if args.action == "preflight" else 55).decode())
