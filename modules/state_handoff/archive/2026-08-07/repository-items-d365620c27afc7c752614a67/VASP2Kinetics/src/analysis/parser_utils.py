"""Shared strict readers for Phase 8 text exports and provenance."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .result_schema import ResultStatus


class ParseFormatError(ValueError):
    """A stable parser error code for malformed existing data."""


@dataclass(frozen=True)
class InputContext:
    """Resolved parser input and Phase 7 provenance."""

    source_path: Path
    simulation_id: str


def _number(token: str, code: str) -> float:
    """Parse one finite numeric token or raise a coded format error."""

    try:
        value = float(token)
    except ValueError as exc:
        raise ParseFormatError(code) from exc
    if not math.isfinite(value):
        raise ParseFormatError(code)
    return value


def read_key_value_file(path: Path, code: str) -> dict[str, float]:
    """Read non-empty `label value` records with comments allowed."""

    values: dict[str, float] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ParseFormatError(f"{code}_READ_ERROR") from exc
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or parts[0] in values:
            raise ParseFormatError(f"{code}_FORMAT_ERROR:{line_number}")
        values[parts[0]] = _number(
            parts[1],
            f"{code}_INVALID_NUMBER:{line_number}",
        )
    if not values:
        raise ParseFormatError(f"{code}_EMPTY")
    return values


def read_scalar_file(path: Path, code: str) -> float:
    """Read exactly one finite numeric token from a text file."""

    try:
        tokens = [
            token
            for line in path.read_text(encoding="utf-8").splitlines()
            for token in line.split("#", 1)[0].split()
        ]
    except OSError as exc:
        raise ParseFormatError(f"{code}_READ_ERROR") from exc
    if len(tokens) != 1:
        raise ParseFormatError(f"{code}_FORMAT_ERROR")
    return _number(tokens[0], f"{code}_INVALID_NUMBER")


def resolve_input_context(input_path: Path, expected_files: set[str]) -> InputContext:
    """Follow only explicit Phase 7 input provenance; never search recursively."""

    run_status_path = input_path / "run_status.json"
    simulation_id = ""
    source_path = input_path
    if not run_status_path.is_file():
        return InputContext(source_path, simulation_id)
    try:
        raw = json.loads(run_status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ParseFormatError("RUN_STATUS_FORMAT_ERROR") from exc
    if not isinstance(raw, dict):
        raise ParseFormatError("RUN_STATUS_FORMAT_ERROR")
    status = raw.get("status")
    simulation_id_value = raw.get("simulation_id", "")
    source_value = raw.get("input_path")
    if not isinstance(simulation_id_value, str) or not isinstance(source_value, str):
        raise ParseFormatError("RUN_STATUS_FORMAT_ERROR")
    if status != "SUCCESS":
        raise ParseFormatError(f"SIMULATION_RUN_{status or 'UNKNOWN'}")
    simulation_id = simulation_id_value
    if not any((input_path / name).is_file() for name in expected_files):
        source_path = Path(source_value).expanduser().resolve()
        if not source_path.is_dir():
            raise ParseFormatError("SOURCE_OUTPUT_DIRECTORY_NOT_FOUND")
    return InputContext(source_path, simulation_id)


def load_reaction_mapping(path: Path, id_field: str) -> tuple[dict[str, str], set[str]]:
    """Load a strict reverse software-ID to internal reaction-ID mapping."""

    if not path.is_file():
        raise ParseFormatError("MAPPING_FILE_NOT_FOUND")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ParseFormatError("MAPPING_FORMAT_ERROR") from exc
    if not isinstance(raw, dict):
        raise ParseFormatError("MAPPING_FORMAT_ERROR")
    reverse: dict[str, str] = {}
    reaction_ids: set[str] = set()
    for reaction_id, entry in raw.items():
        if not isinstance(reaction_id, str) or not reaction_id or not isinstance(entry, dict):
            raise ParseFormatError("MAPPING_FORMAT_ERROR")
        software_id = entry.get(id_field)
        if isinstance(software_id, bool) or not isinstance(software_id, int):
            raise ParseFormatError("MAPPING_FORMAT_ERROR")
        key = str(software_id)
        if software_id <= 0 or key in reverse:
            raise ParseFormatError("MAPPING_FORMAT_ERROR")
        reverse[key] = reaction_id
        reaction_ids.add(reaction_id)
    return reverse, reaction_ids


def map_reaction_values(
    values: dict[str, float],
    reverse_mapping: dict[str, str],
    reaction_ids: set[str],
) -> dict[str, float]:
    """Replace software IDs with existing reaction IDs without renumbering."""

    mapped: dict[str, float] = {}
    for key, value in values.items():
        reaction_id = key if key in reaction_ids else reverse_mapping.get(key)
        if reaction_id is None or reaction_id in mapped:
            raise ParseFormatError(f"REACTION_MAPPING_NOT_FOUND:{key}")
        mapped[reaction_id] = value
    return mapped


def result_status(available: int, required: int, fatal: bool) -> ResultStatus:
    """Derive only the explicit Phase 8 availability status."""

    if fatal:
        return "FAILED"
    if available == 0:
        return "NOT_AVAILABLE"
    return "SUCCESS" if available == required else "PARTIAL"
