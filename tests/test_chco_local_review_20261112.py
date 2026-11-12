"""Small source-integrity checks for the bounded review adapter;no remote execution."""
import hashlib
import io
import tarfile

import pytest

from archive.fe110_ch_co_local_review_20261112.review import extract_verified_archive


def make_archive(path, members):
    with tarfile.open(path, "w:gz") as target:
        for name, data in members:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            target.addfile(item, io.BytesIO(data))


def entry(name, data):
    return {"relative_path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_exact_source_bytes_and_manifest_are_verified(tmp_path):
    payload = b"exact source\r\nbytes\n"
    archive = tmp_path / "source.tar.gz"
    make_archive(archive, [("04/CONTCAR", payload)])
    _, seen = extract_verified_archive(archive, {"files": [entry("04/CONTCAR", payload)]},
        ["04/CONTCAR"], tmp_path / "raw")
    assert seen == {"04/CONTCAR"}
    assert (tmp_path / "raw/04/CONTCAR").read_bytes() == payload


@pytest.mark.parametrize("case", ["unlisted", "traversal", "duplicate", "hash_mismatch", "missing"])
def test_invalid_source_archive_is_rejected(tmp_path, case):
    payload = b"review source\n"
    name = "../outside" if case == "traversal" else "04/CONTCAR"
    manifest = {"files": [entry(name, b"different" if case == "hash_mismatch" else payload)]}
    members = [("unlisted" if case == "unlisted" else name, payload)]
    if case == "duplicate":
        members.append((name, payload))
    if case == "missing":
        members = []
    archive = tmp_path / "source.tar.gz"
    make_archive(archive, members)
    with pytest.raises(ValueError):
        extract_verified_archive(archive, manifest, [name], tmp_path / "raw")
    assert not (tmp_path / "outside").exists()
