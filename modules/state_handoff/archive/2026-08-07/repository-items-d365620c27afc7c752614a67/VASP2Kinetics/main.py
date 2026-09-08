"""Command-line entry point for VASP2Kinetics."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from src.adapter_commands import run_catkinas_generator, run_zacros_generator
from src.analysis.commands import (
    analyze_command,
    parse_catkinas_command,
    parse_zacros_command,
)
from src.cli_arguments import validate_arguments
from src.config import AppConfig, load_config
from src.exceptions import VASP2KineticsError
from src.kinetics.builder import (
    build_kinetic_record,
    load_reaction_definition,
    load_vasp_result,
)
from src.kinetics.registry import RegistryStatus, register
from src.kinetics.validator import validate_dataset, write_validation_report
from src.logging_config import configure_logging
from src.logging_context import phase_log
from src.runner.commands import run_catkinas, run_zacros
from src.vasp.parser import parse_vasp_case, write_vasp_result
from src.workflow.pipeline import run_workflow, show_workflow_status

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the application command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Parse VASP/results, manage kinetics, generate adapters, or run simulators."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to config.yaml.",
    )
    parser.add_argument(
        "--parse-vasp",
        type=Path,
        help="Read an existing VASP or NEB calculation directory.",
    )
    parser.add_argument(
        "--build-kinetics",
        action="store_true",
        help="Build and register one UNVERIFIED kinetic record.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate a kinetic dataset without modifying it.",
    )
    parser.add_argument(
        "--generate-catkinas",
        action="store_true",
        help="Generate static CATKINAS adapter files without running CATKINAS.",
    )
    parser.add_argument(
        "--generate-zacros",
        action="store_true",
        help="Generate static Zacros adapter files without running Zacros.",
    )
    parser.add_argument(
        "--run-catkinas",
        action="store_true",
        help="Run the configured CATKINAS command once.",
    )
    parser.add_argument(
        "--run-zacros",
        action="store_true",
        help="Run the configured Zacros command once.",
    )
    parser.add_argument(
        "--parse-catkinas-result",
        action="store_true",
        help="Parse existing CATKINAS result exports without interpretation.",
    )
    parser.add_argument(
        "--parse-zacros-result",
        action="store_true",
        help="Parse existing Zacros outputs without interpretation.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Summarize one simulation_result.json and write a factual report.",
    )
    parser.add_argument(
        "--workflow",
        action="store_true",
        help="Run the configured fail-fast workflow for one case directory.",
    )
    parser.add_argument(
        "--workflow-status",
        action="store_true",
        help="Print the persisted workflow state without changing it.",
    )
    parser.add_argument(
        "--case",
        type=Path,
        help="Case directory containing vasp/, reaction.yaml, and config.yaml.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help=(
            "Path to vasp_result.json for build or kinetic_dataset.json "
            "for validation/generation, or a simulation directory to run/parse."
        ),
    )
    parser.add_argument(
        "--reaction",
        type=Path,
        help="Path to a human-authored reaction YAML file.",
    )
    parser.add_argument(
        "--surface",
        type=Path,
        help="Path to a human-authored surface_config.yaml file.",
    )
    return parser


def _run_kinetic_builder(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Build and register one unverified kinetic record."""

    output_path = config.paths.processed_data / "kinetic_dataset.json"
    logger.info(
        "Building kinetic record: input=%s reaction=%s output=%s",
        args.input,
        args.reaction,
        output_path,
    )
    try:
        vasp_result = load_vasp_result(args.input)
        reaction = load_reaction_definition(args.reaction)
        record = build_kinetic_record(vasp_result, reaction)
        registration = register(record, output_path)
    except VASP2KineticsError as exc:
        logger.error("%s", exc)
        return 2

    if registration == RegistryStatus.DUPLICATE_ID:
        logger.error("DUPLICATE_ID: reaction_id=%s", record.reaction_id)
        return 1
    logger.info(
        "Kinetic record generated: reaction_id=%s output=%s",
        record.reaction_id,
        output_path,
    )
    return 0


def _run_validator(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Validate one dataset and write an independent report."""

    output_path = config.paths.processed_data / "validation_report.json"
    logger.info(
        "Validating kinetic dataset: input=%s output=%s",
        args.input,
        output_path,
    )
    try:
        report = validate_dataset(
            args.input,
            config.validator.energy_tolerance,
            config.validator.allowed_elements,
        )
        write_validation_report(report, output_path)
    except VASP2KineticsError as exc:
        logger.error("%s", exc)
        return 2

    logger.info("Validation report written to %s", output_path)
    summary = report["summary"]
    if isinstance(summary, dict) and summary.get("failed", 0):
        logger.error("Validation completed with failed reactions: %s", summary)
        return 1
    return 0


def _run_vasp_parser(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Parse one existing VASP case and write its standardized result."""

    result = parse_vasp_case(args.parse_vasp)
    output_path = config.paths.processed_data / "vasp_result.json"
    try:
        write_vasp_result(result, output_path)
    except VASP2KineticsError as exc:
        logger.error("%s", exc)
        return 2

    logger.info("VASP parser result written to %s", output_path)
    error = result.get("error")
    if isinstance(error, str):
        logger.error("VASP parsing completed with error: %s", error)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Initialize the application and run at most one requested action."""

    argument_parser = build_argument_parser()
    args = argument_parser.parse_args(argv)
    validate_arguments(argument_parser, args)

    try:
        workflow_action = args.workflow or args.workflow_status
        config_path = args.case / "config.yaml" if workflow_action else args.config
        config = load_config(
            config_path,
            project_root=args.case if workflow_action else None,
        )
        logger = configure_logging(config.logging)
    except VASP2KineticsError as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger("vasp2kinetics").error("%s", exc)
        return 2

    logger.info(
        "%s %s application initialized.",
        config.project.name,
        config.project.version,
    )
    if args.workflow:
        return run_workflow(args.case, config, logger)
    if args.workflow_status:
        return show_workflow_status(args.case, config, logger)
    if args.build_kinetics:
        return _run_kinetic_builder(args, config, logger)
    if args.validate:
        return _run_validator(args, config, logger)
    if args.generate_catkinas:
        return run_catkinas_generator(args, config, logger)
    if args.generate_zacros:
        return run_zacros_generator(args, config, logger)
    if args.run_catkinas:
        return run_catkinas(args, config, logger)
    if args.run_zacros:
        return run_zacros(args, config, logger)
    if args.parse_catkinas_result:
        return parse_catkinas_command(args, config, logger)
    if args.parse_zacros_result:
        return parse_zacros_command(args, config, logger)
    if args.analyze:
        return analyze_command(args, config, logger)
    if args.parse_vasp is not None:
        try:
            with phase_log(logger, config.logging.phase_files.parser):
                return _run_vasp_parser(args, config, logger)
        except VASP2KineticsError as exc:
            logger.error("%s", exc)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
