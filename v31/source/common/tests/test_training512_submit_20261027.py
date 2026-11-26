"""Duplicate-operation guards must stop before any SSH side effect."""
import pytest

from archive.fe110_training512_submit_20261027 import execute
from archive.fe110_training512_submit_20261027.inspect import inspect


def test_existing_direct_request_cannot_be_rebound(monkeypatch, tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "direct_request.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(execute, "PACKAGE", package)
    monkeypatch.setattr(execute, "OUTPUT", tmp_path / "evidence")
    monkeypatch.setattr(execute, "load_json_object", lambda _: pytest.fail("preparation reread after existing request"))
    with pytest.raises(FileExistsError, match="existing binding"):
        execute.bind()


def test_reserved_upload_cannot_call_ssh_again(monkeypatch, tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "direct_request.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "upload_reservation.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(execute, "PACKAGE", package)
    monkeypatch.setattr(execute, "OUTPUT", output)
    monkeypatch.setattr(execute, "verify", lambda *args: None)
    monkeypatch.setattr(execute, "call", lambda *args, **kwargs: pytest.fail("duplicate SSH mutation"))
    with pytest.raises(FileExistsError):
        execute.upload()


@pytest.mark.parametrize("name", ["../status", "status_../old", "status old", "launch"])
def test_invalid_snapshot_name_does_not_read_or_write(name):
    with pytest.raises(ValueError, match="checkpoint name"):
        inspect(name)
