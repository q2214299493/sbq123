"""Deterministic numeric ordering for Phase 9 report data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankedReaction:
    """One reported reaction rate and its arithmetic absolute-rate share."""

    reaction_id: str
    rate: float
    relative_contribution: float | None


@dataclass(frozen=True)
class RankedCoverage:
    """One explicitly reported species coverage."""

    species: str
    coverage: float


def rank_reaction_rates(reaction_rates: dict[str, float]) -> list[RankedReaction]:
    """Sort rates from highest to lowest without assigning mechanistic meaning."""

    denominator = sum(abs(rate) for rate in reaction_rates.values())
    ordered = sorted(reaction_rates.items(), key=lambda item: (-item[1], item[0]))
    return [
        RankedReaction(
            reaction_id=reaction_id,
            rate=rate,
            relative_contribution=(abs(rate) / denominator if denominator else None),
        )
        for reaction_id, rate in ordered
    ]


def rank_coverage(coverage: dict[str, float]) -> list[RankedCoverage]:
    """Sort reported coverages from highest to lowest without interpretation."""

    ordered = sorted(coverage.items(), key=lambda item: (-item[1], item[0]))
    return [
        RankedCoverage(species=species, coverage=value)
        for species, value in ordered
    ]
