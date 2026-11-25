"""Repair package identity, canonical inputs and bounded executor wiring."""
import json

import pytest

from archive.fe110_five_c2_adsorption_20261006 import repair_vasp as repair
from scripts.neb_agent.submission import InputBundle
from scripts.ts_strategy_engine.execution_gate import validate_decision


def test_repair_hash_and_gate():
    run = repair.DEST / repair.NAME
    source = repair.PACKAGE / repair.NAME / "output/job_2176/POSCAR"
    assert source.read_bytes() == (run / "POSCAR").read_bytes()
    review = json.loads((repair.REVIEW / "review.json").read_text())
    assert review["selected"] == [repair.NAME]
    assert review["records"][0]["geometry"]["pass"]
    assert review["records"][0]["status"] == "UNIQUE_REVIEWED_GPU_CANDIDATE"
    report = json.loads((run / "submission_preflight.json").read_text())
    assert report["passed"]
    InputBundle.from_preflight(report).verify(run)
    decision = json.loads((run / "decision.json").read_text())
    validate_decision(decision)
    assert decision["ALLOWED_ACTIONS"] == ["SUBMIT_VASP"]
    incar = (run / "INCAR").read_text()
    assert "SIGMA = 0.2" in incar and "EDIFFG = -0.02" in incar
    script = (run / "script.lsf").read_text()
    assert "NP=32\n" in script and "NP_PER_NODE=32\n" in script


def test_completed_repair_review_is_immutable():
    with pytest.raises(FileExistsError, match="Preserve existing"):
        repair.review()


def test_empty_remote_optional_snapshot(monkeypatch):
    # Existing tar collector verifies every returned member. Missing optional
    # VASP outputs must not prevent an empty, valid snapshot archive.
    from archive.fe110_five_c2_adsorption_20261006.review_gpu_supplement import collect_tar
    import io
    import subprocess
    import tarfile

    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w"):
        pass
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, stream.getvalue(), b""))
    collect_tar([], repair.REVIEW / "unused_empty_snapshot", set())
