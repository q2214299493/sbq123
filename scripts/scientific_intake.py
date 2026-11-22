"""Inspect reaction evidence or a read-only research project."""
import argparse
import json
from pathlib import Path

from scripts.kinetic_data.reaction_intake import (
    AVAILABLE as AVAILABLE,
    INCOMPATIBLE as INCOMPATIBLE,
    MISSING as MISSING,
    OPERATIONS as OPERATIONS,
    OPTIONAL as OPTIONAL,
    REACTION_FIELDS as REACTION_FIELDS,
    STATES as STATES,
    STATE_FIELDS as STATE_FIELDS,
    UNVERIFIED as UNVERIFIED,
    assess_field as assess_field,
    assess_states as assess_states,
    collect_records as collect_records,
    incompatible as incompatible,
    inspect_record as inspect_record,
    operation_requirements as operation_requirements,
    report as report,
    reuse_correction_conditions as reuse_correction_conditions,
    thermal_routes as thermal_routes,
    validator as validator,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intakes", type=Path, nargs="*", help="Base reaction followed by optional evidence uploads")
    parser.add_argument("--operation", choices=OPERATIONS, default=None)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--inspect-project", nargs=2, type=Path, metavar=("PROJECT", "TASK"),
                        help="Inspect a project and task YAML offline and print a JSON evidence report")
    modes.add_argument("--kinetic-readiness", nargs=2, type=Path, metavar=("PROJECT", "TASK"),
                        help="Qualify each network reaction and reconstruct eligible engine inputs offline")
    args = parser.parse_args()
    if args.inspect_project or args.kinetic_readiness:
        if args.intakes or args.operation is not None:
            mode = "--inspect-project" if args.inspect_project else "--kinetic-readiness"
            parser.error(f"{mode} is separate from positional reaction intake and --operation")
        from scripts.kinetic_data.project_inspection import inspect_project

        try:
            result = inspect_project(*(args.inspect_project or args.kinetic_readiness),
                                     kinetic_readiness=bool(args.kinetic_readiness))
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return
    if not args.intakes:
        parser.error("supply a reaction intake or --inspect-project PROJECT TASK")
    documents = [json.loads(p.read_text(encoding="utf-8-sig"), parse_constant=reject_nonfinite) for p in args.intakes]
    print(json.dumps(report(documents, args.operation or "thermochemistry"), ensure_ascii=True, indent=2, allow_nan=False))


def reject_nonfinite(token):
    raise ValueError(f"Non-finite JSON number: {token}")


if __name__ == "__main__":
    main()
