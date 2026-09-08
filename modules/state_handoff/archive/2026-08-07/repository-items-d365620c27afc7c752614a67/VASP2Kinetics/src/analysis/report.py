"""Render and persist a factual Markdown simulation report."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..exceptions import AnalysisError
from .analyzer import AnalysisResult, NOT_AVAILABLE

LOGGER = logging.getLogger("vasp2kinetics.analysis")
_TOKENS = (
    "{{SYSTEM_INFORMATION}}",
    "{{VALIDATION_STATUS}}",
    "{{SIMULATION_RESULTS}}",
    "{{REACTION_RATE_RANKING}}",
    "{{DATA_SOURCE}}",
    "{{LIMITATIONS}}",
)


def _escape(value: object) -> str:
    """Escape a value for a Markdown table cell."""

    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value: float | None) -> str:
    """Format one optional numeric value for the report."""

    return NOT_AVAILABLE if value is None else f"{value:.12g}"


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    """Render a compact Markdown table."""

    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _simulation_results(result: AnalysisResult) -> str:
    """Render TOF, coverage, and selectivity without interpretation."""

    coverage_rows = [
        (item.species, _number(item.coverage))
        for item in result.summary.main_species
    ]
    coverage = (
        _table(("Species", "Coverage"), coverage_rows)
        if coverage_rows
        else NOT_AVAILABLE
    )
    selectivity = result.summary.selectivity
    selectivity_table = (
        _table(
            ("Product", "Selectivity"),
            [(key, _number(value)) for key, value in sorted(selectivity.items())],
        )
        if isinstance(selectivity, dict)
        else NOT_AVAILABLE
    )
    return (
        f"- TOF: {_number(result.summary.tof)}\n\n"
        f"### Coverage\n\n{coverage}\n\n"
        f"### Selectivity\n\n{selectivity_table}"
    )


def _reaction_ranking(result: AnalysisResult) -> str:
    """Render descriptive reaction-rate ordering."""

    if not result.reaction_analysis:
        return NOT_AVAILABLE
    rows = [
        (
            index,
            item.reaction_id,
            _number(item.rate),
            _number(item.relative_contribution),
        )
        for index, item in enumerate(result.reaction_analysis, start=1)
    ]
    highest = result.reaction_analysis[0]
    return (
        f"The reaction with the highest calculated rate is "
        f"{_escape(highest.reaction_id)} ({_number(highest.rate)}).\n\n"
        + _table(
            ("Rank", "Reaction ID", "Rate", "Absolute-rate share"),
            rows,
        )
    )


def _source_path(raw: dict[str, Any]) -> str:
    """Return an explicit simulation source path when present."""

    source = raw.get("source")
    if not isinstance(source, dict):
        return NOT_AVAILABLE
    path = source.get("path")
    return path if isinstance(path, str) and path else NOT_AVAILABLE


def _limitations(result: AnalysisResult, raw: dict[str, Any]) -> str:
    """List missing fields and fixed interpretation boundaries."""

    missing: list[str] = []
    if result.summary.tof is None:
        missing.append("TOF is NOT_AVAILABLE in the simulation result.")
    if not result.summary.main_species:
        missing.append("Coverage is NOT_AVAILABLE in the simulation result.")
    if result.summary.selectivity == NOT_AVAILABLE:
        missing.append("Selectivity is NOT_AVAILABLE in the simulation result.")
    if not result.reaction_analysis:
        missing.append("Reaction rates are NOT_AVAILABLE in the simulation result.")
    if not result.simulation_id:
        missing.append("Simulation ID is NOT_AVAILABLE in the simulation result.")
    if not result.software:
        missing.append("Software is NOT_AVAILABLE in the simulation result.")
    if _source_path(raw) == NOT_AVAILABLE:
        missing.append("Simulation output source is NOT_AVAILABLE.")
    missing.extend(
        (
            "Surface information is NOT_AVAILABLE in the Phase 8 schema.",
            "Validation summary is NOT_AVAILABLE in the Phase 8 schema.",
            "VASP source is NOT_AVAILABLE in the Phase 8 schema.",
            "Kinetic dataset source is NOT_AVAILABLE in the Phase 8 schema.",
            "Absolute-rate share is an arithmetic ratio of absolute rates; it is not a mechanistic assignment.",
            "Reaction-rate ordering is descriptive only.",
            "Values retain the units of the source file because no unit fields are available.",
        )
    )
    return "\n".join(f"- {item}" for item in missing)


def render_report(
    result: AnalysisResult,
    raw: dict[str, Any],
    input_path: str | Path,
    template_path: str | Path,
) -> str:
    """Render all required sections from present data and explicit limitations."""

    template = Path(template_path).expanduser().resolve()
    try:
        text = template.read_text(encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(f"REPORT_TEMPLATE_READ_ERROR: {template}") from exc
    missing_tokens = [token for token in _TOKENS if token not in text]
    if missing_tokens:
        raise AnalysisError(
            "REPORT_TEMPLATE_MISSING_TOKEN: " + ", ".join(missing_tokens)
        )

    replacements = {
        "{{SYSTEM_INFORMATION}}": _table(
            ("Field", "Value"),
            [
                ("Surface", NOT_AVAILABLE),
                ("Software", result.software or NOT_AVAILABLE),
                ("Simulation ID", result.simulation_id or NOT_AVAILABLE),
            ],
        ),
        "{{VALIDATION_STATUS}}": (
            f"{NOT_AVAILABLE} - validation data are not present in "
            "simulation_result.json."
        ),
        "{{SIMULATION_RESULTS}}": _simulation_results(result),
        "{{REACTION_RATE_RANKING}}": _reaction_ranking(result),
        "{{DATA_SOURCE}}": _table(
            ("Source", "Path"),
            [
                ("Simulation result", Path(input_path).expanduser().resolve()),
                ("Simulation output", _source_path(raw)),
                ("VASP source", NOT_AVAILABLE),
                ("Kinetic dataset", NOT_AVAILABLE),
            ],
        ),
        "{{LIMITATIONS}}": _limitations(result, raw),
    }
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    LOGGER.info("Rendered report from template: %s", template)
    return text.rstrip() + "\n"


def write_analysis_report(
    result: AnalysisResult,
    raw: dict[str, Any],
    input_path: str | Path,
    output_path: str | Path,
    template_path: str | Path,
) -> tuple[Path, Path]:
    """Write analysis_result.json and report.md to the configured directory."""

    directory = Path(output_path).expanduser().resolve()
    analysis_path = directory / "analysis_result.json"
    report_path = directory / "report.md"
    report_text = render_report(result, raw, input_path, template_path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(report_text, encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(f"REPORT_OUTPUT_WRITE_ERROR: {directory}") from exc
    LOGGER.info("Analysis report written: result=%s report=%s", analysis_path, report_path)
    return analysis_path, report_path
