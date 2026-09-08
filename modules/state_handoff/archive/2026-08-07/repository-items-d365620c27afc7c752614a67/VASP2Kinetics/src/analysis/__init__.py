"""Strict simulation-result parsing without scientific interpretation."""

from .catkinas_parser import parse_catkinas_result
from .analyzer import AnalysisResult, analyze_simulation_result
from .result_schema import SimulationResult
from .zacros_parser import parse_zacros_result

__all__ = [
    "AnalysisResult",
    "SimulationResult",
    "analyze_simulation_result",
    "parse_catkinas_result",
    "parse_zacros_result",
]
