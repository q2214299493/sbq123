"""Render research progress and evidence coverage without scientific promotion."""
from __future__ import annotations


AVAILABILITY = {"provided": "已有且已提供相关观察", "withheld": "宿主已有，相关内容尚未完整提供",
                "not_found": "已查范围未找到，留存情况未知", "not_generated": "有生产证据确认未生成",
                "unknown": "尚未核实可用性"}


def render(receipt, answer, tools):
    lines = ["# 项目科研诊断与方案", "", "研究目标：" + receipt["goal"],
             f"状态：{receipt['status']}；模式：{receipt['mode']}；协议：显式结构化请求→宿主执行→结果回传。",
             f"模型回合启动 {receipt['model_turns_started']}；宿主动作请求 {len(tools.actions)}；"
             f"宿主实际执行 {receipt['host_tool_executions']}；原生模型工具调用 {receipt['native_tool_calls']}。", ""]
    if answer is None:
        lines += ["**尚未取得通过校验的最终模型建议。**", f"首个失败/停止阶段：{receipt['first_failure_stage']}；{receipt['problem']}",
                  "已执行工具得到的资料仍保留；工具回执不冒充模型完成验收。", ""]
    else:
        lines += ["意图：" + answer["intent"], "", "**推荐下一步：" + answer["recommended_next"]["action"] + "**",
                  answer["recommended_next"]["rationale"], ""]
        for row in answer["recommended_next"]["outcomes"]:
            lines += ["- 若 " + row["if"] + "：" + row["then"]]
        for heading, key in [("据工具证据形成的事实陈述（科学适用性待复核）", "facts"), ("工具实际带来的新信息", "new_information")]:
            lines += ["", "## " + heading, ""]
            lines += ["- " + row["statement"] + "（" + ", ".join(row["evidence_ids"]) + "）" for row in answer[key]]
        lines += ["", "## 主要不确定性与材料状态", ""]
        for row in answer["uncertainties"]:
            lines += [f"- {row['question']}；{AVAILABILITY[row['availability']]}；范围/依据：{row['scope_and_basis']}。"]
        lines += ["", "## 假说与判别检查", ""]
        for row in answer["hypotheses"]:
            lines += ["- " + row["claim"] + "；判别检查：" + row["discriminating_check"],
                      "  支持：" + (", ".join(row["supporting_evidence_ids"]) or "未列出") + "；反对证据：" + (", ".join(row["opposing_evidence_ids"]) or "未列出，不代表已排除备选解释")]
        lines += ["", "## 可行选择与条件", ""]
        if not answer["options"]:
            lines += ["当前没有足够依据列出候选方案；不为填表补造方案或成本。"]
        for row in answer["options"]:
            cost = row["cost"]
            quantity = "未知" if cost["status"] == "unknown" else str(cost["value"]) + " " + str(cost["unit"])
            lines += ["", "### " + row["id"] + "：" + row["proposal"], "",
                      "适用条件：" + "；".join(row["conditions"]), "依据：" + ", ".join(row["evidence_ids"]),
                      "代价：" + quantity + "；依据：" + cost["basis"], "风险：" + "；".join(row["risks"]),
                      "验收条件：" + "；".join(row["acceptance_conditions"])]
        lines += ["", "## 证据与计算计划（待所属模块审查）", ""]
        for row in answer["evidence_and_calculation_plan"]:
            lines += ["- " + row["step"], "  前置：" + "；".join(row["prerequisites"]),
                      "  所需产物：" + "；".join(row["outputs_needed"]),
                      "  验收条件：" + "；".join(row["acceptance_conditions"])]
        lines += ["", "科学与使用限制：" + answer["scientific_limits"]]
    lines += ["", "## 实际宿主工具动作与来源", "", "|证据ID|工具|状态|实际执行|完整回执|模型实际收到的摘要|", "|---|---|---|---|---|---|"]
    for action in tools.actions:
        supplied = f"[提供记录](<{action['presented_path']}>)" if action.get("presented_path") else "见该回合输入"
        lines += [f"|{action['evidence_id']}|{action['request']['tool']}|{action['status']}|{action['executed']}|[记录](<{action['result_path']}>)|{supplied}|"]
    lines += ["", f"宿主已冻结 {len(tools.catalog.frozen)} 份源文件；原始字节由宿主留存，模型读取范围以各回合输入/提供记录为准。",
              "目录元数据、宿主已有原文和模型已收到的观察是不同状态；未在本次范围找到资料不等于科研材料未生成。"]
    lines += ["", "引用校验不等于科学有效性验收。结果中的历史复核是有来源的解释；模型综合判断与原始计算证据分别保留。",
              "本次没有提交、停止、重启科学作业，没有修改科学阈值，也没有自动批准策略。",
              "使用反馈与后续科学结果分开记录；实际人工耗时未知时保留未知。", ""]
    return "\n".join(lines)
