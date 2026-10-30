"""One natural-language entry for diagnosis, option comparison and research plans."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import sys
from pathlib import Path
import uuid

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links

from .runner import ResearchRun, run_research
from .tools import SPECS
from .catalog import blocked
from .continuation import previous_header
from .policies import PolicyStore
from .policy_cli import add_commands, policy_command, usage_command, validate_usage_feedback, feedback_index_error, config_from_args


def feedback(run: Path, request: Path):
    receipt = load_json_object(run / "run_receipt.json")
    value = load_json_object(request)
    required = {"adopted", "evidence_effectiveness", "repeated_checks", "followup_notes", "scientific_result_reference"}
    if not required <= set(value) or set(value) - required - {"human_review_seconds", "adopted_option_ids", "rsi_feedback", "human_preparation_seconds", "human_correction_seconds"} \
            or (value["adopted"] is not None and type(value["adopted"]) is not bool):
        raise ValueError("feedback requires separate adoption/evidence/repetition/followup/scientific-reference fields")
    if not isinstance(value["evidence_effectiveness"], list) or not isinstance(value["repeated_checks"], list) \
            or not isinstance(value["followup_notes"], str):
        raise ValueError("invalid usage feedback types")
    known = {p.stem for p in (run / "tools").glob("E[0-9][0-9][0-9].json")}
    for item in value["evidence_effectiveness"]:
        if set(item) != {"evidence_id", "effective", "reason"} or item["evidence_id"] not in known \
                or (item["effective"] is not None and type(item["effective"]) is not bool) or not isinstance(item["reason"], str):
            raise ValueError("feedback must refer to actual host actions and explicit unknown/boolean effectiveness")
    if not set(value["repeated_checks"]) <= known:
        raise ValueError("unrecorded repeated check")
    result = value["scientific_result_reference"]
    if result is not None and (not isinstance(result, dict) or set(result) != {"path", "sha256"}
                               or blocked(Path(result["path"])) or sha256_file(Path(result["path"])) != result["sha256"]):
        raise ValueError("scientific result reference must be a real separately checked owner artifact")
    if result is not None:
        _no_links(Path(result["path"]).absolute())
    for key in ("human_review_seconds", "human_preparation_seconds", "human_correction_seconds"):
        seconds = value.get(key)
        if seconds is not None and (type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0):
            raise ValueError("human time must be explicitly measured or unknown")
    selected = value.get("adopted_option_ids", [])
    options = {row["id"] for row in load_json_object(run / "research_result.json")["answer"]["options"]} if selected else set()
    if not isinstance(selected, list) or any(not isinstance(v, str) or v not in options for v in selected) or (selected and value["adopted"] is not True):
        raise ValueError("adopted branches require explicit adoption of existing option IDs")
    validate_usage_feedback(run, value, receipt)
    folder = run / "feedback"
    folder.mkdir(exist_ok=True)
    payload = {"schema_version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
               "run_receipt_sha256": sha256_file(run / "run_receipt.json"), "goal": receipt["goal"],
               "usage_feedback": {k: v for k, v in value.items() if k != "scientific_result_reference"},
               "scientific_result_reference": result, "promotes_scientific_result": False, "strategy_approved": False}
    path = folder / (sha256_json(payload) + ".json")
    write_json_exclusive(path, payload)
    reference = {"path": str(path), "sha256": sha256_file(path)}
    config = receipt.get("rsi_config")
    if config:
        try:
            project = load_json_object(Path(receipt["rsi_application"]["path"]))["selection"]["task"]["project"]
            PolicyStore(config["store"], project).index_feedback(reference, receipt)
        except (OSError, ValueError, KeyError) as exc:
            return {**reference, "rsi_index_error": feedback_index_error(run, reference, exc)}
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
    tools = sub.add_parser("tools", help="Inspect registered host operations; no model or scientific job.")
    tools.set_defaults(tool_listing=True)
    use = sub.add_parser("feedback")
    use.add_argument("--run", type=Path, required=True)
    use.add_argument("--request", type=Path, required=True)
    spc = sub.add_parser("spc-export", help="Offline non-authoritative SPC staging; never changes SPC state or approvals.")
    spc.add_argument("--run", type=Path, required=True)
    spc.add_argument("--spc-root", type=Path, required=True)
    spc.add_argument("--output-dir", type=Path, required=True)
    spc.add_argument("--binding", type=Path)
    spc.add_argument("--planning-input", type=Path)
    args = root.parse_args()
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
        print(json.dumps(feedback(args.run, args.request), ensure_ascii=False))
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


if __name__ == "__main__":
    main()
