"""Command-line handlers for external simulator process management."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import AppConfig
from ..exceptions import LoggingError, RunnerError
from ..logging_context import phase_log
from .base_runner import BaseRunner, ExecutionResult
from .catkinas_runner import CatkinasRunner
from .zacros_runner import ZacrosRunner


def _execute_runner(
    runner: BaseRunner,
    input_path: Path,
    log_path: Path,
    logger: logging.Logger,
) -> int:
    """Execute one runner and translate process status to CLI exit status."""

    try:
        with phase_log(logger, log_path):
            result: ExecutionResult = runner.run(input_path)
    except (RunnerError, LoggingError) as exc:
        logger.error("%s", exc)
        return 2
    return 0 if result.status == "SUCCESS" else 1


def run_catkinas(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Run CATKINAS once with the configured command."""

    output_root = config.paths.output_path
    runner = CatkinasRunner(
        config.simulation.catkinas_command,
        config.simulation.timeout,
        output_root / "catkinas_run",
        output_root / "execution_history.json",
    )
    return _execute_runner(
        runner,
        args.input,
        config.logging.phase_files.simulation,
        logger,
    )


def run_zacros(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Run Zacros once with the configured command."""

    output_root = config.paths.output_path
    runner = ZacrosRunner(
        config.simulation.zacros_command,
        config.simulation.timeout,
        output_root / "zacros_run",
        output_root / "execution_history.json",
    )
    return _execute_runner(
        runner,
        args.input,
        config.logging.phase_files.simulation,
        logger,
    )
