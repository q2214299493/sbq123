import copy
import hashlib
import io
import tarfile

import pytest

from scripts.adsorption import direct_gpu_batch as guard
from archive.fe110_training512_gpu0_20261027.collect import extract_returned


def contract():
    row = {"pid": 101, "uid": 1007, "start_ticks": 900, "script": "wsgi_recommender.py"}
    return {"mode": "resident_service_allowlist", "allowed_processes": [row], "max_training_memory_MiB": 16384}


def test_default_gpu_contract_still_requires_no_existing_processes():
    with pytest.raises(ValueError, match="existing compute"):
        guard.shared_gpu_processes({}, [101])
    guard.shared_gpu_processes({}, [])


def test_exact_resident_identity_can_share(monkeypatch):
    sharing = contract()
    monkeypatch.setattr(guard, "gpu_process_identity", lambda pid: sharing["allowed_processes"][0])
    guard.shared_gpu_processes({"gpu_sharing": sharing}, [101])
    guard.shared_gpu_processes({"gpu_sharing": sharing}, [])


def test_new_process_is_not_implicitly_allowed():
    with pytest.raises(ValueError, match="new or its identity"):
        guard.shared_gpu_processes({"gpu_sharing": contract()}, [202])


@pytest.mark.parametrize("field,value", [("uid", 1008), ("start_ticks", 901), ("script", "training.py")])
def test_pid_reuse_or_script_change_is_rejected(monkeypatch, field, value):
    sharing = contract()
    changed = copy.deepcopy(sharing["allowed_processes"][0])
    changed[field] = value
    monkeypatch.setattr(guard, "gpu_process_identity", lambda pid: changed)
    with pytest.raises(ValueError, match="identity changed"):
        guard.shared_gpu_processes({"gpu_sharing": sharing}, [101])


@pytest.mark.parametrize("field,value", [("mode", "share_everything"), ("max_training_memory_MiB", 24000),
    ("max_training_memory_MiB", 0), ("max_training_memory_MiB", True), ("allowed_processes", [])])
def test_malformed_or_expanded_sharing_contract_rejected(field, value):
    sharing = contract()
    sharing[field] = value
    with pytest.raises(ValueError):
        guard.shared_gpu_processes({"gpu_sharing": sharing}, [])


@pytest.mark.parametrize("path,bad_hash,duplicate", [("candidate.pt", False, False),
    ("../escape", False, False), ("candidate.pt", True, False), ("candidate.pt", False, True)])
def test_returned_bytes_are_confined_hash_bound_and_not_overwritten(tmp_path, path, bad_hash, duplicate):
    content = b"synthetic test bytes;not a model"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for _ in range(2 if duplicate else 1):
            info = tarfile.TarInfo(path)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    manifest = {"files": [{"path": path, "bytes": len(content),
                          "sha256": "0" * 64 if bad_hash else hashlib.sha256(content).hexdigest()}]}
    if path.startswith("../") or bad_hash or duplicate:
        with pytest.raises(ValueError):
            extract_returned(stream.getvalue(), manifest, tmp_path / "returned")
    else:
        extract_returned(stream.getvalue(), manifest, tmp_path / "returned")
        assert (tmp_path / "returned/candidate.pt").read_bytes() == content
