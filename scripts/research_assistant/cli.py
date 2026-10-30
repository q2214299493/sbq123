"""One natural-language entry for diagnosis, option comparison and research plans."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
import uuid

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive

from .usage_sources import validate_feedback_request
from .runner import ResearchRun, run_research
from .tools import SPECS
from .catalog import blocked
from .continuation import previous_header
from .policies import PolicyStore
from .dashboard_cli import add_command as add_dashboard_command, execute as dashboard_command, automatic as refresh_dashboard
from .policy_cli import add_commands, policy_command, usage_command, feedback_index_error, config_from_args


def feedback(run: Path, request: Path, *, no_dashboard=False):
    receipt = load_json_object(run / "run_receipt.json")
    value = load_json_object(request)
    validate_feedback_request(run, value, receipt)
    folder = run / "feedback"
    folder.mkdir(exist_ok=True)
    payload = {"schema_version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
               "run_receipt_sha256": sha256_file(run / "run_receipt.json"), "goal": receipt["goal"],
               "usage_feedback": {k: v for k, v in value.items() if k != "scientific_result_reference"},
               "scientific_result_reference": value["scientific_result_reference"], "promotes_scientific_result": False, "strategy_approved": False}
    path = folder / (sha256_json(payload) + ".json")
    write_json_exclusive(path, payload)
    reference = {"path": str(path), "sha256": sha256_file(path)}
    config = receipt.get("rsi_config")
    if config:
        try:
            project = load_json_object(Path(receipt["rsi_application"]["path"]))["selection"]["task"]["project"]
            PolicyStore(config["store"], project).index_feedback(reference, receipt)
        except (OSError, ValueError, KeyError) as exc:
            reference = {**reference, "rsi_index_error": feedback_index_error(run, reference, exc)}
    refresh_dashboard(run=run, disabled=no_dashboard)
    return reference


def _run_options(sub, command):
    run = sub.add_parser(command)
    run.add_argument("--goal", required=command == "run")
    run.add_argument("--intent", choices=["auto", "diagnose", "compare", "plan"], default="auto" if command == "run" else None)
    run.add_argument("--workdir", type=Path, required=command == "run")
    run.add_argument("--project-root", type=Path)
    run.add_argument("--profile", type=Path, help="Task-local existing codex/auth/model configuration; never credentials.")
    run.add_argument("--scope", type=Path, action="append", default=[])
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--mode", choices=["daily", "evaluation"], default="daily")
    run.add_argument("--evaluation-manifest", type=Path)
    run.add_argument("--model")
    run.add_argument("--effort", choices=["minimal", "low", "medium", "high", "xhigh"])
    run.add_argument("--auth-home", type=Path)
    run.add_argument("--codex")
    run.add_argument("--max-turns", type=int, default=3)
    run.add_argument("--max-actions", type=int, default=10)
    run.add_argument("--timeout-seconds", type=float, default=360)
    run.add_argument("--no-dashboard", action="store_true", help="Skip derived display generation; research records are unchanged.")
    run.add_argument("--rsi-store", type=Path, help="Stable project-owned policy/feedback store, separate from run outputs.")
    run.add_argument("--rsi-mode", choices=["accepted", "off"])
    run.add_argument("--rsi-exclude-policy", action="append", default=[], help="Explicit experimental exclusion; never changes scientific requirements.")
    run.add_argument("--rsi-trial-policy", action="append", default=[], help="Explicitly load an independently reviewed trial policy.")
    if command == "resume":
        run.add_argument("--from-run", type=Path, required=True)
        run.add_argument("--update", required=True, help="New evidence or task clarification within the same research question.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    _run_options(sub, "run")
    _run_options(sub, "resume")
    add_commands(sub)
    add_dashboard_command(sub)
    tools = sub.add_parser("tools", help="Inspect registered host operations; no model or scientific job.")
    tools.set_defaults(tool_listing=True)
    use = sub.add_parser("feedback")
    use.add_argument("--run", type=Path, required=True)
    use.add_argument("--request", type=Path, required=True)
    use.add_argument("--no-dashboard", action="store_true")
    spc = sub.add_parser("spc-export", help="Offline non-authoritative SPC staging; never changes SPC state or approvals.")
    spc.add_argument("--run", type=Path, required=True)
    spc.add_argument("--spc-root", type=Path, required=True)
    spc.add_argument("--output-dir", type=Path, required=True)
    spc.add_argument("--binding", type=Path)
    spc.add_argument("--planning-input", type=Path)
    args = root.parse_args()
    if args.command == "dashboard":
        print(json.dumps(dashboard_command(args), ensure_ascii=False))
        return
    if args.command == "policies":
        print(json.dumps(policy_command(args), ensure_ascii=False, indent=2))
        return
    if args.command == "usage":
        print(usage_command(args.run))
        return
    if args.command == "tools":
        print(json.dumps(SPECS, ensure_ascii=False, indent=2))
        return
    if args.command == "feedback":
        print(json.dumps(feedback(args.run, args.request, no_dashboard=args.no_dashboard), ensure_ascii=False))
        return
    if args.command == "spc-export":
        from .spc_adapter import export
        value = export(args.run, args.spc_root, args.output_dir, binding_path=args.binding, planning_input_path=args.planning_input)
        print(json.dumps({"status": value["status"], "path": str(args.output_dir / "spc_mapping.json")}, ensure_ascii=False))
        return
    old_scopes = []
    if args.command == "resume":
        prior, inventory = previous_header(args.from_run)
        if args.goal and args.goal != prior["goal"]:
            raise ValueError("resume preserves the original goal; pass --update for new context")
        args.goal, args.intent = prior["goal"], args.intent or prior["intent"]
        old_scopes = [Path(path) for path in inventory["scopes"] if Path(path).is_dir()]
        args.workdir = args.workdir or (old_scopes[0] if old_scopes else None)
        if args.workdir is None:
            raise ValueError("previous scopes are missing; supply a current --workdir")
    if args.profile and blocked(args.profile.absolute()):
        raise ValueError("use a task-local nonsecret profile, not personal authentication/configuration")
    profile = load_json_object(args.profile) if args.profile else {}
    if set(profile) - {"project_root", "auth_home", "codex", "output_root", "model", "effort", "rsi"}:
        raise ValueError("profile contains unsupported settings; native permissions are not configurable here")
    project = args.project_root or (Path(profile["project_root"]) if profile.get("project_root") else next(
        (p for p in [args.workdir.absolute(), *args.workdir.absolute().parents] if (p / "configs/execution_backends.yaml").is_file()), None))
    home = args.auth_home or (Path(profile["auth_home"]) if profile.get("auth_home") else None)
    codex = args.codex or profile.get("codex")
    if project is None or home is None or not codex:
        raise ValueError("set one task-local profile with existing project_root/auth_home/codex, or provide them explicitly")
    rsi = config_from_args(project, profile, args)
    output_root = Path(profile["output_root"]) if profile.get("output_root") else project.parent / (project.name + "_research_runs")
    output = args.output_dir or output_root / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
    scopes = list(dict.fromkeys([*old_scopes, args.workdir, *args.scope]))
    if args.mode == "daily" and not old_scopes:
        scopes += [project / name for name in ("docs", "configs", "modules") if (project / name).is_dir()]
    run = ResearchRun(args.goal, args.intent, scopes, project, output, mode=args.mode,
                      manifest=args.evaluation_manifest, model=args.model or profile.get("model", "gpt-6.1-sol"),
                      effort=args.effort or profile.get("effort", "medium"),
                      max_turns=args.max_turns, max_actions=args.max_actions, timeout=args.timeout_seconds,
                      previous_run=args.from_run if args.command == "resume" else None,
                      update=args.update if args.command == "resume" else "", rsi=rsi)
    print(json.dumps(run_research(run, home, codex), ensure_ascii=False))
    refresh_dashboard(run=run.output, disabled=args.no_dashboard)


if __name__ == "__main__":
    main()
