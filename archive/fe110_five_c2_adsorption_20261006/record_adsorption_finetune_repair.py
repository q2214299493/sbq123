"""Record bounded engineering validation and submitted v6 state; never submits."""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = Path("calculations/fe110_five_c2_adsorption_20261006")
EVIDENCE = BASE / "adsorption_finetune_submission_v6"
FILES = ["scripts/adsorption/force_finetune.py"] + [
    "archive/fe110_five_c2_adsorption_20261006/" + name for name in (
        "preflight_adsorption_finetune.py", "prepare_adsorption_finetune_retry.py",
        "launch_adsorption_finetune.py", "test_adsorption_finetune.py", "test_launch_adsorption_finetune.py")]


def main():
    checks = []
    for name, args in (("compile", ["-m", "py_compile", *FILES]),
                       ("ruff", ["-m", "ruff", "check", *FILES]),
                       ("tests", ["-m", "pytest", "-q", *FILES[-2:]])):
        target = ROOT / EVIDENCE / f"validation_{name}.txt"
        if target.exists():
            raise FileExistsError(target)
        result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True)
        target.write_bytes(result.stdout + result.stderr)
        checks.append({"command": [sys.executable, *args], "exit_code": result.returncode,
                       "evidence_path": str(target.relative_to(ROOT)).replace("\\", "/"),
                       "sha256": sha256_file(target)})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect {target}")
    write_json(ROOT / EVIDENCE / "engineering_validation.json", {"checks": checks, "scientific_acceptance": False})
    progress = (ROOT / EVIDENCE / "training_progress_2185.txt").read_text(encoding="utf-8")
    state = re.search(r"JobState=(\S+)", progress).group(1)
    assert state == "RUNNING" and "epoch: 0.2059" in progress and "seed: 42" in progress
    previous = json.loads((ROOT / "modules/state_handoff/events/task-fe110-c2-adsorption-finetune2184-sampler-failed-20261010.json").read_text())
    payload = previous["payload"]
    payload["current_evidence"] = [
        "User 补齐 then 把所有问题理清楚再提交 conditionally authorized one unchanged-budget repair retry after real runtime preflight, not automatic retries or promotion.",
        "Per-split integer natoms/row_ids metadata from original ASE DBs and explicit metadata_path repaired sampler; --seed42 repaired CLI override. Labels/DB bytes/splits34/12/16/baseline/force-only objective/budget unchanged.",
        "v5 CPU preflight failed because new preflight incorrectly compared shuffled Fairchem Subset against sequential raw rows. No GPU submitted; v6 resolves actual indices/row_ids; metadata unchanged.",
        "v6 hash5e04e87a2a04f3937734f2592c2f442172d24cfb189a14d66554b854c50cb311 binds83artifacts. Localcompile/Ruff/33tests and MZ73bash-n/actualtrainer datasets,samplers,DataLoader fulltrain34/development12 traversal and finalCLIconfig PASS_NO_MODEL_RUN. Heldout not predicted/selected.",
        "One MZ73job2185 submitted1GPU/4CPU/32GB/30min/4epochs/lr1e-5/batch1/seed42/requeue0. Latest snapshotRUNNING at1min26sec; actualseed42 and trainingepoch0.0294to0.2059/loss0.0236to0.0229 demonstrate real training iterations, not completion or independent performance.",
        "No baseline replacement, heldout model selection, VASP submission, scientific acceptance, acceleration proof or automatic retry. Complete GPU training/development evaluation chain remains unverified."
    ]
    payload["one_executable_step"] = "Check job2185 terminal scheduler/process evidence and grouped development baseline/candidate force comparison; preserve failure evidence and no automatic retry."
    payload["submission_boundary"] = "Conditional v6 one-run authority consumed by2185; no additional GPU retry, VASP, heldout model selection or checkpoint promotion authorized."
    payload["authoritative_references"] = previous["payload"]["authoritative_references"][:2] + [
        str(BASE / "adsorption_finetune_review_v6/training_request.json").replace("\\", "/"),
        str(EVIDENCE / "submission_summary.json").replace("\\", "/"),
        str(EVIDENCE / "training_progress_2185.txt").replace("\\", "/"),
        "docs/reviews/fe110_adsorption_finetune_package_20261010.md", "scripts/adsorption/adsorption_finetune_job.sh"]
    now = datetime.now(timezone.utc).isoformat()
    sources = [(EVIDENCE / "submission_authorization.json", "user_authorization"),
               (EVIDENCE / "preflight_binding.json", "module_validation"),
               (EVIDENCE / "submission_summary.json", "module_validation"),
               (EVIDENCE / "training_progress_2185.txt", "calculation_file"),
               (EVIDENCE / "engineering_validation.json", "module_validation"),
               (Path("docs/reviews/fe110_adsorption_finetune_package_20261010.md"), "repository_document")]
    event = {"schema_version": 1, "event_id": "task-fe110-c2-adsorption-finetune2185-running-20261010",
             "occurred_at": now, "recorded_at": now, "event_type": "task_updated", "entity": previous["entity"],
             "summary": "Sampler/CLI engineering repair validated; conditional one-run v6 job2185 now performs real training, not yet completed or promoted.",
             "evidence": [{"locator": str(path).replace("\\", "/"), "sha256": sha256_file(ROOT / path),
                           "authority": authority, "observed_at": now} for path, authority in sources],
             "review": {"required": False, "reason_codes": [], "status": "not_required"},
             "supersedes": [previous["event_id"]], "payload": payload}
    target = ROOT / "modules/state_handoff/events" / (event["event_id"] + ".json")
    if target.exists():
        raise FileExistsError(target)
    write_json(target, event)
    print(json.dumps({"tests": "33 passed", "status": state, "event": str(target), "submitted_again": False}))


if __name__ == "__main__":
    main()
