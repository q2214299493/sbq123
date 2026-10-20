"""Record local development-only selection;no model execution or promotion."""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

from .review import DEST, ROOT


def main():
    earlier = load_json_object(DEST / "review_receipt.json")
    original = next(row["sha256"] for row in earlier["source_files"] if row["path"].endswith("/review.py"))
    if original != sha256_file(DEST / "source_before_lint_refactor.py"):
        raise ValueError("generation-time source snapshot missing")
    proposal = DEST / "independent_validation_proposal.json"
    if sha256_file(proposal) != earlier["proposal_sha256"]:
        raise ValueError("frozen proposal changed")
    data = load_json_object(proposal)
    if data["selected_arm"] != "control" or data["heldout_count"] != 46 or data["scientific_boundaries"]["GPU_execution_authorized"]:
        raise ValueError("candidate/authorization boundary changed")
    suites = ET.parse(DEST / "scoped_tests.xml").getroot().findall("testsuite")
    tests = {key: sum(int(s.attrib[key]) for s in suites) for key in ("tests", "errors", "failures", "skipped")}
    if tests != {"tests": 6, "errors": 0, "failures": 0, "skipped": 0}:
        raise ValueError("directly related review tests did not pass")
    doc = "docs/reviews/fe110_adsorption_candidate_selection_20261020.md"
    files = [DEST / name for name in ("review_receipt.json", "source_before_lint_refactor.py", "checkpoint_metadata.json",
        "native_checkpoint_metadata.json", "exported_checkpoint_metrics.json", "grouped_development_review.json",
        "independent_validation_proposal.json", "scoped_tests.xml")]
    files += [ROOT / doc, ROOT / "archive/fe110_adsorption_candidate_review_20261020/review.py"]
    verified = {"status": "GROUPED_REVIEW_COMPLETE_CONTROL_FROZEN_VALIDATION_NOT_RUN", "selected_arm": "control",
        "candidate_sha256": data["models"]["candidate"]["sha256"], "tests": tests,
        "generation_source_preserved": True, "lint_refactor_changes_method_or_data": False,
        "new_model_predictions": 0, "new_training": 0, "new_VASP": 0, "production_model_promoted": False,
        "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in files]}
    write_json_exclusive(DEST / "validation_receipt.json", verified)
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-control-candidate-review-20261020"
    paths = [doc, proposal.relative_to(ROOT).as_posix(), (DEST / "validation_receipt.json").relative_to(ROOT).as_posix(),
             (DEST / "grouped_development_review.json").relative_to(ROOT).as_posix(),
             (DEST / "exported_checkpoint_metrics.json").relative_to(ROOT).as_posix()]
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "Development-only grouped review freezescontrol export for independent validation;46-frame baseline/control proposal prepared,not executable/authorized.No newmodel predictions,training,VASP or production promotion.",
        "evidence": [{"locator": path, "sha256": sha256_file(ROOT / path), "authority": "repository_document", "observed_at": now} for path in paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-corrected-training-completed-20261020"],
        "payload": {"objective": "Review the frozencontrol independent-validation proposal before any new GPU execution;no default-model replacement or speedup claim.",
            "phase": "verification", "current_evidence": [
                "User requested grouped-error review and independent-validation candidate selection.No new GPU inference/training/relaxation or VASP was authorized or run.",
                "Read-only CPU checkpoint checks confirm baseline/control/treatment hashes and architecture.Candidates omit epoch/step but contain val_metrics.Nativebest bytes match each export.",
                "Actual export roleMAE:control0.03978188027,treatment0.04030279919eV/A.Treatment improvesC0.97%,O18.43%,replay5.39%,but worsensH36.14%,nearFe9.30%,otherFe19.20%.Soft review warnings,not zero-tolerance rejection.",
                "Freezecontrol SHA256cfcac123cd56b866a1ea36cc780a3aee634f3aeec979bda4ae8bee2cc831e523 using development only.Single seed/twoepochs is not a statistical-superiority claim.",
                "Native checkpoint.pt is saved before validation;its best_val_metric lags epoch2.Do not substitute that stale value for actual exported val_metrics.",
                "Proposalbf2e4a7c745ae6569f69c70a262c8854566d8b6a123592ca123cbfc6dbfe0c92 freezes baseline/control46exact heldout structures,09_C/10_A23each;oldobserved16 excluded.92force predictions proposed,zero executed.Whole-job/equivalence/source-label integrity verified.",
                "Six directly related tests,compile and scoped Ruff pass.No scientific runtime changed;original proposal and generation source snapshot preserved."],
            "one_executable_step": "Present the frozen46-frame force-only baseline/control validation proposal for separate scope/budget approval;only then prepare an executable GPU request/backend binding.No heldout-driven model reselection.",
            "submission_boundary": "PROPOSAL_ONLY_NOT_EXECUTABLE_NOT_AUTHORIZED:GPU evaluation,training,relaxation,VASP and production promotion remain unauthorized.",
            "done_when": ["The frozen candidate/proposal and separate compute budget receive explicit user authorization.",
                "An exact-hash executable validation package passes native/input/backend preflight before any model prediction.",
                "Independent results retain per-job/role/failure-tail review and do not substitute for geometry or a matched VASP acceleration benchmark."],
            "constraints": ["No test-driven candidate reselection or use of46heldout/16observed frames for fitting/epoch selection.",
                "46frames represent two correlated trajectories,not46independent environments;mother jobs were screened and baseline pretraining overlap is unknown.",
                "C2H3 lacks training coverage;candidate energies remain untrained and TS-domain acceptance absent.",
                "Preserve old packages,checkpoints and source evidence;no automatic retries or production replacement."],
            "authoritative_references": ["configs/execution_backends.yaml", doc, paths[1], paths[2]]}}
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"status": verified["status"], "tests": tests, "event": target.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
