"""Task-scoped byte-preserving BUCT2 runtime migration; no scientific launch."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import shlex
import subprocess

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_c2_site_supplement_20261106/gpu_buct2_ft512_20261106_v1"
REMOTE = "/home/sbq/sbq/fe110_c2_supplement_buct2_20261106_v1"
STAGE = "/home/sbq/sbq/fe110_c2_supplement_buct2_stage_20261106_v1"
MODEL = "home/sbq/sbq/fe110_scratch512_20261028_v1/finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/checkpoints/2026-10-28-20-56-32/best_checkpoint.pt"
SITE = "home/sbq/sbq/ml_ts_acceleration/venv/lib/python3.10/site-packages"
PYTHON_PKGS = "home/sbq/sbq/aqcat25/python_pkgs"
VENDOR = "home/sbq/sbq/aqcat25/vendor"
MODEL_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"


def connection(backend, program="ssh"):
    row = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"][backend]["ssh"]
    args = [program, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=12"]
    if "alias" in row:
        return args, row["alias"]
    args += ["-i", row["identity_file"], "-p" if program == "ssh" else "-P", str(row["port"])]
    return args, row["user"] + "@" + row["host"]


def run_logged(argv, label, *, timeout=60):
    with (OUT / (label + ".stdout")).open("xb") as out, (OUT / (label + ".stderr")).open("xb") as err:
        p = subprocess.run(argv, stdout=out, stderr=err, timeout=timeout, check=False)
    write_json_exclusive(OUT / (label + ".receipt.json"), {"exit_code": p.returncode,
        "checked_at": datetime.now(timezone.utc).isoformat(), "argv": argv,
        "stdout_sha256": sha256_file(OUT / (label + ".stdout"))})
    if p.returncode:
        raise RuntimeError(label + " failed; inspect preserved output before retry")
    return (OUT / (label + ".stdout")).read_bytes()


def rpc(backend, code, label, timeout=60):
    args, dest = connection(backend)
    args += ["-T", dest, "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote(code)]
    return run_logged(args, label, timeout=timeout)


def archive():
    OUT.mkdir(parents=True, exist_ok=False)
    code = '''import hashlib,json,socket,subprocess
from pathlib import Path
assert socket.gethostname()=='MZ73'
root=Path(STAGE);root.mkdir(exist_ok=False)
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(8388608),b''):h.update(chunk)
 return h.hexdigest()
assert digest(Path('/'+MODEL))==MODEL_SHA
paths=[SITE,PYTHON_PKGS,VENDOR,'usr/bin/python3.10','usr/lib/python3.10',MODEL]
argv=['tar','--exclude=__pycache__','--exclude=*.pyc','-I','gzip -1','-cf',str(root/'runtime.tgz'),'-C','/',*paths]
with (root/'tar.stdout').open('xb') as out,(root/'tar.stderr').open('xb') as err:
 p=subprocess.run(argv,stdout=out,stderr=err)
if p.returncode:raise RuntimeError('tar failed; inspect stage/tar.stderr')
record={'archive_sha256':digest(root/'runtime.tgz'),'archive_bytes':(root/'runtime.tgz').stat().st_size,'checkpoint_sha256':MODEL_SHA,'selected_paths':paths}
with (root/'runtime_manifest.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
'''
    constants = "\n".join(k + "=" + repr(v) for k, v in {"STAGE": STAGE, "MODEL": MODEL,
        "SITE": SITE, "PYTHON_PKGS": PYTHON_PKGS, "VENDOR": VENDOR, "MODEL_SHA": MODEL_SHA}.items())
    raw = rpc("aqcat_gpu", constants + "\n" + code, "runtime_archive", timeout=1800)
    import json
    write_json_exclusive(OUT / "runtime_manifest.json", json.loads(raw))
    print("ARCHIVED", raw.decode().strip(), flush=True)


def relay():
    rpc("buct2_gpu", "from pathlib import Path;import socket;assert socket.gethostname()=='pc-G7466-M6';p=Path(" + repr(REMOTE)
        + ");assert p.resolve().is_relative_to(Path('/home/sbq/sbq').resolve());assert not p.exists() or not any(p.iterdir());p.mkdir(exist_ok=True)", "runtime_target_v2")
    cfg = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]
    source, target = cfg["aqcat_gpu"]["ssh"], cfg["buct2_gpu"]["ssh"]["alias"]
    args = ["scp", "-3", "-i", source["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12"]
    # scp URI consumes the first slash as its separator; retain another for an absolute remote path.
    uri = "scp://" + source["user"] + "@" + source["host"] + ":" + str(source["port"]) + "/" + STAGE + "/"
    run_logged(args + [uri + "runtime_manifest.json", target + ":" + REMOTE + "/runtime_manifest.json"], "manifest_relay_v2", timeout=60)
    run_logged(args + [uri + "runtime.tgz", target + ":" + REMOTE + "/runtime.tgz"], "runtime_relay", timeout=3600)
    print("RELAYED_VIA_WORK; remote checksum/extraction still required", flush=True)


def unpack():
    expected = load_json_object(OUT / "runtime_manifest.json")["archive_sha256"]
    code = '''import hashlib,json,socket,tarfile
from pathlib import Path
root=Path(REMOTE);assert socket.gethostname()=='pc-G7466-M6'
h=hashlib.sha256()
with (root/'runtime.tgz').open('rb') as f:
 for block in iter(lambda:f.read(8388608),b''):h.update(block)
assert h.hexdigest()==SHA
target=root/'deps';target.mkdir(exist_ok=False);omitted=[]
def portable_filter(member,destination):
 if member.name=='usr/lib/python3.10/sitecustomize.py' and member.issym() and member.linkname=='/etc/python3.10/sitecustomize.py':
  omitted.append({'path':member.name,'reason':'source Ubuntu apport exception-report hook only;not a numerical dependency'})
  return None
 return tarfile.data_filter(member,destination)
with tarfile.open(root/'runtime.tgz','r:gz') as archive:
 archive.extractall(target,filter=portable_filter)
model=target/MODEL;h=hashlib.sha256(model.read_bytes()).hexdigest();assert h==MODEL_SHA
print(json.dumps({'status':'EXTRACTED_BYTE_BOUND','archive_sha256':SHA,'checkpoint_sha256':h,'omitted_OS_only_symlinks':omitted}))
'''
    constants = "\n".join(k + "=" + repr(v) for k, v in {"REMOTE": REMOTE, "SHA": expected,
        "MODEL": MODEL, "MODEL_SHA": MODEL_SHA}.items())
    print(rpc("buct2_gpu", constants + "\n" + code, "runtime_unpack", timeout=1200).decode(), flush=True)


def split_archive():
    code = '''import hashlib,json,subprocess
from pathlib import Path
root=Path(STAGE);parts=root/'parts';parts.mkdir(exist_ok=False)
subprocess.run(['split','-b','536870912','-d','-a','2',str(root/'runtime.tgz'),str(parts/'part_')],check=True)
rows=[]
for p in sorted(parts.iterdir()):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8388608),b''):h.update(chunk)
 rows.append({'name':p.name,'sha256':h.hexdigest(),'bytes':p.stat().st_size})
print(json.dumps({'parts':rows}))
'''
    import json
    raw = rpc("aqcat_gpu", "STAGE=" + repr(STAGE) + "\n" + code, "runtime_split", timeout=300)
    write_json_exclusive(OUT / "parts_manifest.json", json.loads(raw))
    print("SPLIT_HASHED", len(json.loads(raw)["parts"]), flush=True)


def parallel_relay():
    code = '''from pathlib import Path
root=Path(ROOT);assert root.resolve().is_relative_to(Path('/home/sbq/sbq').resolve())
p=root/'runtime.tgz';assert p.exists() and p.stat().st_size<TOTAL
p.rename(root/'runtime.single_stream_partial.tgz')
(root/'parts').mkdir(exist_ok=False)
'''
    total = load_json_object(OUT / "runtime_manifest.json")["archive_bytes"]
    rpc("buct2_gpu", "ROOT=" + repr(REMOTE) + "\nTOTAL=" + repr(total) + "\n" + code, "preserve_partial_stream")
    cfg = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]
    source, target = cfg["aqcat_gpu"]["ssh"], cfg["buct2_gpu"]["ssh"]["alias"]
    args = ["scp", "-3", "-i", source["identity_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12"]
    uri = "scp://" + source["user"] + "@" + source["host"] + ":" + str(source["port"]) + "/" + STAGE + "/parts/"
    def transfer(row):
        name = row["name"]
        run_logged(args + [uri + name, target + ":" + REMOTE + "/parts/" + name], "relay_" + name, timeout=2400)
        return name
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name in pool.map(transfer, load_json_object(OUT / "parts_manifest.json")["parts"]):
            print("PART_RELAYED", name, flush=True)


def assemble():
    code = '''import hashlib,json
from pathlib import Path
root=Path(ROOT);whole=hashlib.sha256()
with (root/'runtime.tgz').open('xb') as out:
 for row in ROWS:
  p=root/'parts'/row['name'];h=hashlib.sha256()
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(8388608),b''):h.update(chunk);whole.update(chunk);out.write(chunk)
  if p.stat().st_size!=row['bytes'] or h.hexdigest()!=row['sha256']:raise ValueError('part bytes changed')
if whole.hexdigest()!=SHA:raise ValueError('assembled archive changed')
print(json.dumps({'status':'ASSEMBLED_HASH_PASS','sha256':whole.hexdigest()}))
'''
    constants = "\n".join(k + "=" + repr(v) for k, v in {"ROOT": REMOTE,
        "ROWS": load_json_object(OUT / "parts_manifest.json")["parts"],
        "SHA": load_json_object(OUT / "runtime_manifest.json")["archive_sha256"]}.items())
    print(rpc("buct2_gpu", constants + "\n" + code, "runtime_assemble", timeout=300).decode(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("archive", "relay", "unpack", "split", "parallel", "assemble"))
    {"archive": archive, "relay": relay, "unpack": unpack, "split": split_archive,
     "parallel": parallel_relay, "assemble": assemble}[parser.parse_args().phase]()
