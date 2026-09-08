"""Typed unified schema for parsed external simulation results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ResultStatus = Literal["SUCCESS", "FAILED", "PARTIAL", "NOT_AVAILABLE"]


@dataclass(frozen=True)
class Conditions:
    """Explicitly reported simulation conditions."""

    temperature: float | None = None
    pressure: float | None = None


@dataclass(frozen=True)
class ResultSource:
    """Filesystem provenance of parsed values."""

    path: str = ""


@dataclass(frozen=True)
class SimulationResult:
    """Unified result values without interpretation or ranking."""

    simulation_id: str
    software: str
    status: ResultStatus
    conditions: Conditions = field(default_factory=Conditions)
    coverage: dict[str, float] = field(default_factory=dict)
    reaction_rates: dict[str, float] = field(default_factory=dict)
    tof: float | None = None
    selectivity: dict[str, float] = field(default_factory=dict)
    source: ResultSource = field(default_factory=ResultSource)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result record."""

        return asdict(self)
