"""Write only existing reaction energy parameters."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..kinetics.schema import ReactionRecord


def _format_number(value: float) -> str:
    """Format a stored numeric value without changing precision semantics."""

    return format(value, ".15g")


def write_parameter_file(
    records: Sequence[ReactionRecord],
    path: str | Path,
) -> Path:
    """Write activation energy and optional reaction energy by reaction ID."""

    blocks: list[str] = []
    for record in records:
        activation_energy = record.energetics.Ea_forward
        if activation_energy is None:
            raise ValueError(
                f"Reaction {record.reaction_id} has no forward activation energy."
            )
        lines = [
            f"reaction_id: {record.reaction_id}",
            f"activation_energy: {_format_number(activation_energy)}",
        ]
        if record.energetics.E_reaction is not None:
            lines.append(
                f"reaction_energy: {_format_number(record.energetics.E_reaction)}"
            )
        blocks.append("\n".join(lines))

    output_path = Path(path)
    text = "\n\n".join(blocks)
    if text:
        text += "\n"
    output_path.write_text(text, encoding="utf-8")
    return output_path
