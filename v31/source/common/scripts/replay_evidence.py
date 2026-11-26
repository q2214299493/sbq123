"""Locate sealed evidence after relocation, keeping original paths in signed records."""
import json
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]


def evidence_path(value):
    original = Path(value)
    recorded = PureWindowsPath(value)
    if not recorded.is_absolute():
        return original
    mounts = json.loads((ROOT / "evidence-mounts.json").read_bytes())
    for old, relative in mounts.items():
        base = PureWindowsPath(old)
        if not recorded.is_relative_to(base):
            continue
        suffix = recorded.relative_to(base)
        if ".." in suffix.parts:
            raise ValueError("Invalid recorded evidence path")
        target = (ROOT.parent / relative).resolve()
        path = target.joinpath(*suffix.parts).resolve()
        if not path.is_relative_to(target):
            raise ValueError("Evidence path escapes its mount")
        return path
    return original
