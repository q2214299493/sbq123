"""Terminal recovery preserves failed attempts and verifies original file bytes."""
import io
import json
import subprocess
import tarfile

import pytest

from archive.fe110_scratch512_20261028 import collect_results as recovery
from scripts.artifact_io import sha256_bytes


def setup_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(recovery, "ROOT", tmp_path)
    (tmp_path / "output/package").mkdir(parents=True)
    (tmp_path / "output/package/sequence_request.json").write_bytes(b'{"frozen": 1}\n')
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/execution_backends.yaml").write_text(
        "backends:\n  aqcat_gpu:\n    ssh:\n      identity_file: fake-key-path\n      port: 22\n      user: fixture\n      host: fixture.invalid\n", encoding="utf-8")


def returned_archive(*, bad_hash=False):
    data = b"unchanged checkpoint fixture bytes\n"
    manifest = {"files": [{"path": "nequip_v2/output/best.ckpt", "bytes": len(data),
        "sha256": "f" * 64 if bad_hash else sha256_bytes(data)}],
        "models": {"finetune_best": {"kind": "budget_stopped_partial_development_selected_snapshot"}},
        "checkpoint_inventory": []}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, value in [("__collection_manifest__.json", json.dumps(manifest).encode()),
                            (manifest["files"][0]["path"], data)]:
            info = tarfile.TarInfo(name)
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))
    return stream.getvalue(), data


@pytest.mark.parametrize("bad_hash", [False, True])
def test_recovery_hash_verification_and_partial_status(tmp_path, monkeypatch, bad_hash):
    setup_recovery(tmp_path, monkeypatch)
    blob, original = returned_archive(bad_hash=bad_hash)

    def run(args, **kwargs):
        assert args[0] == "ssh" and "CUDA_VISIBLE_DEVICES=-1" in args[-1]
        assert "-vv" in args and kwargs["check"] is False
        kwargs["stdout"].write(blob)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(recovery.subprocess, "run", run)
    target = tmp_path / "output/terminal_recovery_20261028_v1"
    if bad_hash:
        with pytest.raises(ValueError, match="hash differs"):
            recovery.collect()
        assert not (target / "collection.json").exists()
    else:
        recovery.collect()
        assert (target / "returned/nequip_v2/output/best.ckpt").read_bytes() == original
        receipt = json.loads((target / "collection.json").read_bytes())
        assert receipt["partial_FT_not_full20_epoch_candidate"] is True
        assert receipt["GPU_execution"] is False
    assert (target / "returned.tar").read_bytes() == blob


def test_failed_transport_retained_without_automatic_retry(tmp_path, monkeypatch):
    setup_recovery(tmp_path, monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        kwargs["stderr"].write(b"Exceeded MaxStartups")
        return subprocess.CompletedProcess(args, 255)

    monkeypatch.setattr(recovery.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="preserve archive"):
        recovery.collect()
    target = tmp_path / "output/terminal_recovery_20261028_v1"
    assert len(calls) == 1
    assert json.loads((target / "transport.json").read_bytes())["returncode"] == 255
    assert (target / "transport.stderr").read_bytes() == b"Exceeded MaxStartups"
    with pytest.raises(FileExistsError):
        recovery.collect()
    assert len(calls) == 1


@pytest.mark.parametrize("attempt", [0, 10, True, "2"])
def test_invalid_attempt_cannot_create_output(tmp_path, monkeypatch, attempt):
    monkeypatch.setattr(recovery, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="explicit integer"):
        recovery.collect(attempt)
    assert not list(tmp_path.iterdir())


def test_remote_reader_compiles_without_executing():
    compile(recovery.PROGRAM, "<terminal-reader-fixture>", "exec")
    assert "torch.load(path,map_location='cpu'" in recovery.PROGRAM
    assert "training_completed.json" in recovery.PROGRAM
