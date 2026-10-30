"""One-off local acceptance setup. No model call, credentials copy or science job."""
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa: E402 - standalone task bootstrap
from scripts.research_assistant.policies import PolicyStore, utc_now  # noqa: E402

ROOT = Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_runtime_policy_20261030")
PROJECT = Path(r"C:\Users\86177\Desktop\work")
POLICY_ID = "check_registered_material"


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def main():
    tests = ROOT / "software_tests_final.xml"
    suite = ET.parse(tests).getroot().find("testsuite")
    if suite is None or suite.attrib["failures"] != "0" or suite.attrib["errors"] != "0":
        raise ValueError("offline integration must pass before a trial")
    request = ROOT / "user_request.txt"
    with request.open("x", encoding="utf-8") as handle:
        handle.write("2026-10-30 用户本轮请求：请按附件实施现有科研助手的跨任务策略加载、改进候选生成与使用贡献展示，先以一条来源明确的策略完成最小集成验收。交付时分别说明：策略是否进入输入、是否观察到对应行为、是否有用户确认的帮助、是否有对照支持的收益。\n")
    inputs = ROOT / "inputs"
    inputs.mkdir()
    original = PROJECT / "calculations/fe110_c2h4o_adsorption_20261029/review_ready"
    sources = []
    for relative in ("structure_review.md", "candidate_review.json", "A/POSCAR", "B/POSCAR", "C/POSCAR"):
        path, target = original / relative, inputs / relative
        before = ref(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if before["sha256"] != sha256_file(target) or before != ref(path):
            raise ValueError("source changed while freezing paired inputs")
        sources.append({"source": before, "snapshot": ref(target)})
    write_json_exclusive(ROOT / "source_manifest.json", {"collected_at": utc_now(), "sources": sources,
        "purpose": "same previously prepared C2H4O inputs for both arms; not new scientific acceptance"})
    write_json_exclusive(ROOT / "evaluation_manifest.json", {"schema_version": 1, "files": [r["snapshot"] for r in sources]})
    definition = {"policy_id": POLICY_ID, "version": 1, "proposed_at": utc_now(), "proposer": "external_proposal",
        "source_refs": [ref(Path(r"D:\RSI_Runtime_Policy_Implementation_20261030.txt")),
            ref(Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\research_c07_review_20261030\post_model_clarifications.json"))],
        "scope": {"project": str(PROJECT), "intents": ["auto", "diagnose", "compare", "plan"],
            "required_tools": ["evidence.list", "evidence.read"],
            "goal_terms_any": ["结构准备", "新建结构", "重算", "起点准备", "prepare structure"], "excluded_goal_terms_any": [],
            "limitations": "字面触发仅供适用性参考；核对范围内来源不证明所有资料已找全，也不证明重算无价值。"},
        "previous_behavior": "检索未命中时可能遗漏已登记的历史构建清单而建议重新准备；附件及后补C来源记录为提出依据。",
        "behavior_change": "建议新建结构或重算前，核对已登记的材料来源和历史构建记录；命中后读取原记录，说明用途、条件、兼容性和仍需核查项。",
        "expected_help": "可能减少重复准备；具体帮助及人工节省未经验证。", "added_burden": "增加一次有限来源定位和定向读取，实际工具/模型成本另记。",
        "validation_task": "未参与制定规则的C2H4O A/B/C准备问题，以及不触发规则的组成/固定原子核对问题。",
        "evaluation": "分别核对输入、动作顺序/来源读取/输出引用，再评阅科学解释、下一步可执行性、用户反馈和完整同条件配对；不从工具数推断价值。",
        "required_checks": ["材料用途与当前目标一致", "方法/晶胞/约束/磁性等兼容性仍由科学所属模块核查", "不把已有起点自动升级为收敛结果或科学接受", "不自动提交、停止、重启或重算"],
        "checks": {"ordered_tool_groups": [["evidence.list", "methods.search", "history.search"], ["evidence.read"]],
                   "read_search_hit": True, "require_output_citation": True},
        "priority": 10, "equivalence_key": "", "conflict_group": "", "supersedes": []}
    write_json_exclusive(ROOT / "seed_definition.json", definition)
    store = PolicyStore(ROOT / "policy_store", PROJECT)
    record = store.propose(definition)
    review = {"policy_id": POLICY_ID, "version": 1, "content_sha256": record["content_sha256"], "status": "trial",
        "reviewer": "Codex operator for the user's explicitly requested minimal integration trial",
        "validation_scope": "Offline software wiring only; bounded initial-policy trial, not permanent adoption or research benefit",
        "validation_refs": [ref(tests), ref(request)],
        "reason": "本轮用户授权以一条来源明确的策略进行最小集成验收；完成离线验证后单独登记试用，不伪造用户已确认帮助或长期采纳。"}
    write_json_exclusive(ROOT / "trial_review_request.json", review)
    store.review(review, ref(ROOT / "trial_review_request.json"))
    profile = load_json_object(Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\research_c07_review_20261030\profile.current-binary.json"))
    previous_binary = profile["codex"]
    profile["codex"] = r"C:\Users\86177\AppData\Local\OpenAI\Codex\bin\22cfb1d302613eae\codex.exe"
    profile["output_root"] = str(ROOT / "runs")
    profile["rsi"] = {"store": str(store.root), "mode": "accepted", "trial_policy_ids": [POLICY_ID], "include_pending_feedback": False}
    write_json_exclusive(ROOT / "experiment_profile.json", profile)
    daily = {**profile, "rsi": {"store": str(store.root), "mode": "accepted"}}
    write_json_exclusive(ROOT / "daily_profile.json", daily)
    write_json_exclusive(ROOT / "binary_update.json", {"previous_binary": previous_binary, "current_binary": ref(Path(profile["codex"])),
        "reason": "previous installed path no longer exists; current running Codex binary selected; original admission and auth remain mandatory"})
    tasks = [("relevant", "plan", "面向Fe(110) C2H4O的A/B/C构型，给出下一阶段结构准备的一项具体产物，以及所需核查和适用条件。只形成建议，不执行科学作业。", True),
             ("nontrigger", "diagnose", "逐项核对A/B/C三份POSCAR的元素组成和固定原子数量，区分文件实测与说明文档声称，并说明这些数字能够支持的判断范围。只完成资料核对。", False)]
    runs = []
    for task, intent, goal, expected in tasks:
        for arm in ("candidate", "baseline"):
            name = task + "_" + arm
            command = [sys.executable, "-m", "scripts.research_assistant.cli", "run", "--goal", goal, "--intent", intent,
                       "--workdir", str(inputs), "--profile", str(ROOT / "experiment_profile.json"),
                       "--mode", "evaluation", "--evaluation-manifest", str(ROOT / "evaluation_manifest.json"),
                       "--output-dir", str(ROOT / "runs" / name), "--max-turns", "4", "--max-actions", "8", "--timeout-seconds", "480"]
            if arm == "baseline":
                command += ["--rsi-exclude-policy", POLICY_ID]
            runs.append({"name": name, "task": task, "arm": arm, "command": command,
                         "expected_policy_provided": expected and arm == "candidate"})
    write_json_exclusive(ROOT / "planned_runs.json", {"schema_version": 1, "created_at": utc_now(), "runs": runs,
        "source_manifest": ref(ROOT / "source_manifest.json"), "profile": ref(ROOT / "experiment_profile.json"),
        "intentional_difference": "target policy excluded only in each baseline; all other settings/scientific facts identical",
        "retries": 0, "human_review_seconds": None})
    shutil.copyfile(__file__, ROOT / "prepare_acceptance.py")
    print("Prepared one externally sourced trial and four fixed task-level runs; no model started.")


if __name__ == "__main__":
    main()
