"""Limited host checks of frozen inputs, action identity/order and output citations."""
from copy import deepcopy
import json
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file

from .contract import citations
from .policy_selection import model_context


SCOPE = "identity, recorded tool order, search-hit/read linkage and output citation only; scientific correctness, coverage, usefulness and causality require content review"


def pointer(value, reference):
    if not isinstance(reference, str) or not reference.startswith("/"):
        raise ValueError("output reference must be an answer JSON pointer")
    for part in reference[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _action_map(actions):
    result = {}
    for action in actions:
        path = Path(action["result_path"])
        if sha256_file(path) != action["result_sha256"]:
            raise ValueError("RSI action record changed")
        value = load_json_object(path)
        if value["request"] != action["request"] or value["result"]["evidence_id"] != action["evidence_id"]:
            raise ValueError("RSI action binding differs")
        result[action["evidence_id"]] = (action, value["result"])
    return result


def _sequence(checks, refs, actions):
    ordered = [key for key in actions if key in refs]
    if refs != ordered or len(refs) != len(set(refs)):
        return "action references do not follow actual host order"
    position = 0
    for group in checks["ordered_tool_groups"]:
        found = next((i for i in range(position, len(ordered)) if actions[ordered[i]][0]["request"]["tool"] in group), None)
        if found is None:
            return "required tool sequence not observed"
        position = found + 1
    if checks["read_search_hit"]:
        hits = set()
        linked = False
        for key in ordered:
            action, result = actions[key]
            tool = action["request"]["tool"]
            if tool in {"history.search", "methods.search", "evidence.list"}:
                data = result.get("data", {})
                hits.update(row.get("source_id", row.get("id")) for row in data.get("matches", []))
            elif tool == "evidence.read" and hits & set(action["request"]["target_ids"]):
                linked = True
        if not linked:
            return "no recorded read of a returned search hit"
    return None


def _check(claim, selected, actions, answer):
    definition = selected["definition"]
    if (claim["version"], claim["content_sha256"]) != (definition["version"], selected["content_sha256"]):
        return "policy version/hash differs from frozen selection"
    if not claim["action_refs"] or any(ref not in actions or actions[ref][1]["status"] not in {"OK", "PARTIAL"} for ref in claim["action_refs"]):
        return "unrecorded, failed or absent action references"
    if not claim["output_refs"] or answer is None:
        return "no final output reference"
    try:
        outputs = [pointer(answer, ref) for ref in claim["output_refs"]]
    except (ValueError, TypeError, KeyError, IndexError):
        return "unrecorded output reference"
    if definition["checks"]["require_output_citation"]:
        cited = citations(outputs)
        if not cited & set(claim["action_refs"]):
            return "claimed actions are not cited at output references"
        reads = {ref for ref in claim["action_refs"] if actions[ref][0]["request"]["tool"] == "evidence.read"}
        if definition["checks"]["read_search_hit"] and not cited & reads:
            return "output does not cite a claimed source read"
    if not definition["checks"]["ordered_tool_groups"]:
        return "no mechanical behavior check declared; needs content review"
    return _sequence(definition["checks"], claim["action_refs"], actions)


def application_record(output, selection, contributions, actions, answer, candidate_records, submitted_inputs=()):
    inputs = []
    for reference in submitted_inputs:
        path = Path(reference["path"])
        if not path.is_relative_to(output) or sha256_file(path) != reference["sha256"]:
            raise ValueError("submitted RSI input binding differs")
        value = load_json_object(path)
        if value.get("rsi_context") != model_context(selection):
            raise ValueError("actual model input differs from frozen RSI context")
        inputs.append(deepcopy(reference))
    actual = _action_map(actions)
    claims = [(row, set(entry["available_action_refs"])) for entry in contributions for row in entry["rsi"]["applications"]]
    selected = {r["definition"]["policy_id"]: r for r in selection["selected_policies"]}
    applications = []
    for claim, available in claims:
        policy = selected.get(claim["policy_id"])
        reason = ("no submitted policy input" if not inputs else
                  _check(claim, policy, {key: value for key, value in actual.items() if key in available}, answer) if policy else "policy not selected in this run")
        applications.append({"policy_id": claim["policy_id"], "model_claim": deepcopy(claim),
            "action_refs": claim["action_refs"], "output_refs": claim["output_refs"],
            "host_status": "rejected" if reason else "observed_correspondence_needs_content_review",
            "reason": reason, "validation_scope": SCOPE, "causal_attribution": "unknown"})
    for identity in selected:
        if not any(row["policy_id"] == identity for row in applications):
            applications.append({"policy_id": identity, "model_claim": None, "action_refs": [], "output_refs": [],
                                 "host_status": "not_observed", "reason": "selection alone is not application", "validation_scope": SCOPE})
    return {"schema_version": 1, "selection": deepcopy(selection),
        "selected_policies": [{"policy_id": row["definition"]["policy_id"], "version": row["definition"]["version"],
            "content_sha256": row["content_sha256"], "proposer": row["definition"]["proposer"], "source_refs": row["frozen_sources"],
            "behavior_change": row["definition"]["behavior_change"], "selection_reason": row["selection_reason"],
            "provided": bool(inputs), "model_inputs": inputs} for row in selected.values()],
        "applications": applications, "candidate_records": candidate_records,
        "output_binding": {"path": str(output / "research_result.json"), "sha256": sha256_file(output / "research_result.json")} if answer is not None else None,
        "value": {"user_feedback_refs": [], "paired_comparison_refs": [], "user_confirmed_help": None,
                  "controlled_benefit": None, "status": "not_established"},
        "limits": SCOPE}


def usage_lines(record):
    lines = ["", "## 本轮 RSI 使用记录", ""]
    if record.get("status") in {"RSI_RECORD_BLOCKED", "RSI_NOT_FROZEN"}:
        return lines + [record["status"] + "；" + record.get("error", "策略未进入已冻结输入，使用状态未知。")]
    if not record["selected_policies"]:
        lines.append("本轮未触发已采纳策略，科研分析照常完成。")
    for row in record["selected_policies"]:
        observed = any(a["policy_id"] == row["policy_id"] and a["host_status"] == "observed_correspondence_needs_content_review" for a in record["applications"])
        reports = [v for v in record.get("later_user_feedback", []) if v["user_report"]["policy_id"] == row["policy_id"]]
        helpful = max(reports, key=lambda v: v["recorded_at"])["user_report"]["helpful"] if reports else None
        help_label = "未知" if helpful is None else "用户报告有帮助" if helpful else "用户报告无帮助"
        lines += [f"- {row['policy_id']} v{row['version']}（{row['proposer']}）：{row['behavior_change']}",
                  f"  已提供：{'是' if row['provided'] else '否'}；观察到对应行为：{'是，仅动作/引用对应，内容待审' if observed else '未观察到'}；"
                  f"用户确认帮助：{help_label}；对照支持收益：未建立。",
                  "  选择依据：" + json.dumps(row["selection_reason"], ensure_ascii=False),
                  "  来源：" + "；".join(f"[{ref['sha256'][:12]}](<{ref['path']}>)" for ref in row["source_refs"])]
    candidates = [row for row in record["candidate_records"] if row["status"] == "candidate"]
    if candidates:
        lines += ["", "## 待审改进候选", ""]
        for row in candidates:
            proposal = row["proposal"]
            lines += [f"- {row['candidate_id']}：{proposal['problem']}", "  建议：" + proposal["behavior_change"],
                      "  验证：" + proposal["validation_task"] + "；" + proposal["evaluation"], "  状态：待审，尚未进入日常策略加载。"]
    quarantined = sum(row["status"] == "quarantined_observation" for row in record["candidate_records"])
    deferred = sum(row["status"] == "deferred_observation" for row in record["candidate_records"])
    if quarantined or deferred:
        lines += [f"其他观察已保留：隔离 {quarantined}；待处理 {deferred}。"]
    return lines
