"""Local integration tests: no SSH, GPU, VASP or model training is performed."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, sha256_json, write_json
from scripts.registry_schema import migrate_registry
from scripts.neb_agent import submission
from scripts.ts_strategy_engine import learning_cli, strategy_learning as learning
from scripts.ts_strategy_engine.learning_evidence import bind_files, observe, vasp_input_hashes
from scripts.ts_strategy_engine.learning_store import get_event, history_token, read_events, save_event
from scripts.ts_strategy_engine.strategy import compose_strategy


@pytest.fixture
def db(tmp_path):
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    return database


def source(tmp_path: Path, name="evidence.json", **values):
    path = tmp_path / name
    write_json(path, values or {"status": "failed", "cause": "optimizer"})
    return path


def observation(path, pointer="/status", value="failed"):
    return {"path": str(path), "sha256": sha256_file(path), "pointer": pointer, "value": value}


def baseline(db, tmp_path, **updates):
    path = source(tmp_path, "settings_source.json", settings={"images": 5})
    spec = {
        "task_id": "reaction-1", "cases": ["reaction-1"], "attempt_budget": 5,
        "settings": {"candidate_method": "ordinary_neb", "initial_images": 5, "interpolation_strategy": "segmented_idpp"},
        "sources": {"current": str(path)},
    }
    return learning.capture_baseline(db, {**spec, **updates})


def attempt(db, variant, inputs, attempt_id="try-1", **updates):
    return learning.start_attempt(db, {"attempt_id": attempt_id, "variant_id": variant,
        "task_id": "reaction-1", "kind": "matris_ml_neb", "inputs": inputs, "parent_attempt_id": None, **updates})


def outcome(path, **updates):
    return {"status": "failure", "failure_class": "optimizer", "root_cause_status": "confirmed",
        "deterministic": True, "reviewer": "test reviewer", "observations": [observation(path)],
        "costs": {}, "ts_template_id": None, **updates}


def hashes(inputs):
    return {key: ref["sha256"] for key, ref in bind_files(inputs).items()}


def test_reviewed_outcome_correction_keeps_original_and_clears_false_retry_block(db, tmp_path):
    variant = baseline(db, tmp_path)
    inputs = {"request": str(source(tmp_path, "request.json", n=1))}
    evidence = source(tmp_path)
    attempt(db, variant, inputs)
    learning.record_outcome(db, "try-1", outcome(evidence))
    previous = get_event(db, "outcome", "try-1")
    assert learning.retry_assessment(db, "matris_ml_neb", hashes(inputs))["status"] != "NO_KNOWN_FAILURE"
    accepted = source(tmp_path, "accepted.json", status="accepted")
    correction = outcome(accepted, status="stage_pass", deterministic=False,
                         observations=[observation(accepted, value="accepted")])
    learning.revise_outcome(db, "try-1", correction, previous_sha256=sha256_json(previous), reason="reviewed metric interpretation")
    assert get_event(db, "outcome", "try-1")["status"] == "stage_pass"
    assert learning.retry_assessment(db, "matris_ml_neb", hashes(inputs))["status"] == "NO_KNOWN_FAILURE"
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ts_strategy_events WHERE event_type='outcome'").fetchone()[0] == 2
        original = connection.execute("SELECT payload_sha256 FROM ts_strategy_events WHERE event_type='outcome' AND entity_id='try-1'").fetchone()[0]
    assert original == sha256_json(previous)
    with pytest.raises(ValueError, match="outcome changed"):
        learning.revise_outcome(db, "try-1", correction, previous_sha256=sha256_json(previous), reason="stale review")


def test_outcome_correction_rejects_unbound_evidence(db, tmp_path):
    variant = baseline(db, tmp_path)
    evidence = source(tmp_path)
    attempt(db, variant, {"request": str(evidence)})
    learning.record_outcome(db, "try-1", outcome(evidence))
    previous = get_event(db, "outcome", "try-1")
    correction = outcome(evidence, status="stage_pass", deterministic=False)
    correction["observations"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="stale evidence"):
        learning.revise_outcome(db, "try-1", correction, previous_sha256=sha256_json(previous), reason="invalid source")
    assert get_event(db, "outcome", "try-1") == previous


def test_baseline_is_idempotent_and_captures_dirty_file_content(db, tmp_path):
    root = baseline(db, tmp_path)
    assert baseline(db, tmp_path) == root
    record = get_event(db, "variant", root)
    assert record["parent_id"] is None
    assert record["sources"]["current"]["sha256"] == sha256_file(tmp_path / "settings_source.json")
    assert record["automatic_submission"] is False


@pytest.mark.parametrize("changes", [{"ENCUT": 300}, {"initial_images": 0}, {"initial_images": True},
    {"interpolation_strategy": "invented"}, {"initial_images": 7, "candidate_method": "ci_neb"}, {"initial_images": 5}])
def test_proposal_rejects_locked_unknown_invalid_or_unbounded_changes(db, tmp_path, changes):
    root = baseline(db, tmp_path)
    evidence = source(tmp_path)
    with pytest.raises(ValueError):
        learning.propose_variant(db, root, changes, "diagnosed cause", [observation(evidence)])
    assert len(read_events(db, "variant")) == 1


def test_sella_is_reference_only_and_cannot_clear_existing_stop(db, tmp_path):
    root = baseline(db, tmp_path)
    evidence = source(tmp_path)
    child = learning.propose_variant(db, root, {"candidate_method": "aqcat25_ba_sella"}, "test candidate branch", [observation(evidence)])
    strategy = {"status": "NEEDS_REVIEW", "neb_settings": {"initial_images": 3}, "automatic_submission": False}
    result = learning.apply_variant(db, child, strategy)
    assert result["status"] == "NEEDS_BA_SELLA_CANDIDATE_HANDOFF_REVIEW"
    assert result["neb_settings"]["initial_images"] == 5
    assert result["reference_methods"]["aqcat25_ba_sella"]["establishes_ts"] is False
    assert strategy["neb_settings"]["initial_images"] == 3
    strategy["status"] = "STOP_FAMILY_CONTRACT_MISMATCH"
    assert learning.apply_variant(db, child, strategy)["status"] == strategy["status"]


def test_candidate_budget_and_stale_baseline(db, tmp_path):
    root = baseline(db, tmp_path)
    evidence = source(tmp_path)
    for count in (6, 7):
        learning.propose_variant(db, root, {"initial_images": count}, "local refinement", [observation(evidence)])
    with pytest.raises(ValueError, match="budget"):
        learning.propose_variant(db, root, {"initial_images": 8}, "local refinement", [observation(evidence)])
    (tmp_path / "settings_source.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        learning.propose_variant(db, root, {"initial_images": 9}, "local refinement", [observation(evidence)])


def test_failed_attempt_is_blocked_even_after_directory_or_id_rename(db, tmp_path):
    root = baseline(db, tmp_path)
    inputs = {"INCAR": str(source(tmp_path, "input.json", values=1))}
    evidence = source(tmp_path)
    attempt(db, root, inputs)
    learning.record_outcome(db, "try-1", outcome(evidence))
    copied = tmp_path / "renamed.json"
    shutil.copyfile(inputs["INCAR"], copied)
    with pytest.raises(ValueError, match="BLOCKED_KNOWN_FAILURE"):
        attempt(db, root, {"INCAR": str(copied)}, "new-name")
    write_json(copied, {"values": 2})
    assert attempt(db, root, {"INCAR": str(copied)}, "changed-input") == "changed-input"


def test_failure_is_not_a_global_method_ban(db, tmp_path):
    root = baseline(db, tmp_path)
    path = source(tmp_path)
    inputs = {"input": str(path)}
    attempt(db, root, inputs)
    learning.record_outcome(db, "try-1", outcome(path))
    assert learning.retry_assessment(db, "dimer", hashes(inputs))["status"] == "NO_KNOWN_FAILURE"


@pytest.mark.parametrize("updates", [{"root_cause_status": "hypothesis", "deterministic": False},
    {"status": "unknown", "root_cause_status": "unknown", "failure_class": "unknown", "deterministic": False}])
def test_uncertain_failure_requires_review_without_claiming_model_error(db, tmp_path, updates):
    root = baseline(db, tmp_path)
    path = source(tmp_path)
    attempt(db, root, {"input": str(path)})
    learning.record_outcome(db, "try-1", outcome(path, **updates))
    assert learning.retry_assessment(db, "matris_ml_neb", hashes({"input": str(path)}))["status"] == "NEEDS_REVIEW"
    assert get_event(db, "outcome", "try-1")["authorizes_training"] is False


def test_stale_failure_evidence_cannot_silently_unblock_retry(db, tmp_path):
    root = baseline(db, tmp_path)
    inp = source(tmp_path, "input.json")
    evidence = source(tmp_path)
    attempt(db, root, {"input": str(inp)})
    learning.record_outcome(db, "try-1", outcome(evidence))
    write_json(evidence, {"status": "edited"})
    assert learning.retry_assessment(db, "matris_ml_neb", hashes({"input": str(inp)}))["status"] == "NEEDS_REVIEW"


def test_attempt_idempotency_immutability_budget_and_unresolved_state(db, tmp_path):
    root = baseline(db, tmp_path, attempt_budget=1)
    inp = {"input": str(source(tmp_path))}
    assert attempt(db, root, inp) == attempt(db, root, inp)
    with pytest.raises(ValueError, match="immutable"):
        attempt(db, root, inp, kind="aqcat25_ml_neb")
    with pytest.raises(ValueError, match="budget"):
        attempt(db, root, inp, "try-2")


def test_pending_duplicate_and_resume_require_checkpoint(db, tmp_path):
    root = baseline(db, tmp_path)
    inp = {"input": str(source(tmp_path))}
    attempt(db, root, inp)
    with pytest.raises(ValueError, match="unresolved"):
        attempt(db, root, inp, "try-2")
    with pytest.raises(ValueError, match="resume_checkpoint"):
        attempt(db, root, inp, "try-2", parent_attempt_id="try-1")
    inp["resume_checkpoint"] = str(source(tmp_path, "checkpoint.json", step=48))
    attempt(db, root, inp, "try-2", parent_attempt_id="try-1")


def test_outcome_cannot_be_overwritten_and_done_cannot_become_ts(db, tmp_path):
    root = baseline(db, tmp_path)
    path = source(tmp_path)
    attempt(db, root, {"input": str(path)})
    with pytest.raises(ValueError, match="Grade-A"):
        learning.record_outcome(db, "try-1", outcome(path, status="ts_validated", deterministic=False, ts_template_id="invented"))
    learning.record_outcome(db, "try-1", outcome(path))
    with pytest.raises(ValueError, match="immutable"):
        learning.record_outcome(db, "try-1", outcome(path, reviewer="someone else"))


def test_observations_and_costs_are_checked_against_sources(db, tmp_path):
    root = baseline(db, tmp_path)
    path = source(tmp_path)
    attempt(db, root, {"input": str(path)})
    with pytest.raises(ValueError, match="differs"):
        observe([observation(path, value="passed")])
    with pytest.raises(ValueError, match="does not exist"):
        observe([observation(path, pointer="/nonexistent")])
    with pytest.raises(ValueError, match="matching source"):
        learning.record_outcome(db, "try-1", outcome(path, costs={"gpu_hours": 1.0}))
    with pytest.raises(ValueError, match="invalid cost"):
        learning.record_outcome(db, "try-1", outcome(path, costs={"gpu_hours": float("nan")}))


def test_stage_improvement_does_not_promote_or_claim_ts(db, tmp_path):
    root = baseline(db, tmp_path)
    evidence = source(tmp_path)
    child = learning.propose_variant(db, root, {"initial_images": 7}, "resolve missing images", [observation(evidence)])
    attempt(db, root, {"input": str(source(tmp_path, "old.json", value=1))})
    learning.record_outcome(db, "try-1", outcome(evidence))
    attempt(db, child, {"input": str(source(tmp_path, "new.json", value=2))}, "try-2")
    learning.record_outcome(db, "try-2", outcome(evidence, status="stage_pass", deterministic=False))
    result = learning.compare_variants(db, root, child)
    assert result["decision"] == "NEEDS_MORE_EVIDENCE"
    assert result["candidate"]["validated_tasks"] == []
    assert result["candidate"]["stage_pass_tasks"] == ["reaction-1"]
    assert result["automatic_promotion"] is False


def test_history_corruption_and_concurrent_update_are_rejected(db, tmp_path):
    root = baseline(db, tmp_path)
    token = history_token(db)
    save_event(db, "attempt", "synthetic", {"test": True})
    with pytest.raises(ValueError, match="concurrently"):
        save_event(db, "attempt", "stale", {"test": True}, expected_history=token)
    from tests.registry_fixture_mutation import fixture_connection

    with fixture_connection(db) as connection:
        connection.execute("UPDATE ts_strategy_events SET payload_json='{}' WHERE entity_id=?", (root,))
    with pytest.raises(ValueError, match="hash mismatch"):
        read_events(db, "variant")


def test_vasp_preflight_actually_blocks_known_failure_before_remote_execution(db, tmp_path, monkeypatch):
    root = baseline(db, tmp_path)
    job = tmp_path / "job"
    job.mkdir()
    for name, content in {"INCAR": "NSW=0\nIBRION=-1\n", "KPOINTS": "K", "POTCAR.spec": "Fe", "POSCAR": "P", "script.lsf": "NP=1"}.items():
        (job / name).write_text(content, encoding="utf-8")
    initial = submission.preflight(job, "diagnostic_static", learning_database=db)
    assert initial["passed"]
    inputs = {name: str(job / name) for name in vasp_input_hashes(initial["files"])}
    attempt(db, root, inputs, kind="diagnostic_static")
    learning.record_outcome(db, "try-1", outcome(source(tmp_path)))
    result = submission.preflight(job, "diagnostic_static", learning_database=db)
    assert not result["passed"]
    assert "strategy_retry:BLOCKED_KNOWN_FAILURE" in result["errors"]
    monkeypatch.setattr(submission, "preflight", lambda *args: result)
    monkeypatch.setattr(submission, "_run", lambda *_: pytest.fail("remote execution must not occur"))
    with pytest.raises(ValueError, match="bundle changed"):
        submission.submit(job, tmp_path / "unused.json", "sunboquan-codex", "~/sbq/job", "~/sbq/pot", "a" * 64, "SUBMIT_DIAGNOSTIC_VASP")


def test_cli_help_history_and_output_protection(db, tmp_path, capsys):
    root = baseline(db, tmp_path)
    learning_cli.main(["--database", str(db), "history"])
    assert root in capsys.readouterr().out
    output = source(tmp_path, "existing.json", original=True)
    before = output.read_bytes()
    with pytest.raises(SystemExit) as exc:
        learning_cli.main(["--database", str(db), "--output", str(output), "methods"])
    assert exc.value.code == 2
    assert output.read_bytes() == before


def test_warm_start_captures_existing_images_without_rewriting(db, tmp_path):
    job = tmp_path / "existing"
    job.mkdir()
    for name in ("KPOINTS", "POTCAR.spec", "script.lsf"):
        (job / name).write_text("existing", encoding="utf-8")
    (job / "INCAR").write_text("IMAGES=5\nLCLIMB=.FALSE.\n", encoding="utf-8")
    write_json(job / "path_generation_report.json", {"interior_images": 5, "method_used": "segmented_idpp"})
    for index in range(7):
        image = job / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text(f"existing-image-{index}", encoding="utf-8")
    before = {str(p): p.read_bytes() for p in job.rglob("*") if p.is_file()}
    root = learning.capture_workdir(db, job, "reaction-1", {})
    assert get_event(db, "variant", root)["settings"]["initial_images"] == 5
    assert before == {str(p): p.read_bytes() for p in job.rglob("*") if p.is_file()}


def test_default_strategy_exposes_sella_without_selecting_it():
    import yaml
    config = yaml.safe_load(Path("configs/ts_strategy_engine/families.yaml").read_text(encoding="utf-8"))
    fingerprint = {"reaction_family": "hydrogen_transfer", "fingerprint_id": "synthetic", "broken_bonds": [], "formed_bonds": []}
    strategy = compose_strategy(fingerprint, [], config)
    assert "aqcat25_ba_sella" in strategy["reference_methods"]
    assert strategy["automatic_submission"] is False
    assert "candidate_method_preference" not in strategy


def test_unified_cli_forwards_database_and_report_flags(db, tmp_path, capsys):
    from scripts.ts_strategy_engine.cli import parser
    report = tmp_path / "methods.json"
    args = parser().parse_args(["learning", "--database", str(db), "--output", str(report), "methods"])
    args.handler(args)
    assert report.is_file()
    assert "aqcat25_ba_sella" in capsys.readouterr().out


def test_existing_validated_template_must_match_the_attempt_calculation(tmp_path):
    from test_ts_strategy_engine import database, successful_record
    from scripts.ts_strategy_engine.templates import record_template
    db = database(tmp_path / "registered.sqlite3")
    template = successful_record()
    record_template(db, template)
    task_id = template["fingerprint"]["reaction_id"]
    root = baseline(db, tmp_path, task_id=task_id, cases=[task_id])
    evidence = source(tmp_path)
    attempt(db, root, {"input": str(evidence)}, task_id=task_id, source_calculation_id="calc_ts")
    learning.record_outcome(db, "try-1", outcome(evidence, status="ts_validated", deterministic=False,
                                               ts_template_id=template["template_id"]))
    assert learning._variant_results(db, root, [task_id])["validated_tasks"] == [task_id]
    with pytest.raises(ValueError, match="Grade-A"):
        learning._accepted_template(db, template["template_id"], task_id, "wrong_calculation")
    child = learning.propose_variant(db, root, {"initial_images": 7}, "refine", [observation(evidence)])
    with pytest.raises(ValueError, match="different strategy variants"):
        attempt(db, child, {"other": str(evidence)}, "try-2", task_id=task_id, source_calculation_id="calc_ts")


@pytest.mark.parametrize("candidate_succeeds", [True, False])
def test_comparison_uses_real_registry_validation_and_detects_regression(tmp_path, candidate_succeeds):
    from test_ts_strategy_engine import database, successful_record
    from scripts.ts_strategy_engine.templates import record_template
    db = database(tmp_path / "registered.sqlite3")
    template = successful_record()
    record_template(db, template)
    task = template["fingerprint"]["reaction_id"]
    root = baseline(db, tmp_path, task_id=task, cases=[task])
    evidence = source(tmp_path)
    child = learning.propose_variant(db, root, {"initial_images": 7}, "one parameter comparison", [observation(evidence)])
    for is_candidate, variant in ((False, root), (True, child)):
        success = is_candidate == candidate_succeeds
        attempt_id = "candidate" if is_candidate else "baseline"
        inp = source(tmp_path, attempt_id + ".json", variant=variant)
        attempt(db, variant, {"input": str(inp)}, attempt_id, task_id=task,
                source_calculation_id="calc_ts" if success else None)
        result = outcome(evidence)
        if success:
            result.update(status="ts_validated", deterministic=False, ts_template_id=template["template_id"])
        learning.record_outcome(db, attempt_id, result)
    result = learning.compare_variants(db, root, child)
    assert result["decision"] == ("ELIGIBLE_FOR_REVIEW" if candidate_succeeds else "KEEP_BASELINE")
    assert result["regressions"] == ([] if candidate_succeeds else [task])
    assert result["automatic_promotion"] is False


def test_planner_selects_reference_branch_without_generating_a_neb(tmp_path):
    import numpy as np
    import yaml
    from test_ts_strategy_engine import database, contract
    from scripts.neb_agent.utils_structure import Poscar, write_poscar
    from scripts.ts_strategy_engine.workflow import PlanRequest, plan
    db = database(tmp_path / "registry.sqlite3")
    task = contract()["reaction_id"]
    root = baseline(db, tmp_path, task_id=task, cases=[task])
    evidence = source(tmp_path)
    child = learning.propose_variant(db, root, {"candidate_method": "aqcat25_ba_sella"}, "reference only", [observation(evidence)])
    structure = Poscar(comment="synthetic", cell=np.eye(3) * 10, symbols=["Fe", "C", "O"], counts=[1, 1, 1],
                       frac=np.array([[0., 0., 0.], [.2, 0., .2], [.4, 0., .2]]), selective=True,
                       flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")])
    initial, final = tmp_path / "IS", tmp_path / "FS"
    write_poscar(initial, structure)
    write_poscar(final, structure)
    contract_path = tmp_path / "contract.yaml"
    contract_path.write_text(yaml.safe_dump(contract()), encoding="utf-8")
    request = PlanRequest(initial=initial, final=final, contract=contract_path, workdir=tmp_path / "new-plan",
        database=db, families=Path("configs/ts_strategy_engine/families.yaml"),
        thresholds=Path("configs/neb_agent/default_thresholds.yaml"), strategy_variant=child)
    result = plan(request)
    assert result["status"] == "NEEDS_BA_SELLA_CANDIDATE_HANDOFF_REVIEW"
    assert not (request.workdir / "path_candidate").exists()
    assert result["automatic_submission"] is False
    from dataclasses import replace
    with pytest.raises(ValueError, match="GPU candidate reference"):
        plan(replace(request, workdir=tmp_path / "invalid-plan", initialize_path=True))


def test_vasp_incomplete_input_identity_is_rejected(db, tmp_path):
    root = baseline(db, tmp_path)
    with pytest.raises(ValueError, match="complete input manifest"):
        attempt(db, root, {"INCAR": str(source(tmp_path))}, kind="ordinary_neb")


def test_task_failure_lessons_are_returned_to_planning(db, tmp_path):
    root = baseline(db, tmp_path)
    evidence = source(tmp_path)
    attempt(db, root, {"input": str(evidence)})
    learning.record_outcome(db, "try-1", outcome(evidence, failure_class="runtime"))
    lessons = learning.task_lessons(db, "reaction-1")
    assert lessons[0]["next_review"] == "repair_runtime_without_training"
    assert learning.task_lessons(db, "unrelated-reaction") == []


def test_historical_failure_import_preserves_unknown_inputs_without_false_ban(db, tmp_path):
    evidence = source(tmp_path)
    spec = {"attempt_id": "historical", "task_id": "reaction-1", "kind": "matris_ml_neb",
            "inputs": None, "outcome": outcome(evidence, failure_class="runtime")}
    assert learning.import_failure(db, spec) == learning.import_failure(db, spec)
    assert get_event(db, "attempt", "historical")["variant_id"] is None
    assert learning.task_lessons(db, "reaction-1")[0]["scope"] == "advisory_missing_historical_inputs"
    assert learning.retry_assessment(db, "matris_ml_neb", hashes({"input": str(evidence)}))["status"] == "NO_KNOWN_FAILURE"


def test_invalid_historical_outcome_does_not_leave_half_an_import(db, tmp_path):
    evidence = source(tmp_path)
    spec = {"attempt_id": "historical", "task_id": "reaction-1", "kind": "matris_ml_neb",
            "inputs": None, "outcome": outcome(evidence, observations=[observation(evidence, value="invented")])}
    with pytest.raises(ValueError, match="differs"):
        learning.import_failure(db, spec)
    assert not read_events(db, "attempt")
    assert not read_events(db, "outcome")
