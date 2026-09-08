from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 digest for an in-memory byte string."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json(payload: Any) -> bytes:
    """Serialize a value deterministically for hash-bound artifacts."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(payload: Any) -> str:
    """Hash a JSON value using the repository canonical representation."""
    return sha256_bytes(canonical_json(payload))


def source_file_manifest(paths: list[Path]) -> list[dict[str, str]]:
    """Bind a generated artifact to the current, existing source files."""
    unique = sorted({path.resolve() for path in paths if path.is_file()}, key=str)
    return [{"path": str(path), "sha256": sha256_file(path)} for path in unique]


def source_file_manifest_valid(payload: dict[str, Any]) -> bool:
    sources = payload.get("source_files")
    if not isinstance(sources, list) or not sources:
        return False
    for source in sources:
        if not isinstance(source, dict):
            return False
        path = Path(str(source.get("path", "")))
        if not path.is_file() or source.get("sha256") != sha256_file(path):
            return False
    return True


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


def write_json(path: Path, payload: Any, *, ensure_ascii: bool = False) -> Path:
    """Write one JSON artifact through the canonical atomic writer."""

    return write_json_atomic(path, payload, ensure_ascii=ensure_ascii)


def write_json_atomic(path: Path, payload: Any, *, ensure_ascii: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=ensure_ascii)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def require_sha256(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError(f"{label} is not a SHA-256 digest")
    return normalized
