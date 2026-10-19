"""Record verified live execution blockers; do not grant alternative compute authority."""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts.artifact_io import sha256_file, write_json_exclusive

from .execute import ARMS, EVIDENCE, EXPECTED, checked_request
from .prepare import OUTPUT, ROOT


def main():
    checked_request()
    data = json.loads((EVIDENCE / "live_preflight.json").read_text(encoding="utf-8"))
    assert not data["scheduler_available"] and not data["frozen_helper_boundary_compatible"]
    assert data["checkpoint_sha256"] == "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"
    assert not data["target_package_exists"] and not data["remote_files_written"] and not data["training_or_inference_run"]
    tests = ET.parse(EVIDENCE / "scoped_tests.xml").getroot().findall("testsuite")
    counts = {key: sum(int(s.attrib[key]) for s in tests) for key in ("tests", "failures", "errors", "skipped")}
    assert counts == {"tests": 143, "failures": 0, "errors": 0, "skipped": 0}
    files = ["archive/fe110_adsorption_training_comparison_20261019/" + name for name in
             ("execute.py", "test_execute.py", "record_precheck.py")]
    commands = []
    for command in ([sys.executable, "-m", "py_compile", *files], [sys.executable, "-m", "ruff", "check", *files]):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
        commands.append({"command": command, "exit_code": result.returncode, "stdout": result.stdout[:4000], "stderr": result.stderr[:4000]})
    verification = {"status": "BLOCKED_PRECHECK_NO_SUBMISSION", "comparison_request_sha256": EXPECTED,
        "arm_request_sha256": ARMS, "frozen_artifacts_hash_verified": True, "tests": counts, "commands": commands,
        "scheduler_available": False, "frozen_directory_helper_compatible": False,
        "GPU_submission_attempted": False, "remote_files_written": False, "model_run": False,
        "evidence": [{"path": (EVIDENCE / name).relative_to(ROOT).as_posix(), "sha256": sha256_file(EVIDENCE / name)} for name in
                     ("comparison_authorization.json", "control_authorization.json", "treatment_authorization.json", "live_preflight.json", "live_preflight_receipt.json", "scoped_tests.xml")]}
    write_json_exclusive(EVIDENCE / "verification_receipt.json", verification)
    if any(row["exit_code"] for row in commands):
        raise RuntimeError("code validation failed;preserve evidence")
    now = datetime.now(timezone.utc).isoformat()
    doc = "docs/reviews/fe110_adsorption_training_execution_precheck_20261019.md"
    scope = "archive/fe110_adsorption_training_comparison_20261019/authorization_run_20261019.md"
    paths = [doc, scope] + [(EVIDENCE / name).relative_to(ROOT).as_posix() for name in
                           ("comparison_authorization.json", "live_preflight.json", "live_preflight_receipt.json", "verification_receipt.json", "scoped_tests.xml")]
    event_id = "task-fe110-adsorption-training-live-precheck-blocked-20261019"
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "User authorized reviewed two-arm training,but liveMZ73 precheck found unavailableSlurm and incompatible frozen directory guard.No upload/submission/model run.",
        "evidence": [{"locator": path, "sha256": sha256_file(ROOT / path), "authority": "user_authorization" if path == scope
                      else "repository_document", "observed_at": now} for path in paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-training-comparison-prepared-20261019"],
        "payload": {"objective": "Execute the authorized bounded adsorption training comparison after resolving verified runtime blockers within explicit authority.",
            "phase": "blocked", "current_evidence": [
                "User“运行” authorized comparison f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987 and both exact arm requests.Separate immutable authorization files created;frozen package/artifacts unchanged.",
                "MZ73 live2026-10-19T14:32:29Z:slurmctld/slurmd failed;sinfo exit1 controller unreachable;squeue12second timeout.Scheduler state unavailable,not proof of an empty queue.",
                "GPU1 RTX4090 has24066MiB free,0percent utilization at the snapshot;not reserved.Baseline checkpoint hash matches e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50.",
                "Declared /home/sbq/sbq resolves to /home/ubuntu/hdd/sbq/sbq;frozen helper requires the alias resolve to itself and rejects it.Target package absent.No upload,sbatch attempt,remote file write,training or inference.",
                "143scoped tests pass plus compilation/Ruff.Explicit UTF8 fixed a local authorization-read failure before SSH;authorization was not recreated and no compute retry occurred."],
            "one_executable_step": "Obtain explicit scope for a new bounded GPU1 direct-execution package with reviewed canonical-directory handling,or administrator-restoredSlurm plus corrected-wrapper review;do not submit unchanged or reuse old direct exceptions.",
            "submission_boundary": "EXACT_ORIGINAL_SLURM_PACKAGE_AUTHORIZED_BUT_PRECHECK_BLOCKED:alternative direct execution,service restart,other users'GPU/process changes,newVASP,extra budget,retries and model promotion are not authorized.",
            "done_when": ["Authorized deployment/runtime and realGPU preflight pass with fresh exact hashes and correct boundary checks.",
                "Both arms execute sequentially within2epochs/496steps/30min each,total60GPUminutes,and return truthful producer/scheduler evidence.",
                "Grouped development results and frozen candidate artifacts return to work without heldout-driven epoch selection or automatic promotion."],
            "constraints": ["Preserve original pool,model/data/splits and all failed/partial evidence.No automatic resubmission or budget expansion.",
                "Keep46newheldout and16observedheldout outside training/epoch selection.NoVASP or model promotion authority.",
                "Do not emulate SLURM_JOB_ID or treat previous direct-GPU exceptions as authority for this comparison.",
                "Canonical path alias handling must be reviewed in a fresh runtime binding,not patched into the immutable original package.",
                "Code tests/free GPU memory do not establish full-model CUDA/AMP safety,scientific accuracy or actual acceleration."],
            "authoritative_references": ["configs/execution_backends.yaml", doc, scope,
                (OUTPUT / "comparison_request.json").relative_to(ROOT).as_posix(), (EVIDENCE / "verification_receipt.json").relative_to(ROOT).as_posix()]}}
    path = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(path, event)
    print(json.dumps({"event": path.relative_to(ROOT).as_posix(), "status": verification["status"], "tests": counts}))


if __name__ == "__main__":
    main()
