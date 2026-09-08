"""Write reaction-ID provenance mapping for later result parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MappingEntry:
    """Trace one generated reaction back to the kinetic dataset and VASP."""

    reaction_id: str
    catkinas_id: int
    dataset_record_index: int
    source_path: str | None
    validation_status: str


def write_mapping(entries: list[MappingEntry], path: str | Path) -> Path:
    """Write deterministic reaction mapping as UTF-8 JSON."""

    mapping = {
        entry.reaction_id: {
            "catkinas_id": entry.catkinas_id,
            "dataset_record_index": entry.dataset_record_index,
            "source_path": entry.source_path,
            "validation_status": entry.validation_status,
        }
        for entry in entries
    }
    output_path = Path(path)
    output_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
