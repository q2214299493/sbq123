"""Record submission evidence without accepting predicted adsorption results."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json
from scripts.state_manager.models import validate_event

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"


def main():
    evidence = BASE / "gpu_supplement_submission_v1"
    summary = json.loads((evidence / "submission_summary.json").read_text())
    assert summary["job_id"] == "2142"
    assert summary["batch_manifest_sha256"] == sha256_file(BASE / "gpu_supplement_v1/batch_manifest.json")
    assert summary["scheduler_evidence_sha256"] == sha256_file(evidence / "scheduler_2142.txt")
    validation = evidence / "validation_summary.json"
    if validation.exists():
        raise FileExistsError(validation)
    write_json(validation, {
        "executed_commands": [
            {"command": "python -m py_compile archive/fe110_five_c2_adsorption_20261006/prepare_supplement_gpu.py archive/fe110_five_c2_adsorption_20261006/supplement_gpu_remote.py", "exit_code": 0},
            {"command": "python -m ruff check archive/fe110_five_c2_adsorption_20261006/prepare_supplement_gpu.py archive/fe110_five_c2_adsorption_20261006/supplement_gpu_remote.py", "exit_code": 0},
            {"command": "python -m pytest tests/test_fe110_c2_supplement.py -q", "exit_code": 0, "passed": 4},
        ],
        "five_local_handoff_validations": "PASS",
        "remote_preflight": {"status": "PASS_NO_MODEL_RUN", "evidence_sha256": sha256_file(evidence / "preflight.txt")},
        "remote_checks": ["host identity", "frozen package and checkpoint hashes", "five ASE input loads",
                          "atom order and Selective Dynamics", "three shell syntax checks", "no prior output"],
        "scientific_acceptance": False,
    })
    old_id = "task-fe110-five-c2-adsorption-supplement-reviewed-20261006"
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text())
    new_id = "task-fe110-five-c2-adsorption-supplement-gpu2142-submitted-20261006"
    now = datetime.now(timezone.utc).isoformat()
    refs = ["archive/fe110_five_c2_adsorption_20261006/SUPPLEMENT_GPU_SUBMISSION.md",
            "calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_v1/batch_manifest.json",
            "calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_submission_v1/submission_summary.json"]
    event = {
        "schema_version": 1, "occurred_at": now, "recorded_at": now, "event_id": new_id,
        "event_type": "task_updated", "entity": old["entity"],
        "summary": "Explicitly authorized five supplemental adsorption candidates submitted to MZ73 as AQCat25 Slurm2142; existing VASP jobs untouched.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                      "authority": a, "observed_at": summary["observed_at"]} for p, a in (
            (BASE / "gpu_supplement_v1/reviewed_plan.json", "user_authorization"),
            (BASE / "gpu_supplement_v1/batch_manifest.json", "repository_document"),
            (evidence / "submission_summary.json", "module_validation"),
            (evidence / "scheduler_2142.txt", "scheduler"), (validation, "module_validation"))],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "payload": {**old["payload"], "phase": "active",
            "current_evidence": [
                "Existing10VASP adsorption jobs9839748-9839757 unchanged; last saved snapshotPEND, not re-queried in this GPU submission step.",
                "User explicitly authorized five supplemental structures01_extra1,02_extra1/2,03_extra1/2 for bounded AQCat25 pre-relaxation.",
                "Five initial structures pass canonical geometry/connectivity/symmetry-duplicate review; nominal input counts3/3/3/3/3 do not establish distinct stable final minima.",
                "Frozen package SHA256eba3524bc6a64800dd93a849824ea40adeb1fa887a37eda059fe64ccb47beda6; verified prior task-local runtime reused, no global method changes.",
                f"MZ73 Slurm2142 scheduler={summary['scheduler_state']} observed{summary['observed_at']}; oneGPU,4CPU,32GiB,120minutes,5sequential candidates,80steps each,fmax0.10eV/A.",
                "Only bottom18Fe fixed; no artificial bond/height/site forces. All adsorbate pairs monitored; final exact chemistry still requires canonical review in work.",
                "Python syntax,Ruff,4bounded tests,5handoff validations and remote no-model hash/ASE/shell preflight pass. No new VASP, fine-tuning or accepted-energy registration."],
            "one_executable_step": "After2142 finishes, collect producer receipts, result manifests and predicted structures; validate return hashes and review exact chemistry, sites, convergence and duplicates in work before requesting VASP.",
            "submission_boundary": "Five-candidate GPU batch2142 explicitly authorized and submitted. Existing10VASP jobs untouched. No automatic resubmission, fine-tuning or new VASP execution authorized.",
            "authoritative_references": old["payload"]["authoritative_references"] + refs},
        "supersedes": [old_id],
    }
    validate_event(event)
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    if target.exists():
        raise FileExistsError(target)
    write_json(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
