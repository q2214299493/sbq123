"""CLI adapters for local strategy learning; never launch a calculation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json

from .learning_cases import build_cases
from .learning_evaluation import evaluate_cases
from .learning_evidence import attempt_input_hashes, bind_files
from .historical_replay import replay_history
from .next_review import recommend_next_reviews
from .learning_store import DEFAULT_DATABASE, read_events
from .workflow import start_vasp_attempt
from .strategy_learning import (
    capture_baseline, capture_workdir, compare_variants, propose_variant,
    import_failure, record_outcome, reference_methods, retry_assessment, start_attempt, revise_outcome,
)
from .workflow_improvement import create_baseline, propose_policy, policy_status, bind_evaluation, record_decision
from .workflow_review_runner import run_review
from .decision_planner import plan_next
from .template_reference import template_snapshot


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Evidence-backed strategy variants, attempts and comparisons; no execution.")
    root.add_argument("--database", type=Path)
    root.add_argument("--output", type=Path, help="New report file; existing files are never replaced.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("methods", help="List reference candidate generators and their boundaries.")
    commands.add_parser("history", help="List compact version and attempt status.")
    commands.add_parser("template-snapshot", help="Capture registered template/evidence identity from an explicit database; read only.")
    planning = commands.add_parser("plan-next", help="Source-bound TS decision advice; explicit history database required.")
    planning.add_argument("--request", type=Path, required=True)
    planning.add_argument("--expected-request-sha256", required=True)
    planning.add_argument("--use-templates", action="store_true", help="Explicit method-strategy reference only; requires a frozen snapshot hash.")
    planning.add_argument("--expected-template-snapshot-sha256")
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
    build = commands.add_parser("cases-build", help="Build a source-bound offline diagnostic case bundle.")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--allowed-root", type=Path, required=True)
    build.add_argument("--bundle", type=Path, required=True)
    evaluation = commands.add_parser("cases-evaluate", help="Score saved answers without a registry or model.")
    evaluation.add_argument("--bundle", type=Path, required=True)
    evaluation.add_argument("--answers", type=Path, required=True)
    evaluation.add_argument("--report", type=Path, required=True)
    advice = commands.add_parser("advise-next", help="Review-only suggestions from saved schema-2 answers.")
    advice.add_argument("--public", type=Path, required=True)
    advice.add_argument("--answers", type=Path, required=True)
    advice.add_argument("--expected-public-sha256", required=True)
    advice.add_argument("--report", type=Path, required=True)
    advice.add_argument("--workflow-store", type=Path)
    advice.add_argument("--workflow-policy")
    advice.add_argument("--workflow-scope")
    advice.add_argument("--offline-evaluation", action="store_true", help="Explicit offline candidate/fixture preview only.")
    for name in ("workflow-baseline", "workflow-propose", "workflow-bind-evaluation", "workflow-decide", "workflow-status"):
        command = commands.add_parser(name, help="Local immutable review-order artifacts; no database or execution.")
        command.add_argument("--store", type=Path, required=True)
        if name == "workflow-status":
            command.add_argument("--policy-id", required=True)
        else:
            command.add_argument("--request", type=Path, required=True)
    review = commands.add_parser("workflow-run-review", help="One independent read-only review; no model turn by default.")
    review.add_argument("--store", type=Path, required=True)
    review.add_argument("--request", type=Path, required=True)
    review.add_argument("--output-dir", type=Path, required=True)
    review.add_argument("--model", required=True, help="Explicit model identity, also recorded in prepare mode.")
    review.add_argument("--effort", choices=["minimal", "low", "medium", "high", "xhigh"], required=True)
    review.add_argument("--timeout-seconds", type=float, default=120)
    review.add_argument("--codex", help="Actual local executable; no upgrade or installation.")
    review.add_argument("--probe-backend", action="store_true", help="Local help/schema/stdio probe; no model turn.")
    review.add_argument("--execute", action="store_true", help="Request a model review; blocked unless native read confinement is verified.")
    review.add_argument("--auth-home", type=Path, help="Explicit isolated Codex authentication home; live execution only.")
    review.add_argument("--max-tool-calls", type=int, default=8, help="Per-run operation cap in [1, 8].")
    replay = commands.add_parser("replay-history", help="Replay saved, hash-bound historical snapshots without execution.")
    replay.add_argument("--request", type=Path, required=True)
    replay.add_argument("--expected-request-sha256", required=True)
    replay.add_argument("--report", type=Path, required=True)
    return root


def _dispatch_cases(args: argparse.Namespace):
    if args.command == "template-snapshot":
        return template_snapshot(args.database)
    if args.command == "plan-next":
        return plan_next(args.database, args.request, args.expected_request_sha256, use_templates=args.use_templates,
                         expected_template_snapshot_sha256=args.expected_template_snapshot_sha256)
    if args.command == "replay-history":
        return replay_history(args.request, args.report, args.expected_request_sha256)
    if args.command == "cases-build":
        return build_cases(args.manifest, args.allowed_root, args.bundle)
    if args.command == "advise-next":
        return recommend_next_reviews(args.public, args.answers, args.report,
                                      args.expected_public_sha256, workflow_store=args.workflow_store,
                                      workflow_policy=args.workflow_policy, workflow_scope=args.workflow_scope,
                                      offline_evaluation=args.offline_evaluation)
    return evaluate_cases(args.bundle, args.answers, args.report)


def _dispatch_workflow(args: argparse.Namespace):
    if args.command == "workflow-run-review":
        return run_review(args.store, args.request, args.output_dir, model=args.model, effort=args.effort,
                          timeout=args.timeout_seconds, codex=args.codex, probe=args.probe_backend, execute=args.execute,
                          auth_home=args.auth_home, max_tool_calls=args.max_tool_calls)
    if args.command == "workflow-status":
        return policy_status(args.store, args.policy_id)
    if args.command == "workflow-bind-evaluation":
        return bind_evaluation(args.store, {"path": str(args.request.resolve()), "sha256": sha256_file(args.request)})
    handlers = {"workflow-baseline": create_baseline, "workflow-propose": propose_policy, "workflow-decide": record_decision}
    return handlers[args.command](args.store, load_json_object(args.request))


def _dispatch(args: argparse.Namespace):
    if args.command.startswith("workflow-") or args.command in {"cases-build", "cases-evaluate", "advise-next", "replay-history", "plan-next", "template-snapshot"}:
        handler = _dispatch_workflow if args.command.startswith("workflow-") else _dispatch_cases
        return handler(args)
    database = args.database if args.database is not None else DEFAULT_DATABASE
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
        return {"attempt_id": start_vasp_attempt(database, args.workdir, args.kind, args.attempt_id,
                                                 args.variant_id, args.task_id, args.source_calculation_id)}
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
        if (args.command in {"cases-build", "cases-evaluate", "advise-next", "replay-history"}
                or args.command.startswith("workflow-")) and args.output is not None:
            raise ValueError("--output is not supported for diagnostic case commands")
        if args.output and args.output.exists():
            raise ValueError(f"report already exists: {args.output}")
        result = _dispatch(args)
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "workflow-run-review" and result["status"] == "BLOCKED":
            root.exit(2, "strategy learning: model review blocked; see result.json\n")
        if args.command == "cases-evaluate" and not result["integrity_ok"]:
            root.exit(2, f"strategy learning: invalid answer set; details in {args.report}\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        root.exit(2, f"strategy learning: {exc}\n")


if __name__ == "__main__":
    main()
