from __future__ import annotations

from pathlib import Path

from typing import Any

from scripts.aqcat25_handoff import validate_handoff

from scripts.artifact_io import sha256_file


def _empty_destination(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path

def _source_handoff(path_manifest_path: Path, manifest: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    source_path = _resolve(path_manifest_path.parent, manifest["source_handoff"]["path"])
    if sha256_file(source_path) != manifest["source_handoff"]["sha256"]:
        raise ValueError("GPU ML-NEB source handoff hash mismatch")
    return source_path, validate_handoff(source_path, root=source_path.parent)
