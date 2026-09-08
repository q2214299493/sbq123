from __future__ import annotations

from pathlib import Path
from scripts.artifact_io import write_json

__all__ = ["ensure_dir", "write_json"]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
