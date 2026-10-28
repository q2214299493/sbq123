"""Render the same validated recommendation or an explicit blocked report."""
from __future__ import annotations

import json


def _blocked_next(receipt: dict) -> str:
    visibility = (receipt.get("permission_evidence") or {}).get("auth_visibility", {}).get("status")
    if visibility == "HOST_LOGIN_NOT_VISIBLE_TO_NATIVE_CLIENT":
        return "宿主已登录，但原生客户端无法读取认证存储；先审查 auth-visibility-probe.json 中的存储访问错误，不要重复要求登录或放宽权限。"
    if visibility == "CLI_AUTH_VISIBLE_BUT_ACCOUNT_RPC_EMPTY":
        return "宿主与原生 CLI 均能读取登录，但账户 RPC 为空；检查 App Server 的认证加载差异，不要假定用户未登录。"
    if receipt["first_failure_stage"] == "chatgpt_authentication":
        return "核对既有隔离目录的官方登录状态及认证可见性证据，再处理具体阻断。"
    return "按 run_receipt.json 和 journal.jsonl 核对首个失败阶段的 stderr/退出码，再处理该具体阻断。"


def render_report(receipt: dict, loaded: dict, recommendation: dict | None) -> str:
    case = loaded["case"]
    lines = [f"# RSI 现场诊断：{case['case_id']}", "",
             f"冻结检查点：{receipt['checkpoint']}；用途：{receipt['case_usage']}（本次不作盲测评分）。",
             f"运行状态：{receipt['status']}；真实模型回合：{receipt['model_turns_started']}；"
             f"完成的证据读取：{receipt['actual_tool_calls']}。", ""]
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
            lines.append(f"- 若 {row['if']}：{row['then']}")
        lines += ["", "仍缺少：" + "；".join(model["missing_evidence"]),
                  "费用：" + json.dumps(model["cost"], ensure_ascii=False),
                  "适用范围：" + model["scientific_scope"], "",
                  "引用校验只确认来源和值可定位；因果支持与科学有效性仍待独立复核。", "", "首选检查所用证据："]
        cited = set(check["evidence_ids"])
    for item in case["evidence"]:
        if item["evidence_id"] in cited:
            source = loaded["sources"][item["evidence_id"]]
            label = f"{item['evidence_id']} · {item['pointer']}"
            value = json.dumps(item["value"], ensure_ascii=False)
            lines.append(f"- [{label}](<{source['path']}>) = `{value}`；SHA256 `{source['sha256'][:12]}…`。")
    lines += ["", "本次没有执行或批准任何 GPU/VASP/NEB/DIMER 作业，也没有确认 TS、能垒、节省核时或泛化收益。",
              "完整输入、原始模型回答（若有）与逐阶段记录见本目录。", ""]
    return "\n".join(lines)
