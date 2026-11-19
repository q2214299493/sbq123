"""Read-only command line for parsing frequencies and calculating corrections."""
import argparse
import json
from pathlib import Path

from scripts.thermochemistry.engine import calculate
from scripts.thermochemistry.frequencies import draft_intake, parse_outcar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    raw = commands.add_parser("parse")
    raw.add_argument("outcar", type=Path)
    raw.add_argument("poscar", type=Path)
    raw.add_argument("--reaction-id", help="Emit a draft intake document for this reaction")
    raw.add_argument("--state", choices=("IS", "TS", "FS"))
    raw.add_argument("--thermal-basis")
    run = commands.add_parser("calculate")
    run.add_argument("intakes", type=Path, nargs="+")
    run.add_argument("--operation", choices=("zpe", "thermochemistry"), default="thermochemistry")
    run.add_argument("--ts-review", type=Path)
    run.add_argument("--phase", choices=("adsorbate", "gas"), help="Default phase for supplied states")
    run.add_argument("--independent-errors", action="store_true")
    args = parser.parse_args()
    if args.command == "parse":
        result = parse_outcar(args.outcar, args.poscar)
        if args.reaction_id or args.state or args.thermal_basis:
            if not args.reaction_id or not args.state:
                parser.error("Draft intake output requires --reaction-id and --state")
            result = draft_intake(result, args.reaction_id, args.state, args.thermal_basis)
    else:
        documents = [json.loads(p.read_text(encoding="utf-8-sig")) for p in args.intakes]
        review = json.loads(args.ts_review.read_text(encoding="utf-8-sig")) if args.ts_review else None
        result = calculate(documents, operation=args.operation, ts_review=review, phase=args.phase,
                           independent_errors=args.independent_errors)
    print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
