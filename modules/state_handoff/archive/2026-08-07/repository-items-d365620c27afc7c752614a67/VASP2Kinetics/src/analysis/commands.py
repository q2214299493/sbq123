"""Command handlers for Phase 8 result parsing."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..exceptions import AnalysisError, LoggingError
from ..logging_context import phase_log
from .analyzer import analyze_simulation_data, load_simulation_result
from .catkinas_parser import parse_catkinas_result
from .result_schema import SimulationResult
from .result_writer import write_result_files
from .report import write_analysis_report
from .zacros_parser import parse_zacros_result

Parser = Callable[[str | Path], tuple[SimulationResult, dict[str, object]]]


def _run_parser(
    parser: Parser,
    input_path: Path,
    output_path: Path,
    log_path: Path,
    logger: logging.Logger,
) -> int:
    """Run one parser under the configured parser log and write its files."""

    try:
        with phase_log(logger, log_path):
            result, parser_log = parser(input_path)
            result_path, parser_log_path = write_result_files(
                result,
                parser_log,
                output_path,
            )
    except (AnalysisError, LoggingError) as exc:
        logger.error("%s", exc)
        return 2
    logger.info(
        "Simulation result parsed: status=%s result=%s log=%s",
        result.status,
        result_path,
        parser_log_path,
    )
    return 0 if result.status == "SUCCESS" else 1


def parse_catkinas_command(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Parse one CATKINAS run directory."""

    input_path = (
        args.input.expanduser().resolve()
        if args.input is not None
        else config.analysis.result_path / "catkinas_run"
    )
    return _run_parser(
        parse_catkinas_result,
        input_path,
        config.analysis.output_path,
        config.logging.phase_files.parser,
        logger,
    )


def parse_zacros_command(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Parse one Zacros run directory."""

    input_path = (
        args.input.expanduser().resolve()
        if args.input is not None
        else config.analysis.result_path / "zacros_run"
    )
    return _run_parser(
        parse_zacros_result,
        input_path,
        config.analysis.output_path,
        config.logging.phase_files.parser,
        logger,
    )


def analyze_command(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Create Phase 9 JSON and Markdown outputs from one simulation result."""

    try:
        with phase_log(logger, config.logging.phase_files.parser):
            raw = load_simulation_result(args.input)
            result = analyze_simulation_data(raw)
            analysis_path, report_path = write_analysis_report(
                result,
                raw,
                args.input,
                config.report.output_path,
                config.report.template_path,
            )
    except (AnalysisError, LoggingError) as exc:
        logger.error("%s", exc)
        return 2
    logger.info(
        "Phase 9 analysis complete: result=%s report=%s",
        analysis_path,
        report_path,
    )
    return 0
