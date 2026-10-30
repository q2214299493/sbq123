"""Explicit independent policy reviews and additive, user-sourced usage records."""
import json
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, sha256_json

from .policies import PolicyStore, checked_reference
from .rsi_application import pointer, usage_lines


def add_commands(sub):
    policy = sub.add_parser("policies", help="Inspect/propose/review declarative policies; never approves scientific options.")
    policy.add_argument("action", choices=["show", "propose", "review"])
    policy.add_argument("--project-root", type=Path, required=True)
    policy.add_argument("--store", type=Path, required=True)
    policy.add_argument("--request", type=Path)
    policy.add_argument("--candidate-id", help="Bind a reviewed declarative proposal to an archived model candidate.")
    usage = sub.add_parser("usage", help="Read frozen RSI application plus separately recorded later user feedback.")
    usage.add_argument("--run", type=Path, required=True)


def config_from_args(project, profile, args):
    from .policy_selection import settings
    config = settings(project, profile.get("rsi"))
    if args.rsi_store:
        config["store"] = str(args.rsi_store.absolute())
    if args.rsi_mode:
        config["mode"] = args.rsi_mode
    config["exclude_policy_ids"] = list(dict.fromkeys([*config["exclude_policy_ids"], *args.rsi_exclude_policy]))
    config["trial_policy_ids"] = list(dict.fromkeys([*config["trial_policy_ids"], *args.rsi_trial_policy]))
    return config


def policy_command(args):
    store = PolicyStore(args.store, args.project_root)
    if args.action == "show":
        return store.read()
    if not args.request:
        raise ValueError("policy propose/review requires an explicit request artifact")
    reference = {"path": str(args.request.absolute()), "sha256": sha256_file(args.request)}
    checked_reference(reference)
    request = load_json_object(args.request)
    return store.propose(request, args.candidate_id) if args.action == "propose" else store.review(request, reference)


def validate_usage_feedback(run, value, receipt):
    entries = value.get("rsi_feedback", [])
    if not isinstance(entries, list):
        raise ValueError("rsi_feedback must be a separate list")
    if not entries:
        return
    reference = receipt.get("rsi_application")
    if not reference:
        raise ValueError("legacy run has no selected policy for RSI feedback")
    checked_reference(reference)
    record = load_json_object(Path(reference["path"]))
    selected = {row["policy_id"] for row in record["selected_policies"]}
    actions = {row["evidence_id"] for row in load_json_object(run / "research_result.json")["evidence_actions"]}
    answer = load_json_object(run / "research_result.json")["answer"]
    for row in entries:
        if not isinstance(row, dict) or set(row) != {"policy_id", "helpful", "reason", "action_refs", "output_refs"} \
                or row["policy_id"] not in selected or (row["helpful"] is not None and type(row["helpful"]) is not bool) \
                or not isinstance(row["reason"], str) or not isinstance(row["action_refs"], list) or not isinstance(row["output_refs"], list):
            raise ValueError("RSI helpfulness must refer to a selected policy and explicit user report")
        if not set(row["action_refs"]) <= actions:
            raise ValueError("RSI feedback cites an unrecorded action")
        try:
            for ref in row["output_refs"]:
                pointer(answer, ref)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise ValueError("RSI feedback cites an unrecorded output") from exc
        if row["helpful"] is True and (not row["reason"].strip() or not row["action_refs"] or not row["output_refs"]):
            raise ValueError("reported concrete help requires a reason and actual action/output references")


def usage_record(run):
    receipt = load_json_object(run / "run_receipt.json")
    reference = receipt.get("rsi_application")
    if not reference:
        return {"status": "LEGACY_RUN_NO_RSI_RECORD"}
    checked_reference(reference)
    record = load_json_object(Path(reference["path"]))
    feedback = []
    for path in sorted((run / "feedback").glob("*.json")):
        value = load_json_object(path)
        if value["run_receipt_sha256"] != sha256_file(run / "run_receipt.json"):
            raise ValueError("usage feedback receipt binding differs")
        for item in value["usage_feedback"].get("rsi_feedback", []):
            feedback.append({"feedback_ref": {"path": str(path), "sha256": sha256_file(path)},
                             "recorded_at": value["recorded_at"], "user_report": item})
    record["later_user_feedback"] = feedback
    comparisons = []
    for path in sorted((run / "comparisons").glob("*.json")):
        binding = load_json_object(path)
        if binding.get("run_receipt_sha256") != sha256_file(run / "run_receipt.json"):
            raise ValueError("comparison belongs to a different immutable run receipt")
        checked_reference(binding["comparison_reference"])
        comparisons.append(binding["comparison_reference"])
    if "value" in record:
        record["value"]["user_feedback_refs"] = [row["feedback_ref"] for row in feedback]
        record["value"]["paired_comparison_refs"] = comparisons
    # An attached comparison file is only a provenance reference, not a host
    # determination that its scientific/value judgments are correct.
    # This is an additive read view: neither original model inputs nor their
    # hash-bound application and receipt files are rewritten after feedback.
    return record


def usage_command(run):
    value = usage_record(run)
    if "selected_policies" not in value:
        return json.dumps(value, ensure_ascii=False)
    lines = usage_lines(value)
    for row in value["later_user_feedback"]:
        report = row["user_report"]
        lines += [f"后补用户反馈：{report['policy_id']}；报告有帮助={report['helpful']}；{report['reason']}",
                  f"原反馈：[{row['feedback_ref']['sha256'][:12]}](<{row['feedback_ref']['path']}>)"]
    for reference in value.get("value", {}).get("paired_comparison_refs", []):
        lines += [f"配对来源记录：[{reference['sha256'][:12]}](<{reference['path']}>)；收益仍须内容评阅，不能凭记录存在判定。"]
    return "\n".join(lines)


def feedback_index_error(run, feedback_ref, error):
    # Preserve a usable feedback record even if the independent project index
    # is temporarily locked. No complete research/model rerun is necessary.
    payload = {"feedback_ref": feedback_ref, "error": str(error), "status": "RSI_INDEX_PENDING_RECONCILIATION"}
    path = run / "feedback" / ("index-error-" + sha256_json(payload) + ".txt")
    if not path.exists():
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"path": str(path), "sha256": sha256_file(path), "status": payload["status"]}
