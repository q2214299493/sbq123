"""Bounded input and duplicate-submission guards; no models or remote execution."""
import json
from pathlib import Path

import pytest
from ase.io import read

from archive.fe110_five_c2_adsorption_20261006 import supplement_gpu_remote as remote
from scripts.aqcat25_handoff import validate_handoff
from scripts.artifact_io import sha256_file

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_v1"


def test_frozen_package_and_five_inputs():
    manifest = json.loads((PACKAGE / "batch_manifest.json").read_text())
    assert [r["name"] for r in manifest["handoffs"]] == ["01_extra1", "02_extra1", "02_extra2", "03_extra1", "03_extra2"]
    for item in manifest["files"]:
        assert sha256_file(PACKAGE / item["path"]) == item["sha256"]
    for item in manifest["handoffs"]:
        directory = PACKAGE / item["name"]
        validate_handoff(directory / "handoff.json", root=directory)
        doc = json.loads((directory / "handoff.json").read_text())
        atoms = read(directory / "POSCAR", format="vasp")
        assert doc["selective_dynamics"]["fixed_atom_indices_1based"] == list(range(1, 19))
        assert len(atoms.constraints) == 1
        assert not doc["adsorption"]["connectivity_constraints"]
        assert len(doc["adsorption"]["monitored_pairs"]) == (len(atoms)-45)*(len(atoms)-46)//2
        assert doc["model"]["max_steps"] == 80
        assert not doc["restrictions"]["submit_vasp"]


def test_remote_receipt_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, "EVIDENCE", tmp_path)
    (tmp_path / "submit.txt").write_text("existing receipt")
    monkeypatch.setattr(remote.subprocess, "run", lambda *a, **k: pytest.fail("No repeat SSH allowed"))
    with pytest.raises(FileExistsError, match="Inspect existing receipt"):
        remote.run("sbatch", "submit.txt")


def test_failed_remote_command_preserves_failure_without_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, "EVIDENCE", tmp_path)
    calls = []

    def failed(*args, **kwargs):
        calls.append(args)
        return remote.subprocess.CompletedProcess(args[0], 2, b"", b"specific preflight failure")

    monkeypatch.setattr(remote.subprocess, "run", failed)
    with pytest.raises(RuntimeError, match="do not retry unchanged"):
        remote.run("preflight", "preflight.txt")
    assert (tmp_path / "preflight.txt").read_bytes() == b"specific preflight failure"
    assert json.loads((tmp_path / "preflight.command.json").read_text())["exit_code"] == 2
    assert len(calls) == 1
