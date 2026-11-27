"""One resolver for reviewed package data and explicit repository-only context."""
from __future__ import annotations

import hashlib
import json
import atexit
import os
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path, PurePosixPath, PureWindowsPath

_EXTRACTED = ExitStack()
atexit.register(_EXTRACTED.close)
SOURCE_ROOT = Path(os.environ.get("SBQ123_ROLE_DATA", Path(__file__).resolve().parents[1])).resolve()


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
    if repository is not None:
        root = require_repository_context(repository)
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"RESOURCE_UNAVAILABLE: {name}")
        return path
    parts = PurePosixPath(name).parts
    from sbq123.common.compat import _active
    if name.startswith("scripts/") and name.endswith(".py") and _active is not None:
        mod = name[:-3].replace("/", ".")
        if mod in _active.paths:
            return _active.paths[mod][0]
    resource = files("sbq123.common").joinpath("resources", *parts)
    if _active is not None:
        override = files("sbq123." + _active.role).joinpath("resources", *parts)
        if override.is_file():
            resource = override
    if not resource.is_file() and _active is not None and os.environ.get("SBQ123_ROLE_DATA"):
        manifest = json.loads(files("sbq123." + _active.role).joinpath("_data_hashes.json").read_bytes())
        expected = manifest.get(name)
        path = SOURCE_ROOT.joinpath(*parts).resolve()
        if expected and path.is_relative_to(SOURCE_ROOT) and path.is_file():
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Changed historical role data: {name}")
            return path
    if not resource.is_file():
        raise ValueError(f"REPOSITORY_CONTEXT_REQUIRED: resource is not packaged: {name}")
    return _EXTRACTED.enter_context(as_file(resource))


def explicit_database(path: Path, default: Path) -> Path:
    """Keep checkout defaults; installed callers must name their database."""
    if path == default:
        require_repository_context()
    return path
