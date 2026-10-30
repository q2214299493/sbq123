"""One-off condition audit and additive review of the four predeclared runs."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa: E402
from scripts.research_assistant.policies import utc_now  # noqa: E402

ROOT = Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_runtime_policy_20261030")


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def identity(receipt):
    return {key: receipt[key] for key in ("model", "effort", "mode", "credential_store", "evidence_access",
            "source_versions", "producer", "host_tool_implementation")} | {
            "binary_sha256": receipt["permission_evidence"]["executable_sha256"]}


def inspect_run(item):
    root = ROOT / "runs" / item["name"]
    receipt = load_json_object(root / "run_receipt.json")
    initial = load_json_object(root / "turn-001/model_input.json")
    app = load_json_object(root / "rsi_application.json")
    result = load_json_object(root / "research_result.json")
    errors = [{"evidence_id": a["evidence_id"], "tool": a["request"]["tool"],
               "error": load_json_object(Path(a["result_path"]))["result"].get("error")} for a in result["evidence_actions"] if a["status"] == "ERROR"]
    observed = any(a["host_status"] == "observed_correspondence_needs_content_review" for a in app["applications"])
    return {"name": item["name"], "receipt_ref": ref(root / "run_receipt.json"), "result_ref": ref(root / "research_result.json"),
        "application_ref": ref(root / "rsi_application.json"), "initial_input_ref": ref(root / "turn-001/model_input.json"),
        "status": receipt["status"], "model_turns": receipt["model_turns_started"], "host_requests": receipt["host_tool_requests"],
        "host_errors": errors, "elapsed_seconds": receipt["elapsed_seconds"], "tokens": receipt["tokens"],
        "native_attempts": receipt["native_tool_attempts"], "policy_provided": any(r["provided"] for r in app["selected_policies"]),
        "observed_correspondence": observed, "recommended_next": result["answer"]["recommended_next"],
        "candidate_statuses": [r["status"] for r in app["candidate_records"]]}, receipt, initial


def main():
    summary = load_json_object(ROOT / "paired_runs.json")
    if summary["actual_task_runs"] != 4 or not all(summary["complete_pairs"].values()):
        raise ValueError("four successful task-level runs required; never fill a failed/missing arm")
    plan = load_json_object(ROOT / "planned_runs.json")
    reservation = load_json_object(ROOT / "execution_reservation.json")
    write_json_exclusive(ROOT / "review_reservation.json", {"created_at": utc_now(), "paired_summary": ref(ROOT / "paired_runs.json")})
    records, receipts, inputs = {}, {}, {}
    for item in plan["runs"]:
        record, receipt, initial = inspect_run(item)
        if record["status"] != "GENERATED" or record["native_attempts"] != 0 or record["policy_provided"] != item["expected_policy_provided"]:
            raise ValueError("task result differs from the predeclared conditions")
        if receipt["source_versions"] != reservation["source_hashes"] or receipt["producer"]["head"] != reservation["source_head"]:
            raise ValueError("producer/source changed during paired runs")
        records[item["name"]], receipts[item["name"]], inputs[item["name"]] = record, receipt, initial
    checks = []
    for task in ("relevant", "nontrigger"):
        candidate, baseline = task + "_candidate", task + "_baseline"
        left, right = deepcopy(inputs[candidate]), deepcopy(inputs[baseline])
        left["rsi_context"].pop("selected_policies")
        right["rsi_context"].pop("selected_policies")
        equal = left == right and identity(receipts[candidate]) == identity(receipts[baseline])
        if not equal:
            raise ValueError("paired inputs differ beyond selected policy content")
        checks.append({"task": task, "same_input_except_selected_policy": True, "same_model_code_binary_tools_budgets": True,
                       "base_input_excludes_unselected_policy_ids_feedback_and_other_arm_answers": True,
                       "both_complete": True, "benefit": None})
    review = {"schema_version": 1, "reviewed_at": utc_now(), "reviewer": "Codex host/content inspection; not user-reported help or scientific owner acceptance",
        "paired_summary_ref": ref(ROOT / "paired_runs.json"), "condition_checks": checks, "runs": list(records.values()),
        "input_provided": True, "behavior_observed": True, "user_confirmed_help": None, "controlled_benefit": None,
        "content_review": {
            "scientific_scope": "Only source notes and geometry/composition observations were checked; no convergence, endpoint, result or scientific acceptance.",
            "decision_or_product": "Relevant policy arm proposes an existing-source handoff package; baseline proposes conditional B-prime preparation after owner review. Neither product was generated or adopted.",
            "human_correction_and_time": "No actual researcher feedback or measured preparation/review/correction time for these trials.",
            "benefit": "Not established. A different recommendation and a matching action trace do not establish avoided work or a better research outcome.",
            "limits": "One stochastic pair per task in a restricted frozen evidence scope; host errors and all costs remain included. No general or long-term superiority claim."},
        "initial_policy_status": "trial; externally proposed; not autonomously discovered or permanently accepted",
        "retries": 0}
    output = ROOT / "paired_review.json"
    write_json_exclusive(output, review)
    for record in records.values():
        run = Path(record["receipt_ref"]["path"]).parent
        write_json_exclusive(run / "comparisons" / "paired_review.json", {"run_receipt_sha256": record["receipt_ref"]["sha256"], "comparison_reference": ref(output)})
    shutil.copyfile(__file__, ROOT / "review_acceptance.py")
    print(json.dumps({"condition_checks": checks, "metrics": [{k: row[k] for k in ("name", "model_turns", "host_requests", "elapsed_seconds", "policy_provided", "observed_correspondence")} for row in records.values()],
                      "user_confirmed_help": None, "controlled_benefit": None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
