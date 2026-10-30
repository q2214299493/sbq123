"""Execute exactly the predeclared local model trials; no science jobs or retries."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive  # noqa: E402 - standalone task bootstrap
from scripts.research_assistant.policies import utc_now  # noqa: E402

ROOT = Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_runtime_policy_20261030")


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def main():
    plan = load_json_object(ROOT / "planned_runs.json")
    source_hashes = {p.name: sha256_file(p) for p in (REPO / "scripts/research_assistant").glob("*.py")}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    write_json_exclusive(ROOT / "execution_reservation.json", {"created_at": utc_now(), "plan": ref(ROOT / "planned_runs.json"),
        "source_hashes": source_hashes, "source_head": head, "retries": 0, "task_runs_planned": 4})
    shutil.copyfile(__file__, ROOT / "run_acceptance.py")
    results = []
    for item in plan["runs"]:
        current = {p.name: sha256_file(p) for p in (REPO / "scripts/research_assistant").glob("*.py")}
        if current != source_hashes:
            raise ValueError("source changed during paired experiment; no mixed-code comparison")
        with (ROOT / (item["name"] + ".stdout.txt")).open("xb") as out, (ROOT / (item["name"] + ".stderr.txt")).open("xb") as err:
            process = subprocess.run(item["command"], cwd=REPO, stdout=out, stderr=err, timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        run = ROOT / "runs" / item["name"]
        receipt_path = run / "run_receipt.json"
        receipt = load_json_object(receipt_path) if receipt_path.exists() else {}
        app = load_json_object(run / "rsi_application.json") if (run / "rsi_application.json").exists() else {}
        result = {"name": item["name"], "task": item["task"], "arm": item["arm"], "process_exit_code": process.returncode,
            "status": receipt.get("status", "NO_RECEIPT"), "run_receipt": ref(receipt_path) if receipt_path.exists() else None,
            "model_turns": receipt.get("model_turns_started"), "host_requests": receipt.get("host_tool_requests"),
            "policy_provided": any(p["provided"] for p in app.get("selected_policies", [])),
            "application_statuses": [a["host_status"] for a in app.get("applications", [])],
            "failure_stage": receipt.get("first_failure_stage"), "problem": receipt.get("problem")}
        results.append(result)
        write_json_exclusive(ROOT / (item["name"] + ".execution.json"), result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result["status"] != "GENERATED" and receipt.get("model_turns_started", 0) == 0:
            break  # shared environment/admission failure: preserve it, do not retry unchanged calls
    summary = {"schema_version": 1, "recorded_at": utc_now(), "source_head": head, "source_hashes": source_hashes,
        "planned_task_runs": 4, "actual_task_runs": len(results), "results": results,
        "complete_pairs": {task: len([r for r in results if r["task"] == task and r["status"] == "GENERATED"]) == 2 for task in ("relevant", "nontrigger")},
        "retries": 0, "user_confirmed_help": None, "controlled_benefit": None,
        "review_status": "PENDING_CONTENT_AND_CONDITION_REVIEW; completion/cost alone does not establish benefit"}
    path = ROOT / "paired_runs.json"
    write_json_exclusive(path, summary)
    for row in results:
        if row["run_receipt"]:
            folder = Path(row["run_receipt"]["path"]).parent / "comparisons"
            folder.mkdir()
            write_json_exclusive(folder / "paired_runs.json", {"run_receipt_sha256": row["run_receipt"]["sha256"], "comparison_reference": ref(path)})
    print(json.dumps({"actual_task_runs": len(results), "complete_pairs": summary["complete_pairs"], "retries": 0}), flush=True)


if __name__ == "__main__":
    main()
