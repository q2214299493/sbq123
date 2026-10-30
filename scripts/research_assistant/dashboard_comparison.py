"""Actual paired/continuation views and deterministic differences, without inference."""
from copy import deepcopy
import difflib
from pathlib import Path

from .dashboard_sources import bound, costs, answer_text, actions_from, selected_from


def _paired_row(row, sources):
    required = ("receipt_ref", "result_ref", "application_ref", "initial_input_ref")
    documents = {key: bound(row[key]) for key in required}
    receipt, app = documents["receipt_ref"], documents["application_ref"]
    if receipt.get("rsi_application") != row["application_ref"] or app.get("output_binding") != row["result_ref"]:
        raise ValueError("paired run bindings do not match its original receipt/application")
    return {"name": row["name"], "receipt_ref": row["receipt_ref"], "status": receipt.get("status"),
            "answer": documents["result_ref"].get("answer", {}), "costs": costs(receipt),
            "actions": actions_from(documents["result_ref"], sources), "policies": app.get("selected_policies", []),
            "receipt": receipt, "input": documents["initial_input_ref"]}


def _difference(left, right):
    return "\n".join(difflib.unified_diff(answer_text(left).splitlines(), answer_text(right).splitlines(),
                                        fromfile="earlier_or_baseline", tofile="current_or_candidate", lineterm=""))


def _same_conditions(left, right):
    first, second = deepcopy(left["input"]), deepcopy(right["input"])
    for value in (first, second):
        value.get("rsi_context", {}).pop("selected_policies", None)
    keys = ("model", "effort", "mode", "source_versions", "producer", "host_tool_implementation")
    return first == second and all(left["receipt"].get(key) == right["receipt"].get(key) for key in keys)


def paired_comparison(refs, run_ref, sources):
    supported, unsupported = [], []
    for ref in refs:
        document = sources.attempt("comparison_document", ref, lambda: bound(ref))
        if document is None:
            continue
        if not _known_format(document):
            unsupported.append({"reference": ref, "status": "unsupported_format", "message": "已绑定来源；不支持解析此格式，不用于收益结论。"})
            continue
        rows = {}
        for row in document["runs"]:
            value = sources.attempt("paired_run", row, lambda: _paired_row(row, sources))
            if value:
                rows[row["name"]] = value
        for check in document["condition_checks"]:
            task = check.get("task")
            left, right = rows.get(str(task) + "_baseline"), rows.get(str(task) + "_candidate")
            if not left or not right or run_ref not in [left["receipt_ref"], right["receipt_ref"]]:
                continue
            conditions = _same_conditions(left, right)
            for value in (left, right):
                value.pop("input")
                value.pop("receipt")
            supported.append({"kind": "paired", "label": "已登记真实配对", "reference": ref, "condition_check": check,
                "input_conditions_rechecked": conditions, "baseline": left, "candidate": right,
                "text_diff": _difference(left["answer"], right["answer"]), "content_review": document["content_review"],
                "reported_controlled_benefit": document.get("controlled_benefit"), "controlled_benefit": None,
                "validation_scope": "来源哈希及输入条件；两份建议不同或存在配对记录不证明科研收益。"})
    return supported, unsupported


def _known_format(document):
    if document.get("schema_version") != 1 or not {"condition_checks", "runs", "content_review", "controlled_benefit"} <= document.keys():
        return False
    if not isinstance(document["runs"], list) or not isinstance(document["condition_checks"], list):
        return False
    required = {"name", "receipt_ref", "result_ref", "application_ref", "initial_input_ref"}
    return all(isinstance(row, dict) and required <= row.keys() for row in document["runs"]) and all(
        isinstance(row, dict) and isinstance(row.get("task"), str) for row in document["condition_checks"])


def continuation_comparison(run, receipt, current, sources):
    if not receipt.get("continuation"):
        return None
    document = sources.attempt("continuation", receipt["continuation"], lambda: bound(receipt["continuation"]))
    if not document:
        return {"kind": "continuation", "label": "接续变化（来源未能核验）", "available": False}
    refs = document["bound_parent_artifacts"]
    selected = {}
    for name in ("run_receipt.json", "research_result.json"):
        binding = next((r for r in refs if Path(r["path"]).name == name), None)
        if binding:
            selected[name] = sources.attempt("parent_snapshot", binding, lambda: bound({"path": binding["snapshot"], "sha256": binding["sha256"]}))
    parent_receipt, result = selected.get("run_receipt.json"), selected.get("research_result.json")
    if not parent_receipt or not result:
        return {"kind": "continuation", "label": "接续变化（父运行原件未知）", "available": False}
    parent_app = sources.attempt("parent_application", parent_receipt.get("rsi_application"),
                                 lambda: bound(parent_receipt["rsi_application"])) if parent_receipt.get("rsi_application") else None
    context = document["context"]
    return {"kind": "continuation", "label": "接续变化，非控制实验", "available": True,
            "parent_run": context["parent_run"], "update": context["update"], "source_revalidation": context["source_revalidation"],
            "parent": {"answer": result.get("answer", {}), "costs": costs(parent_receipt),
                       "policies": selected_from(parent_app, sources) if parent_app else None,
                       "actions": result.get("evidence_actions", [])},
            "text_diff": _difference(result.get("answer", {}), current), "reference": receipt["continuation"],
            "attribution": "来源、工具、目标更新和缓存复用分别记录；接续变化不能直接归因于 RSI。"}
