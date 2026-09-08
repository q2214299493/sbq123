"""Command handlers for static kinetic-model adapter generation."""

from __future__ import annotations

import argparse
import logging

from .catkinas.generator import generate_catkinas_project
from .config import AppConfig
from .exceptions import VASP2KineticsError
from .zacros.generator import generate_zacros_project


def run_catkinas_generator(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Generate static CATKINAS adapter files without executing CATKINAS."""

    dataset_path = (
        args.input.expanduser().resolve()
        if args.input is not None
        else config.catkinas.input_path
    )
    validation_path = dataset_path.parent / "validation_report.json"
    output_path = config.catkinas.output_path
    logger.info(
        "Generating CATKINAS adapter: dataset=%s validation=%s output=%s",
        dataset_path,
        validation_path,
        output_path,
    )
    try:
        report = generate_catkinas_project(
            dataset_path,
            validation_path,
            output_path,
            config.catkinas.allow_warning,
        )
    except VASP2KineticsError as exc:
        logger.error("%s", exc)
        return 2

    logger.info("CATKINAS generation report: %s", report)
    if report["failed"]:
        logger.error("CATKINAS generation completed with rejected reactions.")
        return 1
    return 0


def run_zacros_generator(
    args: argparse.Namespace,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Generate static Zacros adapter files without executing Zacros."""

    dataset_path = args.input.expanduser().resolve()
    validation_path = dataset_path.parent / "validation_report.json"
    surface_path = (
        args.surface.expanduser().resolve()
        if args.surface is not None
        else config.zacros.surface_config
    )
    output_path = config.zacros.output_path
    logger.info(
        "Generating Zacros adapter: dataset=%s validation=%s surface=%s output=%s",
        dataset_path,
        validation_path,
        surface_path,
        output_path,
    )
    try:
        report = generate_zacros_project(
            dataset_path,
            validation_path,
            surface_path,
            output_path,
            config.zacros.allow_warning,
        )
    except VASP2KineticsError as exc:
        logger.error("%s", exc)
        return 2

    logger.info("Zacros generation report: %s", report)
    if report["failed"]:
        logger.error("Zacros generation completed with rejected reactions.")
        return 1
    return 0
