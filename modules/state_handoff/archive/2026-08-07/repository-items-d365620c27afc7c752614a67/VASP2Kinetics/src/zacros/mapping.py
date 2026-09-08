"""Write Zacros adapter IDs and source provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MappingEntry:
    """Trace a generated event to its reaction, VASP source, energy, and site."""

    reaction_id: str
    zacros_id: int
    dataset_record_index: int
    source_path: str | None
    activation_energy: float
    reaction_energy: float | None
    validation_status: str
    site: str | None


def write_mapping(entries: list[MappingEntry], path: str | Path) -> Path:
    """Write deterministic reaction mapping as UTF-8 JSON."""

    mapping = {
        entry.reaction_id: {
            "zacros_id": entry.zacros_id,
            "dataset_record_index": entry.dataset_record_index,
            "source_path": entry.source_path,
            "activation_energy": entry.activation_energy,
            "reaction_energy": entry.reaction_energy,
            "validation_status": entry.validation_status,
            "site": entry.site,
        }
        for entry in entries
    }
    output_path = Path(path)
    output_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
