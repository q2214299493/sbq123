"""Resume a recorded failed run without inventing a previous research answer."""
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, write_json
from scripts.research_assistant.continuation import validate_progress
from scripts.research_assistant.runner import ResearchRun


def parent_run(tmp_path: Path, with_action=False):
    scope = tmp_path / "source"
    scope.mkdir()
    write_json(scope / "measurement.json", {"value": 2.75})
    parent = ResearchRun("Keep the original question", "diagnose", [scope], scope, tmp_path / "failed")
    if with_action:
        parent.tools.execute({"tool": "evidence.read", "target_ids": [parent.catalog.listed(scope / "measurement.json")],
            "query": "/value", "limit": 1})
    parent.problem = "backend connection failed;no answer received"
    parent.first_failure_stage = "model_turn"
    parent.finish()
    return scope, parent


def child_run(tmp_path, scope, parent):
    child = ResearchRun(parent.goal, parent.intent, [scope], scope, tmp_path / "resumed",
        previous_run=parent.output, update="Explicitly authorized recovery after connection checks")
    child.prepare_continuation()
    return child


def test_failed_first_turn_can_resume_without_result_or_fake_claims(tmp_path):
    scope, parent = parent_run(tmp_path)
    original = {p.name: p.read_bytes() for p in parent.output.iterdir() if p.is_file()}
    child = child_run(tmp_path, scope, parent)
    assert child.question_id == parent.question_id
    assert child.continuation["parent_had_answer"] is False
    assert child.continuation["previous_claims"] == []
    assert child.continuation["previous_options"] == []
    assert child.continuation["previous_failure"]["problem"] == parent.problem
    validate_progress({"progress": None}, child.continuation)
    child.prompt_for(1)  # No empty previous_ref enum may be generated.
    assert not (parent.output / "research_result.json").exists()
    assert original == {p.name: p.read_bytes() for p in parent.output.iterdir() if p.is_file()}


def test_failed_run_revalidates_completed_host_action(tmp_path):
    scope, parent = parent_run(tmp_path, with_action=True)
    child = child_run(tmp_path, scope, parent)
    result = child.tools.execute({"tool": "evidence.read", "target_ids": [child.catalog.listed(scope / "measurement.json")],
        "query": "/value", "limit": 1})
    assert result["host_executed"] is False
    assert result["reused_from_parent"]["run"] == str(parent.output)


@pytest.mark.parametrize("field,value", [("goal", "another goal"), ("question_id", "wrong"), ("answer", {"facts": []})])
def test_inconsistent_failed_state_is_rejected(tmp_path, field, value):
    scope, parent = parent_run(tmp_path)
    path = parent.output / "research_state.json"
    state = load_json_object(path)
    state[field] = value
    write_json(path, state)
    with pytest.raises(ValueError, match="failed parent"):
        child_run(tmp_path, scope, parent)


def test_changed_failed_journal_is_rejected(tmp_path):
    scope, parent = parent_run(tmp_path)
    with (parent.output / "journal.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="failed parent"):
        child_run(tmp_path, scope, parent)


def test_unanswered_parent_cannot_gain_invented_progress(tmp_path):
    scope, parent = parent_run(tmp_path)
    child = child_run(tmp_path, scope, parent)
    with pytest.raises(ValueError, match="unanswered"):
        validate_progress({"progress": {"changes": []}}, child.continuation)


def test_missing_success_result_does_not_use_failure_recovery(tmp_path):
    scope, parent = parent_run(tmp_path)
    path = parent.output / "run_receipt.json"
    receipt = load_json_object(path)
    receipt["status"] = "GENERATED"
    write_json(path, receipt)
    with pytest.raises((OSError, ValueError)):
        child_run(tmp_path, scope, parent)
