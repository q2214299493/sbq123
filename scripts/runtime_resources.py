"""One resolver for reviewed package data and explicit repository-only context."""
from __future__ import annotations

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path, PurePosixPath, PureWindowsPath

_EXTRACTED = ExitStack()
atexit.register(_EXTRACTED.close)
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def require_repository_context(root: Path | None = None) -> Path:
    """Never guess an installed site-packages directory is a project workspace."""
    candidate = (root if root is not None else SOURCE_ROOT).resolve()
    if not (candidate / "pyproject.toml").is_file() or not (candidate / "configs/state_handoff.yaml").is_file():
        raise ValueError("REPOSITORY_CONTEXT_REQUIRED: supply an explicit source checkout/workspace root")
    return candidate


def resource_path(relative: str | Path, *, repository: Path | None = None) -> Path:
    """Resolve a resource from an explicit checkout or the installed distribution.

    Source originals remain authoritative. Wheel copies are build outputs, never
    a second maintained configuration. No cwd lookup or missing-file fallback.
    """
    name = str(relative).replace("\\", "/")
    if PureWindowsPath(name).drive or PurePosixPath(name).is_absolute() or ".." in name.split("/"):
        raise ValueError("RESOURCE_PATH_INVALID: expected a contained relative resource path")
    if repository is not None or (SOURCE_ROOT / "pyproject.toml").is_file():
        root = require_repository_context(repository)
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"RESOURCE_UNAVAILABLE: {name}")
        return path
    parts = PurePosixPath(name).parts
    if name.startswith("scripts/") and name.endswith(".py"):
        resource = files("scripts").joinpath(*parts[1:])
    else:
        resource = files("scripts").joinpath("_resources", *parts)
    if not resource.is_file():
        raise ValueError(f"REPOSITORY_CONTEXT_REQUIRED: resource is not packaged: {name}")
    return _EXTRACTED.enter_context(as_file(resource))


def explicit_database(path: Path, default: Path) -> Path:
    """Keep checkout defaults; installed callers must name their database."""
    if path == default:
        require_repository_context()
    return path
