"use strict";
const DATA = JSON.parse(document.getElementById("dashboard-data").textContent);
const RUNS = DATA.runs || [DATA];
let chosen =
  RUNS.find(
    (r) => r.run.id === new URLSearchParams(location.hash.slice(1)).get("run"),
  ) ||
  RUNS.find((r) => r.run.id === DATA.preferred_run_id) ||
  RUNS.find((r) => r.provided_count > 0) ||
  RUNS[0];
let active = new URLSearchParams(location.hash.slice(1)).get("tab") || "usage";
const fmt = (v) =>
  v === null || v === undefined
    ? "未知"
    : typeof v === "object"
      ? JSON.stringify(v, null, 2)
      : String(v);
const date = (v) => {
  if (!v) return "未知";
  const n = new Date(v);
  return isNaN(n)
    ? String(v)
    : n.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
};
function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = fmt(text);
  if (cls) e.className = cls;
  return e;
}
function add(parent, ...children) {
  children
    .flat()
    .filter(Boolean)
    .forEach((c) => parent.append(c));
  return parent;
}
function card(title, cls = "") {
  const e = el("section", null, "card " + cls);
  if (title) e.append(el("h3", title));
  return e;
}
function badge(text, kind = "") {
  return el("span", text, "badge " + kind);
}
function detail(parent, title, value) {
  const d = el("details");
  add(d, el("summary", title), el("pre", value));
  parent.append(d);
  return d;
}
function uri(path) {
  const p = String(path || "").replaceAll("\\", "/");
  if (p.startsWith("//") || !/^([A-Za-z]:\/|\/)/.test(p)) return null;
  return (
    "file://" +
    (p.startsWith("/") ? "" : "/") +
    encodeURI(p).replaceAll("#", "%23").replaceAll("?", "%3F")
  );
}
function source(parent, ref, title = "来源") {
  if (!ref) return;
  const d = el("div", null, "source");
  d.append(el("span", title + "："));
  const href = uri(ref.path);
  if (href) {
    const a = el("a", ref.path);
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    d.append(a);
  } else d.append(el("span", ref.path));
  if (ref.sha256) d.append(el("div", "SHA-256 " + ref.sha256, "mono"));
  parent.append(d);
}
function fields(parent, values) {
  Object.entries(values).forEach(([k, v]) =>
    add(parent, el("div", k, "field-label"), el("div", v)),
  );
}
function next(parent, value) {
  if (!value) {
    parent.append(el("p", "未取得可核验的最终建议。", "muted"));
    return;
  }
  add(
    parent,
    el("p", value.action, "recommendation"),
    el("p", value.rationale),
  );
  (value.outcomes || []).forEach((r) =>
    parent.append(el("p", "若 " + r.if + " → " + r.then, "muted")),
  );
  if (value.evidence_ids)
    parent.append(el("small", "建议引用：" + value.evidence_ids.join("、")));
}
function actionList(parent, actions) {
  if (!actions?.length) {
    parent.append(el("p", "没有可核验的对应动作。", "muted"));
    return;
  }
  const list = el("ol", null, "actions");
  actions.forEach((a) => {
    const item = el("li");
    add(
      item,
      add(
        el("div", null, "action-title"),
        el("code", a.evidence_id + " · " + a.request?.tool),
        badge(a.status || "未知", a.status === "ERROR" ? "error" : ""),
      ),
      el(
        "div",
        a.executed === false
          ? "实际复用（未重复执行）"
          : a.executed === true
            ? "宿主实际执行"
            : "执行/复用未知",
        "right-note",
      ),
    );
    if (a.error) item.append(el("p", a.error, "right-note"));
    (a.sources || []).forEach((s) =>
      source(
        item,
        { path: s.snapshot || s.path, sha256: s.sha256 },
        "工具记录的材料",
      ),
    );
    source(item, a.reference, "动作原件");
    if (a.reused_from_parent)
      detail(item, "父运行复用绑定", a.reused_from_parent);
    list.append(item);
  });
  parent.append(list);
}
const COST_LABELS = {
  model_turns_started: "模型回合",
  host_tool_requests: "宿主请求",
  host_tool_executions: "实际执行",
  repeated_requests_reused: "请求复用",
  host_actions_reused_from_parent: "父运行复用",
  elapsed_seconds: "程序运行秒数",
  tokens_total: "已记录总 token",
};
function costCard(title, costs) {
  const c = card(title);
  const grid = el("div", null, "costs");
  Object.entries(COST_LABELS).forEach(([key, label]) => {
    const value = costs?.[key];
    add(
      grid,
      el("div", label),
      el(
        "div",
        key === "elapsed_seconds" && typeof value === "number"
          ? value.toFixed(2)
          : fmt(value),
        "number",
      ),
    );
  });
  c.append(grid);
  add(c, el("small", "程序运行秒数不等于人工耗时；token 不换算费用。"));
  detail(c, "token 原始口径", costs?.tokens_raw ?? "未知");
  return c;
}
function feedbackReports(run, policy) {
  return (run.feedback || []).flatMap((r) =>
    (r.usage_feedback?.rsi_feedback || [])
      .filter((f) => !policy || f.policy_id === policy)
      .map((f) => ({
        ...f,
        recorded_at: r.recorded_at,
        reference: r.reference,
      })),
  );
}
function layerCards(run) {
  const observed = (run.applications || []).some(
    (a) =>
      a.source_verified &&
      a.host_status === "observed_correspondence_needs_content_review",
  );
  const reports = feedbackReports(run);
  const latest = reports.at(-1);
  const grid = el("div", null, "grid");
  [
    [
      "策略已提供",
      run.provided_count === null || run.provided_count === undefined
        ? "使用状态未知"
        : run.provided_count + " 条进入输入",
      "核对冻结版本及提交输入引用",
    ],
    [
      "观察到对应行为",
      observed
        ? "观察到，内容待审"
        : run.usage_state === "verified"
          ? "未观察到"
          : "未知",
      "动作与引用对应不证明因果",
    ],
    [
      "用户报告帮助",
      !latest
        ? "尚未反馈"
        : latest.helpful === null
          ? "尚未判断"
          : latest.helpful
            ? "报告有帮助"
            : "报告无帮助",
      "采用、帮助和策略采纳分开",
    ],
    ["对照支持收益", "尚未建立", "有配对记录也不自动证明收益"],
  ].forEach(([label, value, note]) => {
    const m = el("div", null, "metric");
    add(
      m,
      el("div", label, "label"),
      el("div", value, "value"),
      el("small", note),
    );
    grid.append(m);
  });
  return grid;
}
function usage(run, parent) {
  parent.append(layerCards(run));
  if (run.usage_state !== "verified") {
    add(
      parent,
      add(
        card("使用状态未知", "notice"),
        el("p", "冻结记录缺失、旧版或未能核验；不能解释成已确认 0 条策略。"),
      ),
    );
  }
  if (run.usage_state === "verified" && !run.selected_policies.length) {
    const c = card("本轮 0 条策略进入输入", "soft");
    const reasons = run.no_policy_explanation?.recorded_reasons;
    const labels = {
      trigger_not_matched: "字面触发条件未匹配",
      experimental_exclusion: "本轮显式排除（配对基线）",
      disabled: "当时已停用",
      policy_budget: "达到可选策略预算",
      required_capability_unavailable: "所需能力不可用",
      unresolved_explicit_conflict: "显式冲突未解决",
    };
    if (reasons?.length)
      reasons.forEach((r) =>
        c.append(el("p", r.policy_id + "：" + (labels[r.reason] || r.reason))),
      );
    else c.append(el("p", "冻结记录未列出当时未选择的具体原因。"));
    if (run.no_policy_explanation?.current_library_note)
      c.append(
        el("p", run.no_policy_explanation.current_library_note, "muted"),
      );
    parent.append(c);
  }
  (run.selected_policies || []).forEach((policy) => {
    const c = card(policy.behavior_change || policy.policy_id);
    add(
      c,
      add(
        el("div", null, "chips"),
        badge(policy.policy_id + " v" + policy.version),
        badge("当时：" + fmt(policy.status_at_run), "warning"),
        badge(policy.proposer || "来源未知"),
      ),
      el("p", "选择依据：" + fmt(policy.selection_reason)),
      el(
        "p",
        "进入模型输入：" +
          (policy.provided === true
            ? "是"
            : policy.provided === false
              ? "否"
              : "未知"),
      ),
    );
    (policy.model_inputs || []).forEach((r) => source(c, r, "提交输入"));
    (policy.source_refs || []).forEach((r) => source(c, r, "经验来源"));
    const applications = (run.applications || []).filter(
      (a) => a.policy_id === policy.policy_id,
    );
    applications.forEach((a) => {
      add(
        c,
        el("div", "模型声称的应用意图", "field-label"),
        el("p", a.model_claim?.intent || "没有应用声明"),
        badge(
          a.host_status,
          a.host_status === "rejected" || !a.source_verified ? "warning" : "",
        ),
      );
      if (a.reason) c.append(el("p", a.reason, "muted"));
      actionList(c, a.action_details);
      (a.outputs || []).forEach((o) => {
        const d = card("最终建议中的对应内容");
        add(d, el("code", o.pointer), el("pre", o.content));
        c.append(d);
      });
      c.append(el("small", a.validation_scope));
    });
    const reports = feedbackReports(run, policy.policy_id);
    if (!reports.length) c.append(el("p", "用户帮助反馈：尚未反馈。", "muted"));
    reports.forEach((r) => {
      add(
        c,
        el(
          "p",
          date(r.recorded_at) +
            " · " +
            (r.helpful === null
              ? "尚未判断"
              : r.helpful
                ? "报告有帮助"
                : "报告无帮助") +
            "：" +
            r.reason,
        ),
      );
      source(c, r.reference, "反馈原件");
    });
    parent.append(c);
  });
  const recommendation = card("本次实际研究建议");
  next(recommendation, run.recommendation);
  if (run.answer && Object.keys(run.answer).length)
    detail(recommendation, "完整结构化回答（模型判断，未作科学验收）", run.answer);
  parent.append(recommendation);
  const all = card("本轮全部宿主动作与材料");
  actionList(all, run.actions);
  parent.append(all);
}
function answerColumn(title, row) {
  const c = card(title);
  next(c, row?.answer?.recommended_next);
  (row?.answer?.options || []).forEach((o) =>
    add(c, el("div", o.id, "field-label"), el("p", o.proposal)),
  );
  detail(c, "完整实际结构化回答（模型判断，未作科学验收）", row?.answer || "未知");
  source(c, row?.receipt_ref, "实际回执");
  if (row?.actions?.length) {
    const d = el("details");
    add(d, el("summary", "动作与错误"));
    actionList(
      d,
      row.actions.filter((a) => a.request),
    );
    c.append(d);
  }
  return c;
}
function changes(run, parent) {
  const comparison = run.comparison || {};
  const heading = card(
    comparison.kind === "paired"
      ? "已登记真实配对"
      : comparison.kind === "continuation"
        ? "接续变化"
        : comparison.registered_source_count > 0
          ? "已登记来源，尚无可核验配对"
          : "未运行 / 未登记对照",
  );
  heading.append(
    el(
      "p",
      comparison.kind === "unpaired"
        ? "仅展示本次实际动作与建议，不生成假想基线。"
        : "并列真实记录与确定性文本差异；变化不能自动归因于 RSI。",
      "muted",
    ),
  );
  parent.append(heading);
  (comparison.paired || []).forEach((p) => {
    add(
      parent,
      add(
        el("div", null, "columns"),
        answerColumn("实际基线", p.baseline),
        answerColumn("实际试用", p.candidate),
      ),
      add(
        el("div", null, "columns"),
        costCard("基线成本", p.baseline.costs),
        costCard("试用成本", p.candidate.costs),
      ),
    );
    const c = card("配对条件与审阅范围");
    add(
      c,
      badge(
        p.input_conditions_rechecked
          ? "输入条件重新核对一致"
          : "输入条件未通过重新核对",
        p.input_conditions_rechecked ? "" : "warning",
      ),
      el("p", p.validation_scope),
    );
    detail(c, "记录的条件检查", p.condition_check);
    detail(
      c,
      "确定性文本差异（不解释原因）",
      p.text_diff || "上述字段没有文本差异",
    );
    detail(c, "原内容审阅记录", p.content_review);
    source(c, p.reference, "配对来源");
    parent.append(c);
  });
  const continuation = comparison.continuation;
  if (continuation) {
    const c = card("接续变化 · 不是控制实验");
    add(c, el("p", continuation.attribution || "父运行来源未能核验。"));
    if (continuation.available) {
      add(
        parent,
        add(
          el("div", null, "columns"),
          answerColumn("上轮实际建议", continuation.parent),
          answerColumn("本轮实际建议", { answer: run.answer, actions: run.actions, receipt_ref: run.run_receipt_ref }),
        ),
      );
      detail(
        c,
        "判断 / 证据文本变化",
        continuation.text_diff || "没有文本差异",
      );
      detail(c, "来源重新核验", continuation.source_revalidation);
      detail(c, "上轮策略版本（当时记录）", continuation.parent.policies);
      detail(c, "本轮策略版本（当时记录）", run.selected_policies);
      add(parent, add(el("div", null, "columns"), costCard("上轮实际成本", continuation.parent.costs), costCard("本轮实际成本", run.costs)));
      c.append(
        el(
          "p",
          "本轮父运行实际复用：" +
            fmt(run.costs?.host_actions_reused_from_parent),
        ),
      );
    }
    source(c, continuation.reference, "接续绑定");
    parent.append(c);
  }
  if (comparison.kind === "unpaired") {
    const c = card("本次建议");
    next(c, run.recommendation);
    parent.append(c);
  }
  if (comparison.kind !== "paired" && !continuation?.available)
    parent.append(costCard("本次成本", run.costs));
  (comparison.unsupported || []).forEach((r) => {
    const c = card("其他配对来源");
    add(c, el("p", r.message));
    source(c, r.reference);
    parent.append(c);
  });
  (run.selected_policies || []).forEach((p) => {
    const c = card("策略描述的旧做法（不是实际基线回答）");
    c.append(el("p", p.definition?.previous_behavior || "未知"));
    parent.append(c);
  });
}
function candidates(run, parent) {
  const rows = run.candidates || {};
  const c = card("本轮改进候选与观察");
  if (!rows.known) c.append(el("p", "候选记录未知。"));
  else {
    const names = {
      candidate: "新增完整候选",
      observation: "普通观察",
      quarantined_observation: "隔离观察",
      deferred_observation: "延后观察",
      existing_candidate_source_added: "重复候选追加来源",
    };
    const grid = el("div", null, "costs");
    Object.entries(names).forEach(([key, label]) =>
      add(grid, el("div", label), el("div", rows.counts[key] ?? 0, "number")),
    );
    c.append(grid);
    if (!(rows.expanded || []).length)
      c.append(el("p", "没有合格的新完整候选；不强行补建议。", "muted"));
    (rows.expanded || []).forEach((r) =>
      detail(c, "待审候选 " + r.candidate_id, r.proposal),
    );
    detail(c, "所有已保留观察 / 提出记录", rows.records || []);
  }
  add(c, el("small", rows.scope || run.software_change));
  parent.append(c);
}
function projectSummary(parent) {
  if (RUNS.length < 2) return;
  const c = card("已登记运行范围汇总");
  c.append(el("p", RUNS.length + " 次运行；以下是记录数量，不是自主改进或科研价值分数。", "muted"));
  const known = RUNS.every(r => r.candidates?.known);
  const grid = el("div", null, "costs");
  const names = {candidate:"合格新完整候选",observation:"普通观察",quarantined_observation:"隔离观察",deferred_observation:"延后观察",existing_candidate_source_added:"重复候选追加来源"};
  Object.entries(names).forEach(([key,label]) => add(grid, el("div",label), el("div",known ? RUNS.reduce((n,r)=>n+(r.candidates.counts[key]??0),0) : "未知", "number")));
  c.append(grid);
  parent.append(c);
}
function policies(run, parent) {
  const current = run.current_policies;
  const c = card("运行时版本与策略库当前状态");
  if (!current)
    c.append(el("p", "当前策略库不可用或未登记；不能用当前状态补写历史。"));
  (current?.policies || []).forEach((p) => {
    const def = p.definition;
    const old = (run.selected_policies || []).filter(
      (s) => s.policy_id === def.policy_id,
    );
    const d = el("div", null, "detail-row");
    add(
      d,
      el("h3", def.policy_id),
      add(
        el("div", null, "chips"),
        badge(
          "库中：v" + def.version + " · " + p.status,
          p.status === "trial" ? "warning" : "",
        ),
        badge(def.proposer),
      ),
      el(
        "p",
        old.length
          ? "本轮冻结：" +
              old
                .map((s) => "v" + s.version + " · " + s.status_at_run)
                .join("；")
          : "本轮没有该策略的已选冻结记录。",
      ),
    );
    const list = el("ol", null, "timeline");
    add(
      list,
      add(
        el("li"),
        el(
          "div",
          date(p.registered_at || def.proposed_at) + " · candidate 登记",
        ),
      ),
    );
    (p.reviews || []).forEach((r) => {
      const li = el("li");
      add(
        li,
        el("div", date(r.recorded_at) + " · " + r.status),
        el("small", r.reviewer + "；" + r.validation_scope),
        el("p", r.reason),
      );
      source(li, r.request_ref, "独立复核");
      list.append(li);
    });
    d.append(list);
    (p.frozen_sources || []).forEach((r) => source(d, r, "提出来源"));
    c.append(d);
  });
  if (current && !current.policies.length)
    c.append(el("p", "当前库没有策略记录。"));
  parent.append(c);
}
function feedbackHistory(run, parent) {
  const c = card("追加反馈时间线");
  if (!run.feedback?.length) c.append(el("p", "尚未反馈。"));
  (run.feedback || []).forEach((r, i) => {
    const usage = r.usage_feedback || {};
    const d = el("div", null, "detail-row");
    add(
      d,
      el(
        "h3",
        date(r.recorded_at) +
          (i === run.feedback.length - 1 ? " · 最新反馈" : " · 保留的历史反馈"),
      ),
      el(
        "p",
        "科研建议采用：" +
          (usage.adopted === true
            ? "采用"
            : usage.adopted === false
              ? "未采用"
              : "尚未决定"),
      ),
      el("p", usage.followup_notes || "未填写具体说明"),
      el(
        "small",
        "实测人工秒数 · 准备 " +
          fmt(usage.human_preparation_seconds) +
          " / 评阅 " +
          fmt(usage.human_review_seconds) +
          " / 纠正 " +
          fmt(usage.human_correction_seconds),
      ),
    );
    source(d, r.reference, "反馈原件");
    c.append(d);
  });
  (run.feedback_index || []).forEach((r) => {
    c.append(el("p", r.label, "form-status"));
    source(c, r.reference, "索引失败记录");
  });
  parent.append(c);
}
function selectControl(label, options, parent) {
  const l = el("label", label);
  const s = el("select");
  options.forEach(([value, text]) => {
    const o = el("option", text);
    o.value = value;
    s.append(o);
  });
  l.append(s);
  parent.append(l);
  return s;
}
function checkControl(parent, label, value, checked = false) {
  const l = el("label", null, "check");
  const i = el("input");
  i.type = "checkbox";
  i.value = value;
  i.checked = checked;
  add(l, i, el("span", label));
  parent.append(l);
  return i;
}
function ps(value) {
  return "'" + String(value).replaceAll("'", "''") + "'";
}
function feedbackForm(run, parent) {
  const c = card("轻量使用反馈");
  const form = el("form");
  form.addEventListener("submit", (e) => e.preventDefault());
  const group = el("div", null, "form-group");
  const adopted = selectControl(
    "1. 是否采用本次建议",
    [
      ["null", "尚未决定"],
      ["true", "采用"],
      ["false", "未采用"],
    ],
    group,
  );
  form.append(group);
  const options = el("div");
  const optionChecks = (run.answer?.options || []).map((o) =>
    checkControl(options, o.id + " · " + o.proposal, o.id),
  );
  if (optionChecks.length) {
    detail(
      form,
      "部分采用时选择实际方案（只有“采用”时生效）",
      "",
    ).replaceChildren(el("summary", "部分采用时选择实际方案"), options);
    optionChecks.forEach((i) => (i.disabled = true));
    adopted.addEventListener("change", () =>
      optionChecks.forEach((i) => {
        i.disabled = adopted.value !== "true";
        if (i.disabled) i.checked = false;
      }),
    );
  }
  const noteGroup = el("div", null, "form-group");
  const label = el("label", "2. 具体帮助或额外负担（一句话）");
  const note = el("textarea");
  note.setAttribute("aria-label", "具体帮助或额外负担");
  note.placeholder = "说明实际采用了什么、哪里有帮助或增加了什么负担。";
  add(label, note);
  noteGroup.append(label);
  form.append(noteGroup);
  const policyForms = [];
  (run.selected_policies || [])
    .filter((p) => p.source_verified)
    .forEach((p) => {
      const field = el("fieldset");
      field.append(el("legend", p.policy_id + " · 帮助判断（与采用分开）"));
      const helpful = selectControl(
        "是否对这条经验形成帮助判断",
        [
          ["null", "尚未判断"],
          ["true", "有具体帮助"],
          ["false", "没有帮助"],
        ],
        field,
      );
      const apps = (run.applications || []).filter(
        (a) => a.policy_id === p.policy_id && a.source_verified,
      );
      const refs = [...new Set(apps.flatMap((a) => a.action_refs || []))];
      const outputs = [...new Set(apps.flatMap((a) => a.output_refs || []))];
      const actions = refs.map((id) =>
        checkControl(field, "动作 " + id, id, true),
      );
      const pointers = outputs.map((id) =>
        checkControl(field, "建议位置 " + id, id, true),
      );
      policyForms.push({ policy: p.policy_id, helpful, actions, pointers });
      form.append(field);
    });
  const time = el("fieldset");
  time.append(el("legend", "3. 实测人工时间（可选）"));
  const measured = checkControl(
    time,
    "我填写的是实际测量的秒数；未测量保持空白。",
    "measured",
  );
  const times = el("div", null, "times");
  const timeInputs = {};
  [
    ["human_preparation_seconds", "准备"],
    ["human_review_seconds", "评阅"],
    ["human_correction_seconds", "纠正"],
  ].forEach(([key, text]) => {
    const l = el("label", text + "秒数");
    const i = el("input");
    i.type = "number";
    i.min = "0";
    i.step = "any";
    i.disabled = true;
    i.setAttribute("aria-label", text + "实测秒数");
    l.append(i);
    times.append(l);
    timeInputs[key] = i;
  });
  measured.addEventListener("change", () =>
    Object.values(timeInputs).forEach((i) => {
      i.disabled = !measured.checked;
      if (i.disabled) i.value = "";
    }),
  );
  time.append(times);
  form.append(time);
  const button = el("button", "导出反馈 JSON（尚未写入）", "primary");
  button.type = "button";
  const status = el(
    "p",
    "导出只下载请求文件，不会保存到运行或策略库。",
    "form-status",
  );
  const preview = el("pre");
  preview.hidden = true;
  button.addEventListener("click", () => {
    const value = {
      adopted: JSON.parse(adopted.value),
      evidence_effectiveness: [],
      repeated_checks: [],
      followup_notes: note.value,
      scientific_result_reference: null,
      rsi_feedback: [],
    };
    try {
      if (adopted.value === "true" && optionChecks.some((i) => i.checked))
        value.adopted_option_ids = optionChecks
          .filter((i) => i.checked)
          .map((i) => i.value);
      Object.entries(timeInputs).forEach(([key, i]) => {
        value[key] =
          !measured.checked || i.value === "" ? null : Number(i.value);
        if (
          value[key] !== null &&
          (!Number.isFinite(value[key]) || value[key] < 0)
        )
          throw new Error("实测秒数必须为非负数或留空。");
      });
      policyForms.forEach((p) => {
        if (p.helpful.value === "null") return;
        const row = {
          policy_id: p.policy,
          helpful: JSON.parse(p.helpful.value),
          reason: note.value,
          action_refs: p.actions.filter((i) => i.checked).map((i) => i.value),
          output_refs: p.pointers.filter((i) => i.checked).map((i) => i.value),
        };
        if (
          row.helpful &&
          (!row.reason.trim() ||
            !row.action_refs.length ||
            !row.output_refs.length)
        )
          throw new Error(
            "确认有帮助时，请填写具体原因并保留实际动作和建议引用。",
          );
        value.rsi_feedback.push(row);
      });
      const text = JSON.stringify(value, null, 2);
      preview.textContent = text;
      preview.hidden = false;
      const blob = new Blob([text + "\n"], {
        type: "application/json;charset=utf-8",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download =
        "rsi-feedback-" + (run.run.id || "unknown").slice(0, 12) + ".json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      status.textContent =
        "已导出请求；尚未写入。请用下方 feedback 命令保存，通过校验后页面自动刷新。";
      status.className = "form-status";
    } catch (error) {
      status.textContent = error.message;
      status.className = "form-status error";
    }
  });
  add(form, button, status, preview);
  const sourceRoot = DATA.source_root || run.source_root;
  const command =
    "Set-Location -LiteralPath " +
    ps(sourceRoot || "源码目录") +
    "\n& " +
    ps(DATA.python || run.python || "python") +
    " -m scripts.research_assistant.cli feedback --run " +
    ps(run.run.path) +
    " --request '下载后的反馈 JSON 完整路径'";
  detail(form, "下载后用现有校验入口保存（替换文件路径）", command);
  c.append(form);
  parent.append(c);
}
function errors(run, parent) {
  if (!run.source_errors?.length) return;
  const c = card(run.source_errors.length + " 个来源需处理", "notice");
  c.append(el("p", "下列来源未用于结论；其他已核验记录仍可查看。"));
  run.source_errors.forEach((r) => {
    const d = el("div", null, "detail-row");
    add(d, el("code", r.role), el("p", r.error), el("pre", r.source));
    c.append(d);
  });
  parent.append(c);
}
function draw() {
  if (!chosen) {
    document
      .getElementById("content")
      .append(el("p", "没有已登记运行。", "empty-project"));
    return;
  }
  if (!["usage", "changes", "feedback"].includes(active)) active = "usage";
  const header = document.getElementById("run-header");
  header.replaceChildren();
  add(
    header,
    el(
      "p",
      chosen.run.name + " · " + (chosen.run.id || "回执未知").slice(0, 12),
      "eyebrow",
    ),
    el("h1", chosen.run.goal || "运行来源失效或未知"),
    add(
      el("div", null, "metadata"),
      badge(chosen.run.status || "未知"),
      badge(
        chosen.run.mode === "evaluation"
          ? "评测模式"
          : chosen.run.mode === "daily"
            ? "日常模式"
            : "模式未知",
      ),
      badge(chosen.run.run_mode || "运行方式未知"),
      el("span", "运行产生时间：未知（原回执未记录）"),
      el("span", "策略冻结：" + date(chosen.policy_frozen_at)),
    ),
  );
  source(header, chosen.run_receipt_ref, "运行回执");
  if (chosen.run.problem)
    add(
      header,
      el(
        "p",
        fmt(chosen.run.first_failure_stage) + "：" + chosen.run.problem,
        "form-status error",
      ),
    );
  document.getElementById("updated").textContent =
    "页面更新（上海时间）\n" + date(DATA.generated_at || chosen.generated_at);
  const parent = document.getElementById("content");
  parent.replaceChildren();
  document.querySelectorAll("[data-tab]").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.tab === active));
    b.tabIndex = b.dataset.tab === active ? 0 : -1;
  });
  parent.setAttribute("aria-labelledby", "tab-" + active);
  if (active === "usage") usage(chosen, parent);
  else if (active === "changes") changes(chosen, parent);
  else {
    projectSummary(parent);
    policies(chosen, parent);
    candidates(chosen, parent);
    feedbackHistory(chosen, parent);
    feedbackForm(chosen, parent);
  }
  errors(chosen, parent);
  errors({ source_errors: DATA.source_errors }, parent);
  historyReplace();
}
function historyReplace() {
  const q = new URLSearchParams({
    run: chosen.run.id || "unknown",
    tab: active,
  });
  window.history.replaceState(null, "", "#" + q.toString());
}
const selector = document.getElementById("run-select");
RUNS.forEach((r) => {
  const o = el(
    "option",
    r.run.name +
      " · " +
      (r.run.id || "未知").slice(0, 10) +
      " · " +
      (r.run.status || "未知"),
  );
  o.value = r.run.id || r.run.path;
  selector.append(o);
});
if (chosen) selector.value = chosen.run.id || chosen.run.path;
selector.addEventListener("change", () => {
  chosen = RUNS.find((r) => (r.run.id || r.run.path) === selector.value);
  draw();
});
document.querySelectorAll("[data-tab]").forEach((b, i, all) => {
  b.addEventListener("click", () => {
    active = b.dataset.tab;
    draw();
  });
  b.addEventListener("keydown", (e) => {
    if (["ArrowRight", "ArrowLeft"].includes(e.key)) {
      e.preventDefault();
      const next =
        all[(i + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length];
      active = next.dataset.tab;
      draw();
      next.focus();
    }
  });
});
document
  .getElementById("reload")
  .addEventListener("click", () => location.reload());
draw();
