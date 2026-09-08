"""Write unique, unmodified species labels for the CATKINAS adapter."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..kinetics.schema import ReactionRecord


def collect_species(records: Sequence[ReactionRecord]) -> list[str]:
    """Collect unique species in first-appearance order."""

    unique: list[str] = []
    seen: set[str] = set()
    for record in records:
        for species in [*record.species.reactant, *record.species.product]:
            if species not in seen:
                seen.add(species)
                unique.append(species)
    return unique


def write_species_file(records: Sequence[ReactionRecord], path: str | Path) -> Path:
    """Write one original species label per line."""

    output_path = Path(path)
    species = collect_species(records)
    text = "".join(f"{label}\n" for label in species)
    output_path.write_text(text, encoding="utf-8")
    return output_path
