"""Validate returned execution evidence and publish a truthful training-only task state."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts.adsorption.direct_force_training import verify
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

from .transport import EVIDENCE, PACKAGE, ROOT, RUN_ID


def main():
    sha = sha256_file(PACKAGE / "direct_request.json")
    request, _, _ = verify(PACKAGE / "direct_request.json", sha)
    returned = EVIDENCE / "returned"
    terminal = load_json_object(returned / "direct_batch_exit_record.json")
    if terminal["exit_code"] != 0 or terminal["completed_arms"] != ["control", "treatment"]:
        raise ValueError("both corrected producers must finish successfully")
    collection = load_json_object(EVIDENCE / "collection_receipt.json")
    if set(collection["candidates"]) != {"control", "treatment"}:
        raise ValueError("both development-selected checkpoint hashes required")
    arms = {}
    for arm in request["arms"]:
        folder = returned / arm / "output" / RUN_ID
        device = load_json_object(folder / "execution_device.json")
        startup = load_json_object(folder / "native_two_backward_check.json")
        finished = load_json_object(folder / "training_completed.json")
        exit_record = load_json_object(folder / "producer_exit_record.json")
        if (device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != request["gpu_uuid"]
                or startup["request_sha256"] != sha or startup["pid"] != device["pid"]
                or startup["status"] != "PASS_NATIVE_CUDA_TWO_BACKWARDS"
                or [r["native_step"] for r in startup["records"]] != [1, 2]
                or startup["actual_optimizer_updates"] != 2
                or exit_record["exit_code"] != 0 or finished["optimizer_steps"] != 496
                or finished["max_epochs"] != 2 or finished["heldout_used"]):
            raise ValueError("producer CUDA/budget/consecutive-backward evidence mismatch")
        lines = (folder / "training.log").read_text(encoding="utf-8", errors="replace").splitlines()
        development = []
        for line in lines:
            if "base_trainer.py:" in line and "forces_role_vector_mae:" in line and "epoch:" in line:
                development.append({key: float(value) for key, value in re.findall(r"\b(forces_[a-zA-Z_]+|epoch):\s*([-+0-9.eE]+)", line)})
        if len(development) != 2:
            raise ValueError("expected exactly two native development evaluations")
        arms[arm] = {"native_iterations": 496, "epochs": 2, "exit_code": 0,
            "startup_actual_optimizer_updates": 2, "development_rounded_native_log": development,
            "best_development_role_vector_mae_eV_per_A": min(row["forces_role_vector_mae"] for row in development),
            "started_at": exit_record["started_at"], "finished_at": exit_record["finished_at"]}
    suites = ET.parse(EVIDENCE / "scoped_tests.xml").getroot().findall("testsuite")
    counts = {key: sum(int(s.attrib[key]) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 180, "failures": 0, "errors": 0, "skipped": 0}:
        raise ValueError("scoped software validation incomplete")
    receipt = {"status": "BOTH_CORRECTED_CUDA_TRAINING_ARMS_COMPLETED", "request_sha256": sha,
        "arms": arms, "candidates": collection["candidates"], "tests": counts, "automatic_retries": 0, "heldout_model_evaluations": 0,
        "model_promoted": False, "VASP_jobs": 0, "measured_VASP_speedup": "not established",
        "development_is_not_independent_validation": True, "source_files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in
            [ROOT / "scripts/adsorption/role_force_trainer.py", ROOT / "scripts/adsorption/direct_training_arm.py",
             ROOT / "scripts/adsorption/direct_force_training.py", ROOT / "scripts/adsorption/force_training_preflight.py"]]}
    write_json_exclusive(EVIDENCE / "verification_receipt.json", receipt)
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-corrected-training-completed-20261020"
    paths = ["docs/reviews/fe110_adsorption_training_retry_20261020.md",
             "archive/fe110_adsorption_training_retry_20261020/scope.md"]
    paths += [p.relative_to(ROOT).as_posix() for p in (PACKAGE / "direct_request.json", EVIDENCE / "verification_receipt.json",
              EVIDENCE / "collection_receipt.json", EVIDENCE / "scoped_tests.xml", returned / "direct_batch_exit_record.json")]
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "One explicitly authorized corrected GPU1 retry completed both248train/60development arms,2epochs/496iterations each;native two-backward/zero-energy-gradient checks pass.No heldout/promotion/speedup claim.",
        "evidence": [{"locator": path, "sha256": sha256_file(ROOT / path), "authority": "user_authorization" if path.endswith("scope.md") else "repository_document", "observed_at": now} for path in paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-direct-training-ddp-failed-20261020"],
        "payload": {"objective": "Review the completed corrected adsorption training comparison;retain development versus heldout and measured-acceleration boundaries.",
            "phase": "verification", "current_evidence": [
                "User“修复好再跑一次” explicitly authorized one new corrected attempt.New v2 hashes preserve original physical labels,splits,recipes and base checkpoint;v1 failure untouched.",
                "Both actual MZ73 CPU/native CLI/checkpoint preflights and180scoped regressions pass.Only coordinate decoding uses1e-12A tolerance;raw forces/cell/PBC/roles and source hashes exact.",
                "Both control and treatment ran on physicalGPU1 UUID450609b3;each completed2epochs/496native iterations and exited0.Each same-process startup receipt proves two real optimizer updates and exact-zero energy-head gradients.",
                "The DDP integration failure is repaired in actual full-model GPU training.Not evidence of model transferability or actual VASP speedup.",
                "Native development metrics are available in verification_receipt.json;they are rounded training-selection metrics,not independent heldout results.46newheldout and16observedheldout remain excluded.",
                "Both candidate checkpoints remain unpromoted;no newVASP,extra GPU inference,automatic retry or production replacement authorized."],
            "one_executable_step": "Review grouped development/retention results,then prepare an exact-hash independent validation proposal for the chosen frozen candidate without running it yet.",
            "submission_boundary": "ONE_CORRECTED_RETRY_COMPLETED:compute authority consumed.No further training,heldout GPU evaluation,promotion or VASP without its own scope and authorization.",
            "done_when": ["Returned producer evidence and same-process native CUDA checks establish both bounded training runs completed.",
                "Grouped development comparison distinguishes combined recipe effects from independent validation.",
                "A chosen frozen candidate has a reviewable independent-validation proposal;no acceleration claim without a matched VASP benchmark."],
            "constraints": ["Preserve v1 failures and v2 immutable package/checkpoints;no old-package hot patch.",
                "46newheldout and16observedheldout are excluded from training and epoch selection;no unseen-domain or C2H3 training claim.",
                "Energy output is untrained;force-only candidate energies cannot enter scientific tables.",
                "No automatic retry,production promotion or measured VASP acceleration claim."],
            "authoritative_references": ["configs/execution_backends.yaml", paths[0], paths[1],
                "scripts/adsorption/direct_training_arm.py", (EVIDENCE / "verification_receipt.json").relative_to(ROOT).as_posix()]}}
    event_path = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(event_path, event)
    print(json.dumps({"event": event_path.relative_to(ROOT).as_posix(), "status": receipt["status"], "arms": arms}))


if __name__ == "__main__":
    main()
