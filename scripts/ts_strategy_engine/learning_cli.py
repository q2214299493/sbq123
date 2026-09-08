"""CLI adapters for local strategy learning; never launch a calculation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.artifact_io import load_json_object, write_json

from .learning_evidence import attempt_input_hashes, bind_files, vasp_input_hashes
from .learning_store import DEFAULT_DATABASE, read_events
from .strategy_learning import (
    capture_baseline, capture_workdir, compare_variants, propose_variant,
    import_failure, record_outcome, reference_methods, retry_assessment, start_attempt, revise_outcome,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Evidence-backed strategy variants, attempts and comparisons; no execution.")
    root.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    root.add_argument("--output", type=Path, help="New report file; existing files are never replaced.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("methods", help="List reference candidate generators and their boundaries.")
    commands.add_parser("history", help="List compact version and attempt status.")
    baseline = commands.add_parser("capture", help="Capture an existing NEB without resetting its progress.")
    baseline.add_argument("--workdir", type=Path, required=True)
    baseline.add_argument("--task-id", required=True)
    baseline.add_argument("--source", action="append", default=[], metavar="ROLE=PATH")
    baseline.add_argument("--attempt-budget", type=int, default=5)
    for name in ("baseline", "propose", "start", "check", "import-failure"):
        command = commands.add_parser(name, help="Read an explicit JSON request; see module learning documentation.")
        command.add_argument("--request", type=Path, required=True)
    start = commands.add_parser("start-vasp", help="Record an attempt from existing VASP inputs; does not submit.")
    start.add_argument("--workdir", type=Path, required=True)
    start.add_argument("--kind", choices=["ordinary_neb", "ci_neb", "dimer", "diagnostic_static", "neb_pilot", "vfa"], required=True)
    start.add_argument("--variant-id", required=True)
    start.add_argument("--task-id", required=True)
    start.add_argument("--attempt-id", required=True)
    start.add_argument("--source-calculation-id", help="Existing registry calculation ID, required before claiming TS success.")
    outcome = commands.add_parser("outcome", help="Append a reviewed, source-bound outcome to an existing attempt.")
    outcome.add_argument("--attempt-id", required=True)
    outcome.add_argument("--request", type=Path, required=True)
    revision = commands.add_parser("revise-outcome", help="Append an evidence-bound correction while preserving history.")
    revision.add_argument("--attempt-id", required=True)
    revision.add_argument("--request", type=Path, required=True)
    revision.add_argument("--previous-sha256", required=True)
    revision.add_argument("--reason", required=True)
    compare = commands.add_parser("compare", help="Compare frozen cases without promoting a strategy or a result.")
    compare.add_argument("--baseline-id", required=True)
    compare.add_argument("--candidate-id", required=True)
    return root


def _dispatch(args: argparse.Namespace):
    database = args.database
    if args.command == "methods":
        return reference_methods()
    if args.command == "history":
        outcomes = read_events(database, "outcome")
        return {
            "variants": [{"id": key, "parent_id": row["parent_id"], "settings": row["settings"]}
                         for key, row in read_events(database, "variant").items()],
            "attempts": [{"id": key, "task_id": row["task_id"], "status": outcomes.get(key, {}).get("status", "unresolved")}
                         for key, row in read_events(database, "attempt").items()],
        }
    if args.command == "capture":
        sources = {}
        for source in args.source:
            role, separator, value = source.partition("=")
            if not separator or role in sources:
                raise ValueError("sources must have unique ROLE=PATH entries")
            sources[role] = value
        return {"variant_id": capture_workdir(database, args.workdir, args.task_id, sources, args.attempt_budget)}
    if args.command == "compare":
        return compare_variants(database, args.baseline_id, args.candidate_id)
    if args.command == "start-vasp":
        from scripts.neb_agent.submission import preflight
        report = preflight(args.workdir, args.kind, learning_database=database)
        if not report["passed"]:
            raise ValueError("VASP preflight failed; inspect submission_preflight.json")
        spec = {"attempt_id": args.attempt_id, "variant_id": args.variant_id, "task_id": args.task_id,
                "kind": args.kind, "parent_attempt_id": None,
                "source_calculation_id": args.source_calculation_id,
                "inputs": {name: str(args.workdir / name) for name in vasp_input_hashes(report["files"])}}
        return {"attempt_id": start_attempt(database, spec)}
    request = load_json_object(args.request)
    if args.command == "baseline":
        return {"variant_id": capture_baseline(database, request)}
    if args.command == "import-failure":
        return {"attempt_id": import_failure(database, request)}
    if args.command == "propose":
        return {"variant_id": propose_variant(database, **request)}
    if args.command == "start":
        return {"attempt_id": start_attempt(database, request)}
    if args.command == "outcome":
        return {"attempt_id": record_outcome(database, args.attempt_id, request)}
    if args.command == "revise-outcome":
        return {"revision_id": revise_outcome(database, args.attempt_id, request,
                previous_sha256=args.previous_sha256, reason=args.reason)}
    references = bind_files(request["inputs"])
    return retry_assessment(database, request["kind"], attempt_input_hashes(request["kind"], references))


def main(argv: list[str] | None = None) -> None:
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError(f"report already exists: {args.output}")
        result = _dispatch(args)
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        root.exit(2, f"strategy learning: {exc}\n")


if __name__ == "__main__":
    main()
