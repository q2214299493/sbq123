"""Record the single repaired-seed GPU submission, not a scientific result."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json
from scripts.state_manager.models import validate_event

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
OLD_ID = "task-fe110-five-c2-adsorption-gpu2142-reviewed-repair-20261007"
NEW_ID = "task-fe110-five-c2-adsorption-repair-gpu2176-submitted-20261008"


def main():
    target = ROOT / f"modules/state_handoff/events/{NEW_ID}.json"
    if target.exists():
        raise FileExistsError("Immutable event already exists")
    now = datetime.now(timezone.utc).isoformat()
    package = BASE / "gpu_repair_v1"
    evidence = BASE / "gpu_repair_submission_v1"
    submission = json.loads((evidence / "submission_summary.json").read_text())
    assert submission["job_id"] == "2176" and submission["candidate_count"] == 1
    assert submission["names"] == ["03_extra2_repair_v1"]
    assert submission["batch_manifest_sha256"] == sha256_file(package / "batch_manifest.json")
    assert submission["scheduler_evidence_sha256"] == sha256_file(evidence / "scheduler_2176.txt")
    old = json.loads((ROOT / f"modules/state_handoff/events/{OLD_ID}.json").read_text(encoding="utf-8"))
    paths = [package / "batch_manifest.json", package / "reviewed_plan.json",
             evidence / "preflight_binding.json", evidence / "submission_summary.json",
             evidence / "submit.txt", evidence / "scheduler_2176.txt"]
    event = {
        "schema_version": 1, "event_id": NEW_ID, "occurred_at": submission["observed_at"],
        "recorded_at": now, "event_type": "task_updated", "entity": old["entity"],
        "summary": "One repaired CHCO candidate submitted as bounded AQCat25 GPU job2176; no new VASP or fine-tuning.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                      "authority": "scheduler" if p.name == "scheduler_2176.txt" else "repository_document",
                      "observed_at": submission["observed_at"]} for p in paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "payload": {**old["payload"], "phase": "active",
            "current_evidence": old["payload"]["current_evidence"][:-1] + [
                "Previous repair review remains historical unrelaxed input evidence; original failed seed/results unchanged.",
                "User continuation authorized only03_extra2_repair_v1 bounded GPUpre-relaxation; newmanifestdd7c2522cdda517efbfe4f659ab26d379cbfede99ad646582b2b9bde06b572f7.",
                "Localschema/input/hashchecks,Pythoncompile,Ruff and5focusedtestsPASS; MZ73remote no-modelpreflightPASS; checkpoint unchanged.",
                f"GPUjob2176scheduler{submission['scheduler_state']} at{submission['observed_at']}; oneGPU,4CPU,32GiB,30min,80LBFGSsteps,MLfmax0.10eV/A.",
                "OnlyFe0-17fixed; no internal-bond/site/heightrestraints. Optimizer convergence cannot establish intactCHCO; returnedchemistry/site/duplicate/domainreviewrequired.",
                "Existing10VASPjobs and otherGPU candidates untouched; noVASPsubmission,modeltraining,acceptedenergyregistrationorautomaticresubmission."],
            "one_executable_step": "Check GPU2176 at the next requested checkpoint; on exit collect hash-bound producer/result/structure artifacts and review intact CHCO connectivity, adsorption geometry and duplicates before any VASP handoff.",
            "submission_boundary": "User authorized the single bounded repaired-seed GPUjob2176 only. No further GPU/VASP submission, automatic resubmission, stops or fine-tuning.",
            "authoritative_references": old["payload"]["authoritative_references"] + [p.relative_to(ROOT).as_posix() for p in paths]},
        "supersedes": [OLD_ID],
    }
    validate_event(event)
    write_json(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
