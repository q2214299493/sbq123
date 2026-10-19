import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import sha256_file
from archive.fe110_adsorption_training_comparison_20261019 import execute


@pytest.fixture
def comparison(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    arms = {}
    for name in ("control", "treatment"):
        arm = package / name
        arm.mkdir()
        (arm / "data.txt").write_text("fixture only", encoding="utf-8")
        request = {"artifacts": [{"path": "data.txt", "sha256": sha256_file(arm / "data.txt")}]}
        path = arm / "training_request.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        arms[name] = sha256_file(path)
    document = {"arms": {name: {"sha256": sha} for name, sha in arms.items()}}
    parent = package / "comparison_request.json"
    parent.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(execute, "OUTPUT", package)
    monkeypatch.setattr(execute, "EVIDENCE", tmp_path / "evidence")
    monkeypatch.setattr(execute, "EXPECTED", sha256_file(parent))
    monkeypatch.setattr(execute, "ARMS", arms)
    return package, document


def test_exact_authority_preserves_request_and_rejects_duplicate(comparison):
    package, _ = comparison
    before = sha256_file(package / "comparison_request.json")
    execute.authorize()
    approval = json.loads((execute.EVIDENCE / "comparison_authorization.json").read_text(encoding="utf-8"))
    assert approval["authorizing_user_request"] == "运行" and approval["user_authorized"] is True
    assert approval["total_GPU_walltime_minutes_cap"] == 60
    assert approval["direct_execution_authorized"] is False
    assert approval["automatic_retry_authorized"] is False
    assert sha256_file(package / "comparison_request.json") == before
    for arm in execute.ARMS:
        child = json.loads((execute.EVIDENCE / f"{arm}_authorization.json").read_text(encoding="utf-8"))
        assert child["request_sha256"] == execute.ARMS[arm]
        assert child["comparison_authorization_sha256"] == sha256_file(execute.EVIDENCE / "comparison_authorization.json")
    with pytest.raises(FileExistsError):
        execute.authorize()


@pytest.mark.parametrize("target", ["comparison_request.json", "control/training_request.json", "treatment/data.txt"])
def test_tamper_never_authorizes(comparison, target):
    package, _ = comparison
    (package / target).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        execute.authorize()
    assert not execute.EVIDENCE.exists()


def test_preflight_reads_chinese_authority_as_utf8_and_does_not_submit(comparison, monkeypatch):
    execute.authorize()
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        assert command[0] == "ssh" and command[-1].endswith("python3 -")
        program = kwargs["input"].decode()
        assert "sbatch --" not in program and "torch.load" not in program
        kwargs["stdout"].write(json.dumps({"scheduler_available": False, "training_or_inference_run": False}).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(execute.subprocess, "run", fake_run)
    execute.probe()
    assert len(calls) == 1
    receipt = json.loads((execute.EVIDENCE / "live_preflight_receipt.json").read_text(encoding="utf-8"))
    assert receipt["GPU_submission_attempted"] is False and receipt["remote_files_written"] is False


def test_no_train_or_scheduler_service_mutation_in_probe():
    assert all(word not in execute.PROBE for word in ("sbatch --", "systemctl restart", "systemctl start", "torch.load", "torch.cuda"))
    assert "timeout=12" in execute.PROBE
    assert Path(execute.EVIDENCE).name == "adsorption_training_execution_20261019_v1"
