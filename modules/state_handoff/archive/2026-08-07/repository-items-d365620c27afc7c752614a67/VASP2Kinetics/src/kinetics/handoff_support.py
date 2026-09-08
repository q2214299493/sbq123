"""Low-level JSON, hashing, path, and finite-number handoff utilities."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, NoReturn

from ..exceptions import KineticDataError


@dataclass(frozen=True)
class HandoffValidationResult:
    """Structural and eligibility result for one immutable handoff document."""

    status: str
    eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible validation result."""

        return asdict(self)


def _reject_constant(value: str) -> NoReturn:
    """Reject JSON NaN and Infinity constants explicitly."""

    raise ValueError(f"NON_FINITE_JSON_CONSTANT:{value}")


def load_strict_json(path: Path) -> Any:
    """Load strict JSON from one file."""

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise KineticDataError(f"HANDOFF_JSON_READ_ERROR: {path}") from exc


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 of one existing file without loading it at once."""

    source = Path(path)
    digest = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise KineticDataError(f"HANDOFF_SOURCE_READ_ERROR: {source}") from exc
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    """Hash canonical UTF-8 JSON while rejecting non-finite numbers."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise KineticDataError("HANDOFF_CANONICAL_JSON_ERROR") from exc
    return hashlib.sha256(payload).hexdigest()


def resolve_contract_path(base: Path, value: str) -> Path:
    """Resolve one contract path relative to the handoff location."""

    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def find_nonfinite(value: Any, location: str, errors: list[str]) -> None:
    """Recursively reject non-finite programmatic numeric inputs."""

    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"NON_FINITE_NUMBER:{location}")
    elif isinstance(value, dict):
        for key, child in value.items():
            find_nonfinite(child, f"{location}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            find_nonfinite(child, f"{location}[{index}]", errors)
