"""Execution path and LSF identity rules; no evidence or gate dependencies."""
from __future__ import annotations

import re
from pathlib import Path
from .execution_decision import ScientificReadiness as ScientificReadiness


def require_relative_input_path(value: str) -> str:
    if not isinstance(value, str) or not value or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."}
        for part in value.split("/")
    ):
        raise ValueError("input path must be a safe relative path without traversal")
    return value


def require_remote_path(value: str, *, allow_root: bool = False) -> str:
    if value == "~/sbq" and allow_root:
        return value
    if not isinstance(value, str) or not value.startswith("~/sbq/"):
        raise ValueError("remote path must remain under ~/sbq")
    require_relative_input_path(value[len("~/sbq/"):])
    return value


def require_local_input(workdir: Path, relative: str) -> Path:
    require_relative_input_path(relative)
    root = workdir.resolve(strict=True)
    path = root / relative
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError("symlink or junction input paths are forbidden")
    if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
        raise ValueError("input path escapes workdir or is not a regular file")
    return path


def require_job_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("invalid LSF job id")
    return value


INITIAL_SUBMISSIONS = {
    "neb_pilot": (
        "READY_FOR_NEB_PILOT",
        "SUBMIT_DIAGNOSTIC_VASP",
        "SUBMIT_SHORT_ORDINARY_NEB_PILOT",
    ),
    "ordinary_neb": (
        "READY_FOR_ORDINARY_NEB_SUBMISSION",
        "SUBMIT_VASP",
        "SUBMIT_ORDINARY_NO_CLIMB_NEB",
    ),
    "diagnostic_static": (
        "READY_FOR_DIAGNOSTIC_SUBMISSION",
        "SUBMIT_DIAGNOSTIC_VASP",
        "SUBMIT_STATIC_DIAGNOSTIC",
    ),
}
