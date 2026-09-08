"""Write reaction equations and existing forward barriers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..kinetics.schema import ReactionRecord


def _format_number(value: float) -> str:
    """Format a stored numeric value without changing precision semantics."""

    return format(value, ".15g")


def write_reaction_file(
    records: Sequence[ReactionRecord],
    path: str | Path,
) -> Path:
    """Write traceable reaction blocks without changing species names."""

    blocks: list[str] = []
    for record in records:
        barrier = record.energetics.Ea_forward
        if barrier is None:
            raise ValueError(
                f"Reaction {record.reaction_id} has no forward activation energy."
            )
        reactant = " + ".join(record.species.reactant)
        product = " + ".join(record.species.product)
        blocks.append(
            "\n".join(
                (
                    f"reaction_id: {record.reaction_id}",
                    f"reaction: {reactant} = {product}",
                    f"barrier: {_format_number(barrier)}",
                )
            )
        )

    output_path = Path(path)
    text = "\n\n".join(blocks)
    if text:
        text += "\n"
    output_path.write_text(text, encoding="utf-8")
    return output_path
