"""Non-overwriting JSON registry for typed kinetic records."""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path

from ..exceptions import KineticDataError, RegistryError
from .schema import KineticDataset, ReactionRecord

LOGGER = logging.getLogger("vasp2kinetics.kinetics.registry")


class RegistryStatus(str, Enum):
    """Possible registration outcomes."""

    REGISTERED = "REGISTERED"
    DUPLICATE_ID = "DUPLICATE_ID"


def load(path: str | Path) -> KineticDataset:
    """Load the registry, or return an empty typed dataset when absent."""

    dataset_path = Path(path).expanduser().resolve()
    if not dataset_path.exists():
        return KineticDataset()
    if not dataset_path.is_file():
        raise RegistryError(f"Kinetic registry is not a file: {dataset_path}")
    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"Invalid JSON in kinetic registry: {dataset_path}") from exc
    except OSError as exc:
        raise RegistryError(f"Unable to read kinetic registry: {dataset_path}") from exc
    if not isinstance(raw, dict):
        raise RegistryError("Kinetic registry root must be a mapping.")
    try:
        return KineticDataset.from_dict(raw)
    except KineticDataError as exc:
        raise RegistryError(f"Invalid kinetic registry: {dataset_path}") from exc


def register(
    record: ReactionRecord,
    path: str | Path,
) -> RegistryStatus:
    """Append a record unless its reaction ID already exists."""

    dataset_path = Path(path).expanduser().resolve()
    dataset = load(dataset_path)
    if any(existing.reaction_id == record.reaction_id for existing in dataset.records):
        LOGGER.warning("Duplicate reaction ID rejected: %s", record.reaction_id)
        return RegistryStatus.DUPLICATE_ID

    updated = KineticDataset(
        records=[*dataset.records, record],
        schema_version=dataset.schema_version,
    )
    _write(updated, dataset_path)
    LOGGER.info("Registered reaction_id=%s in %s", record.reaction_id, dataset_path)
    return RegistryStatus.REGISTERED


def _write(dataset: KineticDataset, path: Path) -> None:
    """Atomically refresh the physical JSON file without replacing old records."""

    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(dataset.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        raise RegistryError(f"Unable to write kinetic registry: {path}") from exc
