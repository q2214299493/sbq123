"""Installed engineering controls shared by the Windows and Linux jobs."""
import ast
from hashlib import sha256
from importlib.resources import files
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from sbq123.common.artifacts.materialize import materialize
from sbq123.common.evidence.registry import dataset
from sbq123.common.workflow.process import run_bounded


@pytest.mark.parametrize("parent_stays", [False, True])
def test_timeout_after_launcher_start(tmp_path, parent_stays):
    started, finished = tmp_path / "started", tmp_path / "finished"
    worker = ("import pathlib,sys,time;pathlib.Path(sys.argv[1]).touch();"
              "time.sleep(4);pathlib.Path(sys.argv[2]).touch()")
    launcher = ("import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',*sys.argv[1:]]);"
                + ("time.sleep(15)" if parent_stays else ""))
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", launcher, worker, str(started), str(finished)],
                    timeout=3, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert started.exists()
    time.sleep(2)
    assert not finished.exists()


def test_interrupted_materialization(tmp_path):
    target = tmp_path / "role"
    marker = tmp_path / "live"
    worker = """import os,sys,time
from pathlib import Path
from sbq123.common.artifacts.materialize import materialize
def read(name):
    Path(sys.argv[2]).touch()
    time.sleep(60)
materialize(Path(sys.argv[1]), {"unfinished": "pending"}, read)
"""
    child = subprocess.Popen([sys.executable, "-c", worker, str(target), str(marker)])
    try:
        for _ in range(250):
            if marker.exists():
                break
            time.sleep(0.04)
        assert marker.exists()
        with pytest.raises(OSError):
            materialize(target, {}, lambda name: b"")
        assert not target.exists()
    finally:
        child.kill()
        child.wait(timeout=10)
    path = "/".join(["long-directory-name"] * 16 + ["value"])
    result = materialize(target, {path: sha256(b"ok").hexdigest()}, lambda name: b"ok")
    assert (result / path).read_bytes() == b"ok"
    assert set(p.name for p in tmp_path.iterdir()) == {"role", "live", ".role.sbq123-lock"}


def test_registry_and_archive_dependency_direction():
    root = files("sbq123.common")
    # These are the two original edges of the delayed import cycle.
    for f in ("kinetic_model/archive.py", "evidence/_records.py"):
        tree = ast.parse(root.joinpath(*f.split("/")).read_text(encoding="utf8"))
        assert not any(isinstance(n, ast.ImportFrom) and n.module == "sbq123.common.evidence.registry"
                       for n in ast.walk(tree))
    assert dataset("v31-closed-cycle").provenance == "archived_software_benchmark"
