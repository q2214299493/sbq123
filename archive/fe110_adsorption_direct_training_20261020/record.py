"""Record truthful failed first GPU attempt and CPU-only source fix; never reauthorizes compute."""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.adsorption.direct_force_training import verify

from .transport import EVIDENCE, PACKAGE, ROOT


def main():
    direct = PACKAGE / "direct_request.json"
    verify(direct, sha256_file(direct))
    returned = EVIDENCE / "returned"
    terminal = json.loads((returned / "direct_batch_exit_record.json").read_text())
    native = json.loads((returned / "ddp_cpu_regression.json").read_text())
    mapping = json.loads((returned / "ddp_parameter_diagnostic.json").read_text())
    assert terminal["exit_code"] == 1 and terminal["completed_arms"] == []
    assert all(p["name"].startswith("output_heads.energy.") for p in mapping["unused_parameters"])
    assert native["status"] == "PASS_NATIVE_CPU_DDP_TOY_ONLY" and not native["AQCat25_forward_or_training"]
    role = ROOT / "scripts/adsorption/role_force_trainer.py"
    assert sha256_file(role) == native["new_role_source_sha256"]
    collection = json.loads((EVIDENCE / "collection_receipt.json").read_text())
    assert not collection["source_files"]["candidate_exists"] and not collection["source_files"]["treatment_output_exists"]
    suites = ET.parse(EVIDENCE / "scoped_tests_postfix.xml").getroot().findall("testsuite")
    counts = {key: sum(int(s.attrib[key]) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    assert counts == {"tests": 174, "failures": 0, "errors": 0, "skipped": 0}
    files = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "archive/fe110_adsorption_direct_training_20261020").glob("*.py")]
    files += ["scripts/adsorption/direct_force_training.py", "scripts/adsorption/direct_training_arm.py", "scripts/adsorption/role_force_trainer.py"]
    commands = []
    for command in ([sys.executable, "-m", "py_compile", *files], [sys.executable, "-m", "ruff", "check", *files]):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
        commands.append({"command": command, "exit_code": result.returncode, "stdout": result.stdout[:4000], "stderr": result.stderr[:4000]})
    receipt = {"status": "GPU_ATTEMPT_FAILED_SOURCE_FIXED_CPU_ONLY", "direct_request_sha256": sha256_file(direct),
        "GPU_attempts": 1, "automatic_retries": 0, "treatment_started": False, "candidate_exists": False,
        "energy_head_unused_parameters_confirmed": 9, "corrected_role_source_sha256": sha256_file(role),
        "corrected_AQCat25_GPU_training_validated": False, "native_CPU_DDP_toy_regression_passed": True,
        "original_bound_training_artifacts_unchanged": True, "tests": counts, "commands": commands,
        "source_files": [{"path": path, "sha256": sha256_file(ROOT / path)} for path in files]}
    write_json_exclusive(EVIDENCE / "verification_receipt.json", receipt)
    if any(row["exit_code"] for row in commands):
        raise RuntimeError("source validation failed;preserve evidence")
    doc = "docs/reviews/fe110_adsorption_direct_training_20261020.md"
    scope = "archive/fe110_adsorption_direct_training_20261020/scope.md"
    paths = [doc, scope, direct.relative_to(ROOT).as_posix(),
             (EVIDENCE / "portable_preflight/preflight_adjustment.json").relative_to(ROOT).as_posix()]
    paths += [(EVIDENCE / name).relative_to(ROOT).as_posix() for name in
              ("verification_receipt.json", "collection_receipt.json", "scoped_tests_postfix.xml")]
    paths += [(returned / name).relative_to(ROOT).as_posix() for name in
              ("direct_batch_exit_record.json", "ddp_parameter_diagnostic.json", "ddp_cpu_regression.json")]
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-direct-training-ddp-failed-20261020"
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "Authorized direct control enteredGPU1 but failed on9unusedDDP energy-head tensors;no treatment/candidate.Source zero-energy graph fix passes nativeCPU toyDDP,not re-run on GPU.",
        "evidence": [{"locator": path, "sha256": sha256_file(ROOT / path), "authority": "user_authorization" if path == scope
                      else "repository_document", "observed_at": now} for path in paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-training-live-precheck-blocked-20261019"],
        "payload": {"objective": "Complete the adsorption training comparison after fresh corrected-runtime binding and renewed GPU authority;do not infer success from CPU tests.",
            "phase": "blocked", "current_evidence": [
                "User“跑” authorized GPU1 direct mode with unchanged2epoch/496step/30min-per-arm,total60min,no-retry scope.Backend policy adds only this exception.Direct request b0cc4cf03ee9e2fd52fa0c7deb86f204e771b15263be8001af703f29af7d6203 preserves all original bound arm artifacts.",
                "Both on-disk/nativeCPU preflights pass with supplementary hash-bound coordinate-decoding allowance1e-12A;observed cross-platform difference1.776e-15A.All cell/PBC/rawforces and source hashes remain exact.No geometry optimization or data change.",
                "Actual direct controllerPID2888886/controlPID2888895 ran2026-10-20 00:22:34–00:22:52CST;actual model parameters CUDAcuda:0 on physicalGPU1 UUID450609b3.Producers exited1 before a completed epoch;no candidate,treatment or automatic retry.",
                "Native error lists9unused tensors374–382;CPU mapping confirms all are output_heads.energy.*.New force-only role loss omitted their graph dependency;native one-rank DDP rejects the next forward.This is adapter integration failure,not evidence of model accuracy.",
                "Source fix adds exactly-zero energy-output graph dependency without energy fitting.NativeCPU toyDDP reproduces old failure after1step and passes2fixed steps with identical force loss/gradients;corrected roleSHAaf3019d8755bb3a91bf2c97dae5c491f60dc8d90bb4792773cb1fb6cb2e4a90e.Not deployed/retried for AQCat25GPU.",
                "174scoped regressions plus compilation/Ruff pass;11original producer/diagnostic/log files returned byte-exact with remote SHA verification.Source/failed runtime and logs preserved.No model promotion,heldout model evaluation,newVASP or speedup claim."],
            "one_executable_step": "Bind the corrected role runtime into fresh reviewed arm/direct requests and obtain renewed GPU execution authority;then verify consecutive native forward/backward steps within the same bounded training process.No old-package hot patch or automatic retry.",
            "submission_boundary": "DIRECT_V1_AUTHORITY_CONSUMED_BY_FAILED_FIRST_ATTEMPT:correctedGPU relaunch,newVASP,model promotion,extra budget and automatic retries are not authorized.",
            "done_when": ["Fresh corrected-runtime/source and data bindings pass actual native preflight and explicit authority checks.",
                "Both bounded arms complete actualCUDA forward/backward training and return producer/checkpoint evidence without heldout epoch selection.",
                "Grouped development review truthfully distinguishes candidate quality from independent validation and measured VASP acceleration."],
            "constraints": ["Preserve all old frozen packages,source data and failure evidence;do not overwrite or reuse old launch markers.",
                "Keep46newheldout and16observedheldout out of gradients/epoch selection;no independent validation claimed for training failure structures.",
                "The zero energy graph dependency is a DDP execution fix,not an energy-loss/DFT/geometry/weighting change.",
                "CPU toyDDP success does not establish corrected full-model GPU/AMP behavior or scientific acceleration.",
                "No automatic retry;new corrected compute requires fresh request hash authorization."],
            "authoritative_references": ["configs/execution_backends.yaml", doc, scope, "scripts/adsorption/role_force_trainer.py",
                "scripts/adsorption/direct_force_training.py", (EVIDENCE / "verification_receipt.json").relative_to(ROOT).as_posix()]}}
    path = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(path, event)
    print(json.dumps({"event": path.relative_to(ROOT).as_posix(), "status": receipt["status"], "tests": counts}))


if __name__ == "__main__":
    main()
