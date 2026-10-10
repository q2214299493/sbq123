import json
import sys

import pytest

from archive.fe110_five_c2_adsorption_20261006 import launch_adsorption_finetune as launch
from scripts.artifact_io import sha256_file


@pytest.fixture
def package(tmp_path, monkeypatch):
    package = tmp_path / "package"
    evidence = tmp_path / "evidence"
    package.mkdir()
    evidence.mkdir()
    (package / "runtime").mkdir()
    (package / "runtime/preflight_adsorption_finetune.py").write_text("# test fixture\n", encoding="utf-8")
    request = package / "training_request.json"
    request.write_text(json.dumps({"remote_package_root": launch.REMOTE, "artifacts": []}), encoding="utf-8")
    digest = sha256_file(request)
    approval = {"user_authorized": True, "request_sha256": digest,
                "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE", "user_message": "启动"}
    (evidence / "submission_authorization.json").write_text(json.dumps(approval, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(launch, "PACKAGE", package)
    monkeypatch.setattr(launch, "EVIDENCE", evidence)
    monkeypatch.setattr(launch, "EXPECTED", digest)
    monkeypatch.setattr(sys, "argv", ["launch", "submit"])
    return package, evidence, approval


def test_changed_request_rejected(package):
    (package[0] / "training_request.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Reviewed request changed"):
        launch.main()


def test_wrong_authorization_rejected(package):
    package[2]["request_sha256"] = "0" * 64
    (package[1] / "submission_authorization.json").write_text(json.dumps(package[2]), encoding="utf-8")
    with pytest.raises(AssertionError):
        launch.main()


def test_no_preflight_no_submission(package):
    with pytest.raises(FileNotFoundError, match="preflight_binding"):
        launch.main()
    assert not (package[1] / "local_submission_reservation.json").exists()


def test_missing_authorization_rejected(package):
    (package[1] / "submission_authorization.json").unlink()
    with pytest.raises(FileNotFoundError, match="authorization"):
        launch.main()
