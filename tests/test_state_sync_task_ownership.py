from __future__ import annotations

import json

import pytest

from scripts.state_manager.baseline import build_baseline_event
from scripts.state_manager.checkpoints import derive_task_completion_event
from scripts.state_manager.cli import _actionable_reviews, main
from scripts.state_manager.models import StateEvent
from scripts.state_manager.projections import render_current_task
from scripts.state_manager.proposals import ProposalStore, apply_proposal, build_proposal
from tests.test_state_manager import (
    END_MARKER,
    START_MARKER,
    adopt_current_task,
    file_evidence,
    init_repository,
    store,
    task_acceptance_event,
    task_event,
)


def _record_task(root, schema, event_store, event_id, *, entity="task-current", recorded_at=None):
    evidence = root / f"{event_id}.txt"
    evidence.write_text("bound task evidence\n", encoding="utf-8")
    payload = task_event(event_id, evidence=file_evidence(evidence, root), objective=event_id).payload
    payload["entity"]["id"] = entity
    if recorded_at is not None:
        payload["recorded_at"] = recorded_at
    event = StateEvent.from_mapping(payload, schema_path=schema)
    event_store.record(event)
    return event, evidence


def _managed_placeholder(root):
    (root / "tasks/current_task.md").write_text(
        START_MARKER.format(block_id="current_task") + "\nOld\n"
        + END_MARKER.format(block_id="current_task") + "\n", encoding="utf-8",
    )


def _sync(root, policy, schema, capsys):
    code = main(["--root", str(root), "--policy", str(policy), "--schema", str(schema), "sync", "--safe-only"])
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out else None, captured.err


def _approved_baseline(root, event_store):
    (root / "tasks/current_task.md").write_text(
        "# Current Task\n\n## Objective\n\nBaseline task\n\n"
        "## One Executable Step\n\nReview baseline.\n\n## Done When\n\n- Reviewed.\n",
        encoding="utf-8",
    )
    (root / "docs/02_CURRENT_STATE.md").write_text(
        "# State\n\n## Existing Section\n\n### Current Gate 2026-08-02\n\n- Recorded only.\n",
        encoding="utf-8",
    )
    baseline = build_baseline_event(root)
    event_store.record(baseline)
    event_store.record_review(
        proposal_id="proposal-reviewed-baseline", decision="approve", reviewer="user",
        reviewed_event_id=baseline.event_id, reviewed_event_sha256=baseline.digest,
    )
    return baseline


@pytest.mark.parametrize("legacy_date", ["2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"])
def test_sync_uses_canonical_task_instead_of_older_or_newer_legacy_task(tmp_path, capsys, legacy_date):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    _managed_placeholder(tmp_path)
    canonical, _ = _record_task(tmp_path, schema, event_store, "canonical-task")
    legacy, evidence = _record_task(
        tmp_path, schema, event_store, "legacy-task", entity="legacy-entity", recorded_at=legacy_date,
    )
    evidence.write_text("historical evidence changed after recording\n", encoding="utf-8")

    code, output, error = _sync(tmp_path, policy, schema, capsys)
    assert code == 0 and error == ""
    assert (tmp_path / "tasks/current_task.md").read_bytes() == render_current_task(canonical).encode("utf-8")
    assert [item["event_id"] for item in output["deferred_projection_events"]] == [legacy.event_id]
    manifest = json.loads((tmp_path / "data/state_handoff/projection_manifest.json").read_text(encoding="utf-8"))
    assert manifest["projections"]["tasks/current_task.md#current_task"]["source_event_id"] == canonical.event_id


def test_reviews_keep_only_pending_successor_of_current_task_entity(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    canonical, _ = _record_task(tmp_path, schema, event_store, "current-task")
    (tmp_path / "tasks/current_task.md").write_bytes(render_current_task(canonical).encode("utf-8"))
    pending = []
    for name, entity, supersedes in (
        ("old-task-review", "legacy-entity", []),
        ("next-task-review", "task-current", [canonical.event_id]),
    ):
        payload = task_event(name, supersedes=supersedes, objective=name).payload
        payload["entity"]["id"] = entity
        payload["review"] = {"required": True, "reason_codes": ["user_review"], "status": "pending"}
        event = StateEvent.from_mapping(payload, schema_path=schema)
        event_store.record(event)
        pending.append(event)

    reviews = _actionable_reviews(event_store, root=tmp_path, policy=policy)
    assert [item["event_id"] for item in reviews] == [pending[1].event_id]
    code, output, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 1
    assert len(output["pending_review"]) == 1
    assert output["deferred_projection_events"][0]["event_id"] == pending[0].event_id
    assert (tmp_path / "tasks/current_task.md").read_bytes() == render_current_task(canonical).encode("utf-8")


def test_canonical_completion_preserves_review_handoff_and_cannot_resurrect_legacy_or_baseline(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    baseline = _approved_baseline(tmp_path, event_store)
    canonical, event_store = adopt_current_task(tmp_path, policy, schema)
    legacy, _ = _record_task(tmp_path, schema, event_store, "legacy-active-task", entity="legacy-entity")
    validation = tmp_path / "validation.txt"
    validation.write_text("validation passed\n", encoding="utf-8")
    artifact = tmp_path / "result.txt"
    artifact.write_text("verified artifact\n", encoding="utf-8")
    acceptance = task_acceptance_event(
        canonical, validation_evidence=validation, artifact=artifact, root=tmp_path, requires_user_review=True,
    )
    event_store.record(acceptance)
    completion = derive_task_completion_event(acceptance, event_store=event_store, schema_path=schema)
    event_store.record(completion)

    code, output, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 1
    assert "No active task" not in (tmp_path / "tasks/current_task.md").read_text(encoding="utf-8")
    assert len(output["pending_review"]) == 1
    proposal_id = output["pending_review"][0]["proposal_id"]
    event_store.record_review(
        proposal_id=proposal_id, decision="approve", reviewer="user",
        reviewed_event_id=completion.event_id, reviewed_event_sha256=completion.digest,
    )

    code, output, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 0
    closed_task = (tmp_path / "tasks/current_task.md").read_bytes()
    assert b"No active task" in closed_task
    assert completion.event_id in (tmp_path / "docs/08_HISTORICAL_RESULTS.md").read_text(encoding="utf-8")
    assert event_store.current_task_source() is None
    assert {item["event_id"] for item in output["deferred_projection_events"]} == {legacy.event_id, baseline.event_id}
    code, repeated, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 0 and repeated["applied"] == []
    assert (tmp_path / "tasks/current_task.md").read_bytes() == closed_task


def test_ambiguous_legacy_tasks_fail_before_any_projection(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    _managed_placeholder(tmp_path)
    for name in ("first-legacy-task", "second-legacy-task"):
        _record_task(tmp_path, schema, event_store, name, entity=name)
    before = (tmp_path / "tasks/current_task.md").read_bytes()
    manifest = (tmp_path / "data/state_handoff/projection_manifest.json").read_bytes()

    code, output, error = _sync(tmp_path, policy, schema, capsys)
    assert code == 2 and output is None
    assert "multiple effective active task entities" in error
    assert (tmp_path / "tasks/current_task.md").read_bytes() == before
    assert (tmp_path / "data/state_handoff/projection_manifest.json").read_bytes() == manifest
    assert not ProposalStore(tmp_path, policy).cache_dir.exists()


def test_baseline_mixed_adoption_cannot_overwrite_current_task(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    baseline = _approved_baseline(tmp_path, event_store)
    canonical, _ = _record_task(tmp_path, schema, event_store, "established-task")
    (tmp_path / "tasks/current_task.md").write_bytes(render_current_task(canonical).encode("utf-8"))
    state_before = (tmp_path / "docs/02_CURRENT_STATE.md").read_bytes()

    code, output, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 0
    assert output["applied"] == []
    assert output["deferred_projection_events"][0]["event_id"] == baseline.event_id
    assert (tmp_path / "tasks/current_task.md").read_bytes() == render_current_task(canonical).encode("utf-8")
    assert (tmp_path / "docs/02_CURRENT_STATE.md").read_bytes() == state_before


def test_current_task_evidence_hash_failure_is_still_rejected(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    _managed_placeholder(tmp_path)
    _, evidence = _record_task(tmp_path, schema, event_store, "current-task")
    evidence.write_text("changed current evidence\n", encoding="utf-8")
    before = (tmp_path / "tasks/current_task.md").read_bytes()

    code, output, error = _sync(tmp_path, policy, schema, capsys)
    assert code == 2 and output is None
    assert "evidence hash changed" in error
    assert (tmp_path / "tasks/current_task.md").read_bytes() == before


def test_single_legacy_task_still_uses_existing_fallback_without_canonical_task(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    _managed_placeholder(tmp_path)
    legacy, _ = _record_task(tmp_path, schema, event_store, "only-legacy-task", entity="legacy-entity")

    code, output, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 0
    assert "deferred_projection_events" not in output
    assert event_store.current_task_source().event_id == legacy.event_id
    assert (tmp_path / "tasks/current_task.md").read_bytes() == render_current_task(legacy).encode("utf-8")


def test_approved_legacy_completion_is_deferred_with_its_handoff(tmp_path, capsys):
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    _managed_placeholder(tmp_path)
    legacy, _ = _record_task(tmp_path, schema, event_store, "old-legacy-task", entity="legacy-entity")
    apply_proposal(
        build_proposal(legacy, project_root=tmp_path, policy_path=policy),
        event_store=event_store, project_root=tmp_path, policy_path=policy, safe_only=True,
    )
    validation = tmp_path / "legacy-validation.txt"
    validation.write_text("validation passed\n", encoding="utf-8")
    artifact = tmp_path / "legacy-result.txt"
    artifact.write_text("legacy artifact\n", encoding="utf-8")
    payload = task_acceptance_event(
        legacy, validation_evidence=validation, artifact=artifact, root=tmp_path, requires_user_review=True,
    ).payload
    payload["payload"]["task_entity_id"] = "legacy-entity"
    acceptance = StateEvent.from_mapping(payload, schema_path=schema)
    event_store.record(acceptance)
    completion = derive_task_completion_event(acceptance, event_store=event_store, schema_path=schema)
    event_store.record(completion)
    closure = build_proposal(completion, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=closure["proposal_id"], decision="approve", reviewer="user",
        reviewed_event_id=completion.event_id, reviewed_event_sha256=completion.digest,
    )
    canonical, _ = _record_task(tmp_path, schema, event_store, "new-canonical-task")
    history = tmp_path / "docs/08_HISTORICAL_RESULTS.md"
    history_before = history.read_bytes()

    code, output, _ = _sync(tmp_path, policy, schema, capsys)
    assert code == 0
    assert [item["event_id"] for item in output["deferred_projection_events"]] == [completion.event_id]
    assert (tmp_path / "tasks/current_task.md").read_bytes() == render_current_task(canonical).encode("utf-8")
    assert history.read_bytes() == history_before
    assert event_store.get(completion.event_id).digest == completion.digest
