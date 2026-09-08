"""Write unique, unmodified species labels for the Zacros adapter."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..kinetics.schema import ReactionRecord


def collect_species(records: Sequence[ReactionRecord]) -> list[str]:
    """Collect unique species in first-appearance order."""

    species: list[str] = []
    seen: set[str] = set()
    for record in records:
        for label in [*record.species.reactant, *record.species.product]:
            if label not in seen:
                seen.add(label)
                species.append(label)
    return species


def write_species_file(records: Sequence[ReactionRecord], path: str | Path) -> Path:
    """Write one original species label per line."""

    output_path = Path(path)
    output_path.write_text(
        "".join(f"{label}\n" for label in collect_species(records)),
        encoding="utf-8",
    )
    return output_path
