"""Write only existing activation and reaction energies."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..kinetics.schema import ReactionRecord


def _format_number(value: float) -> str:
    """Format a stored numeric value without changing precision semantics."""

    return format(value, ".15g")


def write_energetics_file(
    records: Sequence[ReactionRecord],
    path: str | Path,
) -> Path:
    """Write energy blocks without adding units or missing values."""

    blocks: list[str] = []
    for record in records:
        barrier = record.energetics.Ea_forward
        if barrier is None:
            raise ValueError(f"Reaction {record.reaction_id} has no barrier.")
        lines = [
            f"reaction_id: {record.reaction_id}",
            f"Ea: {_format_number(barrier)}",
        ]
        if record.energetics.E_reaction is not None:
            lines.append(
                f"E_reaction: {_format_number(record.energetics.E_reaction)}"
            )
        blocks.append("\n".join(lines))
    output_path = Path(path)
    text = "\n\n".join(blocks)
    output_path.write_text(f"{text}\n" if text else "", encoding="utf-8")
    return output_path
