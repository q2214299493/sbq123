"""Verify and atomically publish a role, with a kernel-owned per-target writer lock."""
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
from typing import Callable, Mapping
import uuid


def long_path(path: Path) -> Path:
    """Return a resolved native path, including extended-length Windows UNC paths."""
    path = Path(path).resolve()
    if os.name != "nt":
        return path
    text = str(path)
    if text.startswith("\\\\?\\"):
        return path
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def _writer_lock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def materialize(target: Path, manifest: Mapping[str, str], reader: Callable[[str], bytes]) -> Path:
    """Publish once. A retry reclaims only this target's recorded private staging area."""
    target = long_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy = target.with_name(target.name + ".lock")
    if legacy.exists():
        raise FileExistsError("Legacy writer lock requires ownership inspection: " + str(legacy))
    control = target.with_name("." + target.name + ".sbq123-lock")
    if control.is_symlink() or control.is_junction():
        raise ValueError("Unexpected materialization lock link")
    # Keep the inode stable across calls. Closing this descriptor releases the
    # kernel lock even after a crash. Unlinking it would allow concurrent writers.
    with control.open("a+b") as stream:
        _writer_lock(stream)
        if target.exists():
            raise FileExistsError(target)
        stream.seek(1)
        token = stream.read(33)
        if len(token) != 32:
            if len(token) >= 32 or any(c not in b"0123456789abcdef" for c in token):
                raise ValueError("Unrecognized staging ownership record")
            token = uuid.uuid4().hex.encode("ascii")
            stream.seek(0)
            stream.truncate()
            stream.write(b"1" + token)
            stream.flush()
            os.fsync(stream.fileno())
        if any(c not in b"0123456789abcdef" for c in token):
            raise ValueError("Invalid staging ownership record")
        stage = target.with_name("." + target.name + ".sbq123-" + token.decode("ascii"))
        if stage.is_symlink() or stage.is_junction():
            raise ValueError("Unexpected materialization staging link")
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        try:
            for name, digest in manifest.items():
                parts = PurePosixPath(name).parts
                if not parts or "\\" in name or PureWindowsPath(name).drive or PurePosixPath(name).is_absolute() or ".." in parts:
                    raise ValueError("Invalid release asset path")
                data = reader(name)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("Asset identity mismatch: " + name)
                out = stage.joinpath(*parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                with out.open("xb") as f:
                    f.write(data)
            stage.rename(target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return target
