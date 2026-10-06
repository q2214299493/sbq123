"""Apply the inspected submission-only registry plan and record factual task state."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json
from scripts.registry_mutations import apply_registry_batch
from scripts.registry_transactions import approve_plan
from scripts.state_manager.models import validate_event

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "vasp_batch_v1"


def main():
    batch = json.loads((DEST / "registry_batch.json").read_text())
    plan = json.loads((DEST / "registry_plan.json").read_text())
    # Reviewed scope: ten calculations, ten jobs, ten status observations, seventy input file records.
    assert plan["scope"] == ["calculations", "files", "job_status_history", "jobs"]
    assert plan["insert_count"] == 100 and plan["update_count"] == 0
    assert all(action["action"] == "insert" for action in plan["actions"])
    assert len(batch["rows"]["calculations"]) == len(batch["rows"]["jobs"]) == 10
    now = datetime.now(timezone.utc).isoformat()
    if (DEST / "registry_receipt.json").exists():
        receipt = json.loads((DEST / "registry_receipt.json").read_text())
        assert receipt["plan_sha256"] == plan["plan_sha256"] and receipt["inserted"] == 100
    else:
        approval = approve_plan(plan, reviewer="Codex", reviewed_at=now)
        write_json(DEST / "registry_approval.json", approval)
        receipt = apply_registry_batch(ROOT / "data/project_registry.sqlite3", batch,
            confirmed_sha256=plan["plan_sha256"], plan=plan, approval=approval)
        write_json(DEST / "registry_receipt.json", receipt)
    write_json(DEST / "validation_summary.json", {
        "python_syntax": "PASS", "ruff_task_helpers_and_preflight": "PASS",
        "pytest_adsorption_preflight_adapter_submission": {"passed": 37},
        "extended_lifecycle_suite": {"failed": 10,
            "blocker": "Existing upload executor uses _run(stdin=...), but existing lifecycle test remote mocks reject stdin; unrelated source changes preserved, not repaired in this task."},
        "actual_inputs": {"geometry_graph_cell_fixed_atoms": "10_PASS", "custodian_no_blockers_or_warnings": "10_PASS",
            "canonical_preflight_execution_authorization": "10_PASS", "remote_input_and_POTCAR_hash_verification": "10_PASS",
            "unique_submission_receipts": "10_SUBMITTED"},
        "unverified": ["electronic convergence", "ionic convergence", "final chemical identity", "reportable adsorption energies"],
    })
    old_id = "task-fe110-five-c2-adsorption-gpu2139-submitted-20261006"
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text())
    new_id = "task-fe110-five-c2-adsorption-vasp-submitted-20261006"
    event = {
        "schema_version": 1, "occurred_at": now, "recorded_at": now,
        "event_id": new_id, "event_type": "task_updated", "entity": old["entity"],
        "summary": "Ten explicitly authorized connectivity-specific Fe110 adsorption relaxations submitted; queue snapshot PEND for9839748-9839757.",
        "evidence": [{"locator": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path), "authority": authority,
                      "observed_at": now} for path, authority in (
            (Path(__file__).with_name("vasp_authorization.md"), "user_authorization"),
            (BASE / "gpu_return_review.json", "module_validation"),
            (DEST / "submission_summary.json", "module_validation"),
            (DEST / "scheduler_snapshot.txt", "scheduler"),
            (DEST / "registry_receipt.json", "calculation_registry"),
        )],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "payload": {**old["payload"], "phase": "active",
            "objective": "Optimize the five exact Fe110 C2 adsorption identities with reviewed GPU candidates and a chemistry-preserving direct-VASP fallback.",
            "current_evidence": [
                "GPU2139 returned12 validated predictions. Chemistry review excluded fragmented02_cfg1 and03_cfg0 output;01_cfg0 duplicates01_cfg2.",
                "Nine intact distinct GPU outputs plus intact pre-GPU03_cfg0 were submitted as10 ordinary adsorption relaxations, species counts2/1/1/3/3.",
                "LSF9839748-9839757 allPEND in the saved snapshot;32MPI ranks each. Electronic/ionic convergence not yet assessed.",
                "Production PBE/PAW-PBE,ENCUT400,Gamma5x5x1,SIGMA0.20,Fe45five-layer,fixedFe0-17 preserved; no artificial bond restraints.",
                "Registry received submission/job/input metadata only, no predicted energy or accepted adsorption result. Prior TS work remains deferred.",
                "37 relevant tests pass;10 extended lifecycle tests have existing stdin mock incompatibility; no unrelated source repair."],
            "one_executable_step": "At the next authorized status check, inspect queue and compact electronic/ionic progress of9839748-9839757; after completion review target connectivity/sites/duplicates before result registration.",
            "submission_boundary": "This10-job adsorption batch explicitly authorized and submitted; no automatic resubmission, TS, frequency or gas-reference submission.",
            "done_when": ["Completed VASP candidates have convergence, exact chemical identity, site and duplicate reviews before accepted result/energy promotion."],
            "authoritative_references": old["payload"]["authoritative_references"] + [
                "calculations/fe110_five_c2_adsorption_20261006/gpu_return_review.json",
                "calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/batch_manifest.json",
                "calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/submission_summary.json",
                "calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/registry_receipt.json"]},
        "supersedes": [old_id],
    }
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    assert not target.exists()
    validate_event(event)
    write_json(target, event)
    print(json.dumps({"registry_inserted": receipt["inserted"], "event": str(target)}))


if __name__ == "__main__":
    main()
