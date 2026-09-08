"""Write traceable reaction and explicit site records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..kinetics.schema import ReactionRecord


@dataclass(frozen=True)
class MechanismEntry:
    """One admitted reaction and its optional user-provided site."""

    record: ReactionRecord
    site: str | None


def _format_number(value: float) -> str:
    """Format a stored numeric value without changing precision semantics."""

    return format(value, ".15g")


def write_mechanism_file(
    entries: Sequence[MechanismEntry],
    path: str | Path,
) -> Path:
    """Write reaction blocks without inferring missing site information."""

    blocks: list[str] = []
    for entry in entries:
        record = entry.record
        barrier = record.energetics.Ea_forward
        if barrier is None:
            raise ValueError(f"Reaction {record.reaction_id} has no barrier.")
        blocks.append(
            "\n".join(
                (
                    f"reaction_id: {record.reaction_id}",
                    f"reaction: {' + '.join(record.species.reactant)} -> "
                    f"{' + '.join(record.species.product)}",
                    f"sites: {entry.site if entry.site is not None else 'NOT_AVAILABLE'}",
                    f"barrier: {_format_number(barrier)}",
                )
            )
        )
    output_path = Path(path)
    text = "\n\n".join(blocks)
    output_path.write_text(f"{text}\n" if text else "", encoding="utf-8")
    return output_path
