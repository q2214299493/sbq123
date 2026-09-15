"""Stream to sunboquan python3: read-only runtime check; never writes/submits."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def query(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if len(result.stdout) + len(result.stderr) > 16000:
        raise ValueError("unexpectedly large preflight command output")
    return {"command": command, "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


binary = Path.home() / "soft/vasp541vtst/bin/vasp_std"
mpirun = shutil.which("mpirun")
if not mpirun:
    raise RuntimeError("MPI launcher missing after sourced site environment")
parent = Path.home() / "sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904"
target = parent / "h_migration_int06_mid_scf_chain_20260915"
old = parent / "h_migration_int06_mid_fixed_density_20260914"
potcar = Path.home() / "sbq/Fe110/potcars/Fe_C_O_H/POTCAR"
tail = b""
with (old / "vasp.out").open("rb") as handle:
    handle.seek(max(0, (old / "vasp.out").stat().st_size - 4096))
    tail = handle.read()
result = {
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "host": platform.node(), "server_alias": "sunboquan-codex",
    "python": {"version": platform.python_version(), "executable": sys.executable,
               "command": shutil.which("python3")},
    "executable": str(binary), "executable_sha256": digest(binary),
    "mpirun": mpirun, "mpirun_sha256": digest(mpirun),
    "libraries": query(["ldd", str(binary)]),
    "mpi_version": query([mpirun, "--version"]),
    "scheduler": query(["bjobs", "-a", "9755394"]),
    "potcar_sha256": digest(potcar), "target": str(target), "target_exists": target.exists(),
    "parent_writable": os.access(parent, os.W_OK),
    "source_input_hashes": {name: digest(old / name) for name in ("INCAR", "POSCAR", "KPOINTS", "POTCAR")},
    "source_output_sizes": {name: (old / name).stat().st_size
                            for name in ("OUTCAR", "OSZICAR", "CONTCAR", "WAVECAR", "CHGCAR")},
    "source_stdout_tail": tail.decode("utf-8", errors="replace"),
    "remote_writes": False, "vasp_executed": False, "mpi_calculation_executed": False,
}
# Imports needed by the zipapp, without launching its main or allocating MPI.
import base64  # noqa: E402,F401
import math  # noqa: E402,F401
import signal  # noqa: E402,F401
import struct  # noqa: E402,F401
import zipfile  # noqa: E402,F401
import zlib  # noqa: E402,F401

print(json.dumps(result, sort_keys=True))
