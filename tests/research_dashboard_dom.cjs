/* DOM-only client tests. No browser, network, model, or feedback write. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { JSDOM, VirtualConsole } = createRequire(
  path.resolve(process.argv[2], "package.json"),
)("jsdom");
const html = fs.readFileSync(process.argv[3], "utf8");
const errors = [],
  downloads = [],
  blobs = [];
const console = new VirtualConsole();
console.on("jsdomError", (e) => errors.push(e.message));
function open(source) {
  return new JSDOM(source, {
    url: "https://rsi-dashboard.invalid/",
    runScripts: "dangerously",
    virtualConsole: console,
    beforeParse(window) {
      window.Blob = Blob;
      window.URL.createObjectURL = (blob) => {
        blobs.push(blob);
        return "blob:unit-test";
      };
      window.URL.revokeObjectURL = () => {};
      window.HTMLAnchorElement.prototype.click = function () {
        downloads.push(this.download);
      };
    },
  });
}
(async () => {
  const dom = open(html),
    w = dom.window,
    d = w.document;
  assert.equal(errors.length, 0, errors.join("\n"));
  assert.equal(d.querySelectorAll("#run-select option").length, 4);
  assert.match(d.getElementById("content").textContent, /1 条进入输入/);
  assert.match(d.getElementById("content").textContent, /观察到，内容待审/);
  assert.match(d.body.textContent, /尚未建立/);
  d.getElementById("tab-changes").click();
  assert.equal(
    d.getElementById("tab-changes").getAttribute("aria-selected"),
    "true",
  );
  assert.match(d.getElementById("content").textContent, /实际基线/);
  assert.match(d.getElementById("content").textContent, /实际试用/);
  assert.match(d.getElementById("content").textContent, /84,?604|84604/);
  d.getElementById("tab-feedback").click();
  assert.match(d.getElementById("content").textContent, /trial/);
  assert.match(d.getElementById("content").textContent, /没有合格的新完整候选/);
  const note = d.querySelector("textarea");
  note.value = "DOM 单元测试：具体帮助，不是真实用户反馈。";
  const helpful = d.querySelector("fieldset select");
  helpful.value = "true";
  helpful.dispatchEvent(new w.Event("change", { bubbles: true }));
  const button = [...d.querySelectorAll("button")].find((b) =>
    b.textContent.includes("导出反馈 JSON"),
  );
  button.click();
  assert.equal(blobs.length, 1);
  const exported = JSON.parse(await blobs[0].text());
  assert.equal(exported.adopted, null);
  assert.equal(exported.human_review_seconds, null);
  assert.equal(exported.rsi_feedback[0].helpful, true);
  assert.ok(exported.rsi_feedback[0].action_refs.includes("E002"));
  assert.ok(exported.rsi_feedback[0].output_refs.includes("/recommended_next"));
  assert.match(d.querySelector(".form-status").textContent, /尚未写入/);
  const selector = d.getElementById("run-select");
  selector.value = [...selector.options].find((o) =>
    o.textContent.includes("nontrigger_baseline"),
  ).value;
  selector.dispatchEvent(new w.Event("change", { bubbles: true }));
  d.getElementById("tab-usage").click();
  assert.match(
    d.getElementById("content").textContent,
    /本轮 0 条策略进入输入/,
  );
  assert.equal(errors.length, 0, errors.join("\n"));
  dom.window.close();
  const match = html.match(
    /<script type="application\/json" id="dashboard-data">([\s\S]*?)<\/script>/,
  );
  const data = JSON.parse(match[1]);
  const fixture = structuredClone(data.runs[0]);
  fixture.run.goal =
    '</script><img src=x onerror="globalThis.BAD=1"><script>BAD=1</script>';
  fixture.usage_state = "unknown";
  fixture.provided_count = null;
  fixture.selected_policies = [];
  fixture.applications = [];
  data.runs = [fixture];
  const serialized = JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e");
  const maliciousHtml = html.replace(match[1], () => serialized);
  const safe = open(maliciousHtml);
  assert.equal(safe.window.BAD, undefined);
  assert.equal(safe.window.document.querySelectorAll("img").length, 0);
  assert.equal(
    safe.window.document.querySelector("h1").textContent,
    fixture.run.goal,
  );
  assert.match(
    safe.window.document.getElementById("content").textContent,
    /使用状态未知/,
  );
  assert.doesNotMatch(
    safe.window.document.getElementById("content").textContent,
    /本轮 0 条策略进入输入/,
  );
  safe.window.close();
  assert.equal(errors.length, 0, errors.join("\n"));
  const result = {
    status: "PASSED",
    scope: "DOM-only; not a browser layout/visual acceptance",
    run_options: 4,
    checks: [
      "tabs",
      "run selector",
      "paired actual costs",
      "trial status",
      "candidate counts",
      "feedback export without save",
      "true-vs-unknown state",
      "script escaping",
    ],
    exports: downloads.length,
    network_requests: 0,
  };
  if (process.argv[4])
    fs.writeFileSync(process.argv[4], JSON.stringify(result, null, 2) + "\n");
  process.stdout.write(JSON.stringify(result) + "\n");
})().catch((error) => {
  process.stderr.write(error.stack + "\n");
  process.exitCode = 1;
});
