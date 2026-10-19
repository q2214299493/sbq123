"""Deploy an additive CPU-only preflight adjustment; preserve all frozen training artifacts."""
import argparse
import io
import shlex
import tarfile
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json_exclusive

from .transport import EVIDENCE, PACKAGE, REMOTE, call
from archive.fe110_adsorption_training_comparison_20261019.prepare import copy_exact

LOCAL = EVIDENCE / "portable_preflight"


def prepare():
    LOCAL.mkdir(exist_ok=False)
    copy_exact(Path(__file__).with_name("portable_preflight.py"), LOCAL / "portable_preflight.py")
    request = {"document_kind": "numerical_roundtrip_CPU_preflight_adjustment", "direct_request_sha256": sha256_file(PACKAGE / "direct_request.json"),
        "adapter_sha256": sha256_file(LOCAL / "portable_preflight.py"), "coordinate_atol_A": 1e-12,
        "observed_max_coordinate_difference_A": 1.7763568394002505e-15,
        "diagnostic_sha256": sha256_file(EVIDENCE / "numeric_roundtrip_diagnostic.stdout"),
        "raw_forces_cell_PBC_tolerance": 0, "training_artifact_changes": [], "GPU_runs": 0}
    path = LOCAL / "preflight_adjustment.json"
    write_json_exclusive(path, request)
    write_json_exclusive(LOCAL / "preflight_adjustment_authorization.json", {"user_request": "跑", "user_authorized": True,
        "request_sha256": sha256_file(path), "scope": "CPU-only numerical input decoding validation within authorized GPU training preflight"})
    print(sha256_file(path))


def upload():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path in sorted(LOCAL.iterdir()):
            archive.add(path, arcname=path.name, recursive=False)
    program = r'''
import hashlib,json,shutil,socket,sys,tarfile
from pathlib import Path
root=Path(ROOT)
if socket.gethostname()!='MZ73' or not root.resolve().is_relative_to(Path('/home/sbq/sbq').resolve()):raise ValueError('bad host/root')
if (root/'direct_launch_marker.json').exists():raise ValueError('no change after launch')
if hashlib.sha256((root/'direct_request.json').read_bytes()).hexdigest()!=EXPECTED:raise ValueError('direct input changed')
allowed={'portable_preflight.py','preflight_adjustment.json','preflight_adjustment_authorization.json'}
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  if member.name not in allowed or not member.isfile():raise ValueError('unexpected supplement')
  with archive.extractfile(member) as source,(root/member.name).open('xb') as target:shutil.copyfileobj(source,target)
print(json.dumps({'status':'ADDITIVE_CPU_PREFLIGHT_DEPLOYED','original_files_overwritten':0}))
'''
    sha = sha256_file(PACKAGE / "direct_request.json")
    command = "env PYTHONDONTWRITEBYTECODE=1 python3 -c " + shlex.quote("ROOT=" + repr(REMOTE) + "\nEXPECTED=" + repr(sha) + "\n" + program)
    print(call(command, "portable_upload", stream.getvalue()).decode())


def check():
    sha = sha256_file(LOCAL / "preflight_adjustment.json")
    for arm in ("control", "treatment"):
        prefix = REMOTE + "/" + arm + "/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor"
        command = "env PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES= PYTHONPATH=" + shlex.quote(prefix)
        command += " /home/sbq/sbq/ml_ts_acceleration/venv/bin/python " + REMOTE + "/portable_preflight.py --arm " + arm + " --adjustment-sha256 " + sha
        raw = call(command, "portable_" + arm, timeout=300)
        print(raw.decode())
        program = "import sys;from pathlib import Path;sys.stdout.buffer.write(Path(" + repr(REMOTE + "/preflight_" + arm + ".json") + ").read_bytes())"
        call("env PYTHONDONTWRITEBYTECODE=1 python3 -", "portable_" + arm + "_canonical", program.encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "upload", "check"))
    arguments = parser.parse_args()
    {"prepare": prepare, "upload": upload, "check": check}[arguments.action]()
