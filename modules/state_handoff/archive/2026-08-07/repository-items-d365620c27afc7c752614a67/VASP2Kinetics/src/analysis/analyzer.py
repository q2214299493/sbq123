"""Build a typed, non-interpretive summary from simulation_result.json."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..exceptions import AnalysisError
from .ranking import RankedCoverage, RankedReaction, rank_coverage, rank_reaction_rates

LOGGER = logging.getLogger("vasp2kinetics.analysis")
NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True)
class AnalysisSummary:
    """Existing scalar and sorted coverage/selectivity results."""

    tof: float | None
    main_species: tuple[RankedCoverage, ...]
    selectivity: dict[str, float] | str

    def to_dict(self) -> dict[str, object]:
        """Return the exact Phase 9 summary keys."""

        return {
            "TOF": self.tof,
            "main_species": [
                {"species": item.species, "coverage": item.coverage}
                for item in self.main_species
            ],
            "selectivity": self.selectivity,
        }


@dataclass(frozen=True)
class AnalysisResult:
    """Phase 9 result without scientific interpretation."""

    simulation_id: str
    software: str
    summary: AnalysisSummary
    reaction_analysis: tuple[RankedReaction, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable Phase 9 record."""

        return {
            "simulation_id": self.simulation_id,
            "software": self.software,
            "summary": self.summary.to_dict(),
            "reaction_analysis": [
                {
                    "reaction_id": item.reaction_id,
                    "rate": item.rate,
                    "relative_contribution": item.relative_contribution,
                }
                for item in self.reaction_analysis
            ],
        }


def load_simulation_result(path: str | Path) -> dict[str, Any]:
    """Read one JSON object without modifying or supplementing its values."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise AnalysisError(f"SIMULATION_RESULT_NOT_FOUND: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"SIMULATION_RESULT_INVALID_JSON: {source}") from exc
    except OSError as exc:
        raise AnalysisError(f"SIMULATION_RESULT_READ_ERROR: {source}") from exc
    if not isinstance(raw, dict):
        raise AnalysisError("SIMULATION_RESULT_ROOT_NOT_OBJECT")
    LOGGER.info("Loaded simulation result: %s", source)
    return raw


def _optional_number(value: object, field: str) -> float | None:
    """Validate one optional finite numeric field."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisError(f"INVALID_NUMERIC_FIELD: {field}")
    number = float(value)
    if not math.isfinite(number):
        raise AnalysisError(f"NON_FINITE_NUMERIC_FIELD: {field}")
    return number


def _numeric_mapping(raw: object, field: str) -> dict[str, float]:
    """Validate one optional string-to-number mapping."""

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AnalysisError(f"INVALID_MAPPING_FIELD: {field}")
    parsed: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise AnalysisError(f"INVALID_MAPPING_KEY: {field}")
        number = _optional_number(value, f"{field}.{key}")
        if number is None:
            raise AnalysisError(f"MISSING_NUMERIC_VALUE: {field}.{key}")
        parsed[key] = number
    return parsed


def analyze_simulation_data(raw: dict[str, Any]) -> AnalysisResult:
    """Extract only present simulation values and calculate simple ordering."""

    simulation_id = raw.get("simulation_id", "")
    software = raw.get("software", "")
    if not isinstance(simulation_id, str) or not isinstance(software, str):
        raise AnalysisError("INVALID_SIMULATION_ID_OR_SOFTWARE")

    coverage = _numeric_mapping(raw.get("coverage"), "coverage")
    rates = _numeric_mapping(raw.get("reaction_rates"), "reaction_rates")
    selectivity_values = _numeric_mapping(raw.get("selectivity"), "selectivity")
    selectivity: dict[str, float] | str = (
        selectivity_values if selectivity_values else NOT_AVAILABLE
    )
    result = AnalysisResult(
        simulation_id=simulation_id,
        software=software,
        summary=AnalysisSummary(
            tof=_optional_number(raw.get("tof"), "tof"),
            main_species=tuple(rank_coverage(coverage)),
            selectivity=selectivity,
        ),
        reaction_analysis=tuple(rank_reaction_rates(rates)),
    )
    LOGGER.info(
        "Analyzed simulation result: simulation_id=%s reactions=%d species=%d",
        simulation_id or NOT_AVAILABLE,
        len(result.reaction_analysis),
        len(result.summary.main_species),
    )
    return result


def analyze_simulation_result(path: str | Path) -> AnalysisResult:
    """Load and analyze one simulation_result.json file."""

    return analyze_simulation_data(load_simulation_result(path))
