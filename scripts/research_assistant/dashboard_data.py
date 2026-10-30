"""Versioned read-only dashboard projections from existing, verified RSI artifacts."""
from collections import Counter
from pathlib import Path

from .dashboard_sources import Sources, reference, read_json, bound, selected_from, applications_from, actions_from, read_additions, costs
from .dashboard_comparison import paired_comparison, continuation_comparison
from .policies import PolicyStore, utc_now


def current_store(root, project, sources):
    if root is None or project is None:
        return None
    if not (Path(root) / "state.json").is_file():
        return None
    return sources.attempt("current_policy_store", str(root), lambda: PolicyStore(root, project).read())


def _candidates(app):
    rows = app.get("candidate_records")
    if not isinstance(rows, list):
        return {"known": False, "counts": {}, "expanded": []}
    budget = app.get("selection", {}).get("config", {}).get("max_presented_candidates", 1)
    return {"known": True, "counts": dict(Counter(row.get("status", "unknown") for row in rows)),
            "expanded": [row for row in rows if row.get("status") == "candidate"][:min(1, budget)],
            "records": rows, "scope": "本次模型提出记录；人工实施看板属于软件改动，不计为自主改进。"}


def _no_policy_explanation(app, current, receipt):
    recorded = app.get("selection", {}).get("not_selected")
    result = {"recorded_reasons": recorded, "current_library_note": None}
    if current and current["policies"] and all(r["status"] == "trial" for r in current["policies"]):
        config = receipt.get("rsi_config", {})
        if config.get("mode") == "accepted" and not config.get("trial_policy_ids"):
            result["current_library_note"] = "当前策略库只有 trial；accepted-only 默认不会加载。此为当前库说明，不补写当时未选原因。"
    return result


def _feedback_state(feedback, index_errors, current):
    registered = {row["reference"]["sha256"] for row in current.get("feedback", [])} if current else None
    state = []
    for error in index_errors:
        digest = error.get("feedback_ref", {}).get("sha256")
        label = ("索引已恢复；保留曾经的失败记录" if registered is not None and digest in registered else
                 "反馈已保存，供后续运行使用的索引待恢复" if registered is not None else "反馈曾报告索引待恢复，当前状态未知")
        state.append({**error, "label": label})
    return state


def build_run(run, expected_receipt=None):
    run = Path(run).absolute()
    sources = Sources()
    ref = expected_receipt or sources.attempt("run_receipt", str(run), lambda: reference(run / "run_receipt.json"))
    receipt = sources.attempt("run_receipt", ref, lambda: bound(ref)) if ref else None
    data = {"schema_version": 1, "kind": "rsi_dashboard_run", "generated_at": utc_now(), "run_receipt_ref": ref,
            "run": {"path": str(run), "id": ref["sha256"] if ref else None, "name": run.name, "status": "unknown"},
            "source_errors": sources.errors, "software_change": "本地展示接入；不属于 RSI 自主科研改进。"}
    if not receipt:
        return {**data, "usage_state": "unknown", "selected_policies": [], "applications": [], "recommendation": None,
                "costs": costs({}), "feedback": [], "comparison": {"kind": "unpaired"}, "candidates": _candidates({})}
    data["run"].update({key: receipt.get(key) for key in ("goal", "intent", "status", "question_id", "mode", "run_mode", "first_failure_stage", "problem")})
    app = sources.attempt("rsi_application", receipt.get("rsi_application"), lambda: bound(receipt["rsi_application"])) if receipt.get("rsi_application") else None
    app = app or {}
    known = app.get("schema_version") == 1 and isinstance(app.get("selected_policies"), list) and "selection" in app and app.get("status") not in {"RSI_NOT_FROZEN", "RSI_RECORD_BLOCKED"}
    result = sources.attempt("research_result", app.get("output_binding"), lambda: bound(app["output_binding"])) if app.get("output_binding") else None
    if result is None and not receipt.get("rsi_application") and (run / "research_result.json").exists():
        result = sources.attempt("legacy_result", str(run / "research_result.json"), lambda: read_json(run / "research_result.json"))
    result = result or {}
    answer = result.get("answer") or {}
    actions = actions_from(result, sources)
    selected = selected_from(app, sources) if known else []
    applications = applications_from(app, selected, actions, answer, sources)
    feedback, comparison_refs, index_errors = read_additions(run, sources)
    task = app.get("selection", {}).get("task", {})
    current = current_store(receipt.get("rsi_config", {}).get("store"), task.get("project"), sources)
    paired, unsupported = paired_comparison(comparison_refs, ref, sources)
    continuation = continuation_comparison(run, receipt, answer, sources)
    data.update({"usage_state": "verified" if known else "unknown", "selected_policies": selected, "applications": applications,
        "provided_count": sum(row.get("provided") is True for row in selected) if known and all(r["source_verified"] for r in selected) else None,
        "recommendation": answer.get("recommended_next"), "answer": answer, "actions": actions, "costs": costs(receipt),
        "policy_frozen_at": app.get("selection", {}).get("frozen_at"), "feedback": feedback,
        "feedback_index": _feedback_state(feedback, index_errors, current), "current_policies": current,
        "no_policy_explanation": _no_policy_explanation(app, current, receipt), "candidates": _candidates(app),
        "comparison": {"kind": "paired" if paired else "continuation" if continuation else "unpaired",
                       "paired": paired, "continuation": continuation, "unsupported": unsupported, "registered_source_count": len(comparison_refs)},
        "value": {"original": app.get("value"), "user_confirmed_help": None, "controlled_benefit": None},
        "validation_scope": app.get("limits", "使用状态未知；旧版/缺失冻结记录不等于 0 条策略。")})
    return data
