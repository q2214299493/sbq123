"""Render the same validated recommendation or an explicit blocked report."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file
from .learning_evidence import exact_keys
from .review_evidence import safe_file


def _reference(reference: dict) -> dict:
    exact_keys(reference, {"path", "sha256"})
    path = safe_file(Path(reference["path"]), Path(reference["path"]).parent)
    if sha256_file(path) != reference["sha256"]:
        raise ValueError("stale report context reference")
    return reference


def _texts(values: list):
    if not isinstance(values, list) or len(values) > 12 or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("report context requires bounded nonempty text entries")


def load_review_context(path: Path | None, loaded: dict) -> tuple[dict | None, dict | None]:
    """Host-only follow-up notes; never included in model instructions or evidence."""
    if path is None:
        return None, None
    path = safe_file(path.absolute(), path.absolute().parent)
    document = load_json_object(path)
    exact_keys(document, {"schema_version", "case_id", "review_kind", "parent_run", "new_information", "judgment_changes",
                          "metric_definitions", "historical_review_source", "historical_interpretations", "remaining_unknown"})
    if type(document["schema_version"]) is not int or document["schema_version"] != 1 \
            or document["case_id"] != loaded["case"]["case_id"] or document["review_kind"] != "unblinded_followup":
        raise ValueError("report context version/case/kind mismatch")
    parent = load_json_object(Path(_reference(document["parent_run"])["path"]))
    if parent["task_id"] != loaded["case"]["group_id"]:
        raise ValueError("report context parent task mismatch")
    _reference(document["historical_review_source"])
    for name in ("new_information", "remaining_unknown"):
        _texts(document[name])
    allowed = set(loaded["sources"])
    for name, fields in (("judgment_changes", {"judgment", "before", "after", "change", "evidence_ids"}),
                         ("historical_interpretations", {"claim", "primary_evidence_assessment", "evidence_ids"})):
        rows = document[name]
        if not isinstance(rows, list) or len(rows) > 12:
            raise ValueError("too many report context rows")
        for row in rows:
            exact_keys(row, fields)
            _texts([v for k, v in row.items() if k != "evidence_ids"])
            ids = row["evidence_ids"]
            _texts(ids)
            if not set(ids) <= allowed or len(ids) != len(set(ids)):
                raise ValueError("report context cites unlisted or duplicate evidence")
            if name == "judgment_changes" and row["change"] not in {"strengthened", "weakened", "unchanged"}:
                raise ValueError("unsupported judgment change")
    metrics = document["metric_definitions"]
    if not isinstance(metrics, list) or len(metrics) > 12:
        raise ValueError("too many metric definitions")
    for row in metrics:
        exact_keys(row, {"evidence_id", "label", "meaning", "unit", "comparison"})
        _texts(list(row.values()))
        if row["evidence_id"] not in allowed:
            raise ValueError("metric definition cites unlisted evidence")
    return document, {"path": str(path), "sha256": sha256_file(path)}


def _blocked_next(receipt: dict) -> str:
    visibility = (receipt.get("permission_evidence") or {}).get("auth_visibility", {}).get("status")
    if visibility == "HOST_LOGIN_NOT_VISIBLE_TO_NATIVE_CLIENT":
        return "宿主已登录，但原生客户端无法读取认证存储；先审查 auth-visibility-probe.json 中的存储访问错误，不要重复要求登录或放宽权限。"
    if visibility == "CLI_AUTH_VISIBLE_BUT_ACCOUNT_RPC_EMPTY":
        return "宿主与原生 CLI 均能读取登录，但账户 RPC 为空；检查 App Server 的认证加载差异，不要假定用户未登录。"
    if receipt["first_failure_stage"] == "chatgpt_authentication":
        return "核对既有隔离目录的官方登录状态及认证可见性证据，再处理具体阻断。"
    return "按 run_receipt.json 和 journal.jsonl 核对首个失败阶段的 stderr/退出码，再处理该具体阻断。"


def _ids(values: list[str]) -> str:
    return "、".join(f"`{v}`" for v in values) if values else "无已列出的证据"


def _model_sections(model: dict) -> list[str]:
    lines = ["", "## 主要假说与备选解释", ""]
    if not model["hypotheses"]:
        lines.append("结构化建议未列出额外假说，不补造备选解释。")
    for index, row in enumerate(model["hypotheses"], 1):
        lines += [f"**假说 {index}：{row['claim']}**", "", f"- 支持：{_ids(row['supporting_evidence_ids'])}。",
                  f"- 反对或限制证据：{_ids(row['opposing_evidence_ids'])}。", f"- 不确定性：{row['uncertainty']}", ""]
    lines += ["## 条件性方案（均未批准执行）", ""]
    if not model["conditional_proposals"]:
        lines.append("结构化建议中的条件性方案为空；本报告未补造策略修改建议。")
    for index, row in enumerate(model["conditional_proposals"], 1):
        lines += [f"**方案 {index} 的条件**：{row['condition']}", "", f"条件满足后考虑：{row['proposal']}", "",
                  f"证据：{_ids(row['evidence_ids'])}。", ""]
    lines += ["", "<details>", "<summary>模型完整观察与引用</summary>", ""]
    lines += [f"- {row['statement']}（{_ids(row['evidence_ids'])}）" for row in model["observations"]]
    lines += ["", "</details>"]
    return lines


def _context_sections(context: dict | None) -> list[str]:
    if context is None:
        return ["", "本次未绑定跨轮新增信息或指标定义记录；不自动推断相较上一轮的变化。"]
    lines = ["", "## 本轮新增信息（宿主原始证据核对）", ""]
    lines += [f"- {text}" for text in context["new_information"]]
    lines += ["", "## 判断变化（宿主证据复核，区别于模型判断）", ""]
    labels = {"strengthened": "增强", "weakened": "减弱", "unchanged": "保持"}
    for row in context["judgment_changes"]:
        lines += [f"- **{row['judgment']}：{labels[row['change']]}**。之前：{row['before']}；现在：{row['after']}。证据：{_ids(row['evidence_ids'])}。"]
    lines += ["", "## 关键指标：含义、单位与比较对象", "",
              "|指标|含义|单位|比较对象|", "|---|---|---|---|"]
    for row in context["metric_definitions"]:
        cells = [row['label'] + ' · ' + row['evidence_id'], row['meaning'], row['unit'], row['comparison']]
        lines.append("|" + "|".join(str(v).replace("|", "\\|").replace("\n", " ") for v in cells) + "|")
    lines += ["", "## 历史事后复核中的解释", "",
              "以下单独引用历史复核，不作为已读取的原始异常证据；此段只在宿主报告中展示，未发给模型。", ""]
    for row in context["historical_interpretations"]:
        lines.append(f"- 历史陈述：{row['claim']}；本轮原始证据对照：{row['primary_evidence_assessment']}（{_ids(row['evidence_ids'])}）。")
    reference = context["historical_review_source"]
    lines += [f"来源：[历史复核](<{reference['path']}>)；SHA256 `{reference['sha256']}`。", ""]
    return lines


def _all_citations(value) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_all_citations(v) for v in value))
    if isinstance(value, dict):
        result = set()
        for key, item in value.items():
            result.update(item if key.endswith("evidence_ids") else _all_citations(item))
        return result
    return set()


def render_report(receipt: dict, loaded: dict, recommendation: dict | None, context: dict | None = None) -> str:
    case = loaded["case"]
    lines = [f"# RSI 现场诊断：{case['case_id']}", "",
             f"材料冻结/复核截至时间：{receipt['checkpoint']}；用途：{receipt['case_usage']}（本次不作盲测评分）。",
             f"运行状态：{receipt['status']}；真实模型回合：{receipt['model_turns_started']}；"
             f"模型工具调用：{receipt['actual_tool_calls']}。", ""]
    if receipt.get("evidence_access") == "frozen-context":
        lines += ["证据方式：冻结上下文；原文件和值由宿主在模型调用前后核对，模型工具调用数为 0。", ""]
    cited = set()
    if receipt["status"].endswith("ADMITTED_NO_TURN"):
        lines += ["仅完成 live 预检；未发送 turn/start，未生成新诊断。", "",
                  "下一项检查：使用相同入口和冻结材料，去掉 --probe-live，运行一次真实诊断。"]
    elif recommendation is None:
        lines += ["**未生成新诊断。** 下列仅是冻结材料中的原始观察，不是模型建议。", "",
                  f"首个阻断阶段：`{receipt['first_failure_stage']}`。{receipt['problem'] or ''}",
                  "下一项软件检查：" + _blocked_next(receipt),
                  "当前没有可采用的模型科学检查建议。", "",
                  "冻结材料（节选）："]
        cited = {e["evidence_id"] for e in case["evidence"][:8]}
    else:
        model = recommendation["recommendation"]
        diagnosis, check = model["diagnosis"], model["next_check"]
        lines += [f"最重要的发现：{model['observations'][0]['statement']}",
                  f"模型因果判断（未独立复核）：{diagnosis['causal_status']}；{diagnosis['causal_claim'] or '原因未知，需补证据。'}", "",
                  f"**现在先检查：{check['action']}**", f"依据：{check['rationale']}", ""]
        for row in check["expected_outcomes"]:
            lines += [f"- 条件：{row['if']}", f"  对应判断：{row['then']}"]
        lines += _model_sections(model)
        lines += _context_sections(context)
        unknown = list(dict.fromkeys(model["missing_evidence"] + (context["remaining_unknown"] if context else [])))
        lines += ["", "## 仍然未知", ""] + [f"- {text}" for text in unknown]
        cost = model["cost"]
        quantity = "未知（未测量）" if cost["status"] == "unknown" else f"{cost['status']}；{cost['value']} {cost['unit']}"
        lines += ["", f"成本：{quantity}。依据：{cost['basis']}",
                  "适用范围：" + model["scientific_scope"], "",
                  "程序引用校验仅确认来源和值；宿主复核与模型判断分别列示，均不授予作业执行或TS/能垒验收权限。", "", "<details>", "<summary>全部建议所用证据索引</summary>", ""]
        cited = _all_citations(model) | _all_citations(context) | ({row["evidence_id"] for row in context["metric_definitions"]} if context else set())
    for item in case["evidence"]:
        if item["evidence_id"] in cited:
            source = loaded["sources"][item["evidence_id"]]
            label = f"{item['evidence_id']} · {item['pointer']}"
            value = json.dumps(item["value"], ensure_ascii=False)
            if len(value) > 240:
                value = value[:160] + "…（完整值见来源文件）…" + value[-60:]
            lines.append(f"- [{label}](<{source['path']}>) = `{value}`；SHA256 `{source['sha256'][:12]}…`。")
    if recommendation is not None:
        lines += ["", "</details>"]
    lines += ["", "本次没有执行或批准任何 GPU/VASP/NEB/DIMER 作业，也没有确认 TS、能垒、节省核时或泛化收益。",
              "完整输入、原始模型回答（若有）与逐阶段记录见本目录。", ""]
    return "\n".join(lines)
