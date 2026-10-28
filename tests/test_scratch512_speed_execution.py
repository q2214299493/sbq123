"""Terminal return must preserve failures and reject a different execution."""
import contextlib
import io
import json
import shlex

import pytest

from archive.fe110_scratch512_20261028 import speed_transport as transport
from scripts.artifact_io import sha256_file


@pytest.mark.parametrize("terminal_code", [0, 1])
def test_terminal_transport_returns_original_success_or_failure_records(tmp_path, monkeypatch, terminal_code):
    local = tmp_path / "local"
    package = local / "package"
    package.mkdir(parents=True)
    (package / "request.json").write_text("{}", encoding="utf-8")
    remote = tmp_path / "remote"
    (remote / "output").mkdir(parents=True)
    digest = sha256_file(package / "request.json")
    for name in ["producer_exit_record.json", "controller_exit_record.json"]:
        (remote / "output" / name).write_text(json.dumps({"exit_code": terminal_code, "request_sha256": digest}), encoding="utf-8")
    for name in ["launch_marker.json", "launch_receipt.json"]:
        (remote / name).write_text(json.dumps({"request_sha256": digest}), encoding="utf-8")
    monkeypatch.setattr(transport, "OUTPUT", local)
    monkeypatch.setattr(transport, "PACKAGE", package)
    monkeypatch.setattr(transport, "REMOTE", str(remote))

    def read_only_call(command, name, **kwargs):
        code = shlex.split(command)[-1]
        if name.endswith("_manifest"):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                exec(compile(code, "<fixture-manifest-reader>", "exec"), {})
            raw = captured.getvalue().encode()
        else:
            buffer = io.BytesIO()
            captured = io.TextIOWrapper(buffer, encoding="utf-8")
            with contextlib.redirect_stdout(captured):
                exec(compile(code, "<fixture-tar-reader>", "exec"), {})
            captured.flush()
            raw = buffer.getvalue()
            captured.detach()
        (local / (name + ".stdout")).write_bytes(raw)
        return raw

    monkeypatch.setattr(transport, "call", read_only_call)
    transport.collect("final")
    returned = json.loads((local / "returned/output/producer_exit_record.json").read_bytes())
    assert returned["exit_code"] == terminal_code
    assert (local / "collection_receipt.json").exists()


def test_terminal_reader_rejects_wrong_request_before_return(tmp_path, monkeypatch):
    local = tmp_path / "local"
    package = local / "package"
    package.mkdir(parents=True)
    (package / "request.json").write_text("{}", encoding="utf-8")
    remote = tmp_path / "remote"
    (remote / "output").mkdir(parents=True)
    for name in ["producer_exit_record.json", "controller_exit_record.json"]:
        (remote / "output" / name).write_text(json.dumps({"exit_code": 0, "request_sha256": "wrong"}), encoding="utf-8")
    monkeypatch.setattr(transport, "OUTPUT", local)
    monkeypatch.setattr(transport, "PACKAGE", package)
    monkeypatch.setattr(transport, "REMOTE", str(remote))

    def read_only_call(command, name, **kwargs):
        exec(compile(shlex.split(command)[-1], "<fixture-reader>", "exec"), {})

    monkeypatch.setattr(transport, "call", read_only_call)
    with pytest.raises(ValueError, match="binding changed"):
        transport.collect("final")
    assert not (local / "returned").exists()
