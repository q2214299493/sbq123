"""Cross-phase command-line combination validation."""

from __future__ import annotations

import argparse


def validate_arguments(
    argument_parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    """Reject ambiguous or incomplete command combinations."""

    action_count = sum(
        (
            args.parse_vasp is not None,
            args.build_kinetics,
            args.validate,
            args.generate_catkinas,
            args.generate_zacros,
            args.run_catkinas,
            args.run_zacros,
            args.parse_catkinas_result,
            args.parse_zacros_result,
            args.analyze,
            args.workflow,
            args.workflow_status,
        )
    )
    if action_count > 1:
        argument_parser.error(
            "Parse, build, validate, generate, and run actions are "
            "mutually exclusive."
        )
    workflow_action = args.workflow or args.workflow_status
    if workflow_action and args.case is None:
        argument_parser.error("--workflow and --workflow-status require --case.")
    if not workflow_action and args.case is not None:
        argument_parser.error("--case requires --workflow or --workflow-status.")
    if args.build_kinetics and (args.input is None or args.reaction is None):
        argument_parser.error("--build-kinetics requires --input and --reaction.")
    if args.validate and args.input is None:
        argument_parser.error("--validate requires --input.")
    if args.validate and args.reaction is not None:
        argument_parser.error("--reaction cannot be used with --validate.")
    if args.generate_catkinas and args.reaction is not None:
        argument_parser.error("--reaction cannot be used with --generate-catkinas.")
    if args.generate_zacros and args.input is None:
        argument_parser.error("--generate-zacros requires --input.")
    if args.generate_zacros and args.reaction is not None:
        argument_parser.error("--reaction cannot be used with --generate-zacros.")
    if (args.run_catkinas or args.run_zacros) and args.input is None:
        argument_parser.error("simulation runner actions require --input.")
    result_action = args.parse_catkinas_result or args.parse_zacros_result
    if args.analyze and args.input is None:
        argument_parser.error("--analyze requires --input.")
    if (
        args.run_catkinas
        or args.run_zacros
        or result_action
        or args.analyze
    ) and args.reaction:
        argument_parser.error("--reaction cannot be used with run/parse actions.")
    if not args.generate_zacros and args.surface is not None:
        argument_parser.error("--surface requires --generate-zacros.")
    input_actions = (
        args.build_kinetics
        or args.validate
        or args.generate_catkinas
        or args.generate_zacros
        or args.run_catkinas
        or args.run_zacros
        or result_action
        or args.analyze
    )
    if not input_actions and (args.input is not None or args.reaction is not None):
        argument_parser.error(
            "--input requires a build, validate, generate, run, or result-parse "
            "action; --reaction requires --build-kinetics."
        )
