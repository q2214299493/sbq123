from __future__ import annotations

import json
import multiprocessing
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.artifact_io import sha256_file
from scripts.state_manager.audit import _latest_status_mentions, audit_repository
from scripts.state_manager.baseline import build_baseline_event
from scripts.state_manager.checkpoints import derive_task_completion_event
from scripts.state_manager.lifecycle import build_task_transition_event
from scripts.state_manager.lifecycle_views import build_lifecycle_views_adoption_event
from scripts.state_manager.models import StateEvent
from scripts.state_manager.projections import (
    END_MARKER,
    START_MARKER,
    render_current_task,
    render_state_block,
)
from scripts.state_manager.cli import _control_status, main as state_manager_main
from scripts.state_manager.proposals import (
    ProposalStore,
    ReviewRequired,
    StaleProposal,
    apply_proposal,
    build_proposal,
)
from scripts.state_manager.reconciliation import build_entity_reconciliation_event
from scripts.state_manager.store import EventStore
from scripts.state_manager.stale_items import build_stale_item_batch_event, build_stale_item_event
from scripts.state_manager.state_compaction import build_state_history_compaction_event


ROOT = Path(__file__).resolve().parents[1]
TIMESTAMP = "2026-08-02T08:00:00+08:00"


def init_repository(root: Path, *, include_module: bool = True) -> tuple[Path, Path]:
    for relative in (
        "configs",
        "modules/state_handoff/events",
        "modules/state_handoff/archive",
        "data/state_handoff",
        "tasks",
        "docs",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    policy = root / "configs/state_handoff.yaml"
    schema = root / "configs/state_handoff_event.schema.json"
    shutil.copy2(ROOT / "configs/state_handoff.yaml", policy)
    shutil.copy2(ROOT / "configs/state_handoff_event.schema.json", schema)
    (root / "data/state_handoff/projection_manifest.json").write_text(
        '{"schema_version": 1, "projections": {}}\n',
        encoding="utf-8",
    )
    managed_views = {
        "tasks/backlog.md": ("task_backlog_events", "Managed Backlog"),
        "docs/04_ERROR_LOG.md": ("task_error_events", "Managed Open Errors"),
        "docs/03_DECISIONS_LOG.md": ("task_decision_events", "Managed Decisions"),
        "docs/08_HISTORICAL_RESULTS.md": ("task_history_events", "Managed Task History"),
    }
    for relative, (block_id, title) in managed_views.items():
        (root / relative).write_text(
            f"# Test View\n\n{START_MARKER.format(block_id=block_id)}\n"
            f"## {title}\n\n{END_MARKER.format(block_id=block_id)}\n",
            encoding="utf-8",
        )
    if include_module:
        (root / "modules/state_handoff/README.md").write_text(
            "# State Handoff\n\n## Purpose\n\nTest.\n\n## Done Criteria\n\nTest.\n",
            encoding="utf-8",
        )
    return policy, schema


def event_payload(
    event_id: str,
    event_type: str,
    kind: str,
    entity_id: str,
    payload: dict[str, Any],
    *,
    evidence: list[dict[str, Any]] | None = None,
    supersedes: list[str] | None = None,
    review_required: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "entity": {"kind": kind, "id": entity_id, "module": "state_handoff"},
        "occurred_at": TIMESTAMP,
        "recorded_at": TIMESTAMP,
        "summary": f"{event_type} {entity_id}",
        "payload": payload,
        "evidence": evidence or [],
        "supersedes": supersedes or [],
        "review": {
            "required": review_required,
            "reason_codes": ["user_review"] if review_required else [],
            "status": "pending" if review_required else "not_required",
        },
    }


def task_event(
    event_id: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
    supersedes: list[str] | None = None,
    phase: str = "verification",
    objective: str = "Keep 状态 current",
) -> StateEvent:
    return StateEvent.from_mapping(
        event_payload(
            event_id,
            "task_opened" if not supersedes else "task_updated",
            "task",
            "task-current",
            {
                "objective": objective,
                "current_evidence": ["Evidence is hash-bound."],
                "one_executable_step": "Run one read-only audit.",
                "done_when": ["The audit report is reviewed."],
                "phase": phase,
                "constraints": ["Do not submit calculations."],
                "authoritative_references": ["configs/state_handoff.yaml"],
            },
            evidence=evidence,
            supersedes=supersedes,
        )
    )


@pytest.mark.parametrize("phase", ["open", "active", "blocked", "verification"])
def test_active_task_projection_preserves_execution_backend_authority(phase: str) -> None:
    projected = render_current_task(task_event(f"event-task-backend-{phase}", phase=phase))

    assert "## Authoritative Constraint" in projected
    assert "`configs/execution_backends.yaml`" in projected


def file_evidence(path: Path, root: Path) -> list[dict[str, Any]]:
    return [
        {
            "locator": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "authority": "repository_document",
            "observed_at": TIMESTAMP,
        }
    ]


def task_acceptance_event(
    task: StateEvent,
    *,
    validation_evidence: Path,
    artifact: Path,
    root: Path,
    requires_user_review: bool = False,
    risk_status: str = "no_open_risks",
    handoff: dict[str, Any] | None = None,
) -> StateEvent:
    validation_hash = sha256_file(validation_evidence)
    artifact_hash = sha256_file(artifact)
    task_payload = (
        task.payload["payload"]["task"]
        if task.event_type == "baseline_adopted"
        else task.payload["payload"]
    )
    if handoff is None:
        handoff = {
            "history": {
                "title": "Task accepted",
                "summary": "The formal task acceptance passed.",
                "outcome": "Closed after evidence-bound validation.",
                "evidence_sha256": [validation_hash],
            },
            "backlog_items": [],
            "errors": [],
            "decisions": [],
        }
    return StateEvent.from_mapping(
        event_payload(
            "event-task-acceptance-001",
            "task_acceptance_recorded",
            "task_acceptance",
            "acceptance-task-current-001",
            {
                "task_entity_id": "task-current",
                "task_event_id": task.event_id,
                "task_event_sha256": task.digest,
                "completion_summary": "All required task evidence passed.",
                "done_when_results": [
                    {
                        "criterion": task_payload["done_when"][0],
                        "status": "passed",
                        "evidence_sha256": [validation_hash],
                    }
                ],
                "validation_results": [
                    {
                        "kind": "test",
                        "name": "targeted regression",
                        "command": "python -m pytest tests/test_target.py -q",
                        "exit_code": 0,
                        "status": "passed",
                        "evidence_sha256": [validation_hash],
                    }
                ],
                "artifact_policy": "required",
                "artifacts": [
                    {
                        "path": artifact.relative_to(root).as_posix(),
                        "sha256": artifact_hash,
                        "status": "present",
                        "evidence_sha256": [artifact_hash],
                    }
                ],
                "risk_assessment": {
                    "status": risk_status,
                    "summary": "No unreviewed task risks remain.",
                    "evidence_sha256": [validation_hash],
                },
                "handoff": handoff,
                "requires_user_review": requires_user_review,
                "review_reason_codes": (
                    ["accepted_open_risks"] if requires_user_review else []
                ),
                "verdict": "accepted",
            },
            evidence=(
                file_evidence(validation_evidence, root)
                + file_evidence(artifact, root)
            ),
        )
    )


def store(root: Path, schema: Path) -> EventStore:
    return EventStore(
        events_dir=root / "modules/state_handoff/events",
        schema_path=schema,
        project_root=root,
    )


def adopt_current_task(
    root: Path,
    policy: Path,
    schema: Path,
) -> tuple[StateEvent, EventStore]:
    current_task = root / "tasks/current_task.md"
    current_task.write_text("# Current Task\n\nLegacy unmanaged task.\n", encoding="utf-8")
    task = task_event("event-task-checkpoint-base-001")
    event_store = store(root, schema)
    event_store.record(task)
    proposal = build_proposal(task, project_root=root, policy_path=policy)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=task.event_id,
        reviewed_event_sha256=task.digest,
    )
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=root,
        policy_path=policy,
    )
    return task, event_store


def test_event_schema_rejects_unreviewed_scientific_claim() -> None:
    payload = event_payload(
        "event-task-science-001",
        "task_opened",
        "task",
        "task-science",
        {
            "objective": "Test",
            "one_executable_step": "Inspect",
            "done_when": ["Done"],
            "scientific_acceptance": True,
        },
    )
    with pytest.raises(ValueError, match="scientific claims require user review"):
        StateEvent.from_mapping(payload)


def test_log_event_rejects_missing_markdown_payload() -> None:
    payload = task_event("event-error-missing-markdown-001").payload
    payload["event_type"] = "error_opened"
    payload["entity"] = {
        "kind": "error",
        "id": "error-001",
        "module": "state_handoff",
    }
    payload["payload"] = {}
    payload["review"] = {
        "required": True,
        "reason_codes": ["reviewed_log_or_history_change"],
        "status": "pending",
    }
    with pytest.raises(ValueError, match="payload.markdown"):
        StateEvent.from_mapping(payload)


def test_event_store_is_idempotent_and_immutable(tmp_path: Path) -> None:
    _, schema = init_repository(tmp_path)
    event = task_event("event-task-store-001")
    event_store = store(tmp_path, schema)

    first = event_store.record(event)
    second = event_store.record(event)

    assert first == second
    assert len(list(first.parent.glob("event-task-store-001.json"))) == 1
    changed = dict(event.payload)
    changed["summary"] = "different immutable content"
    with pytest.raises(ValueError, match="immutable event ID"):
        event_store.record(StateEvent.from_mapping(changed))


def test_pending_review_event_does_not_become_effective_before_approval(
    tmp_path: Path,
) -> None:
    _, schema = init_repository(tmp_path)
    payload = task_event("event-task-pending-review-001").payload
    payload["review"] = {
        "required": True,
        "reason_codes": ["manual_projection_import"],
        "status": "pending",
    }
    event = StateEvent.from_mapping(payload, schema_path=schema)
    event_store = store(tmp_path, schema)
    event_store.record(event)

    assert event_store.current_task_source() is None
    assert [item.event_id for item in event_store.pending_review_events()] == [event.event_id]
    event_store.record_review(
        proposal_id="proposal-pending-review-001",
        decision="approve",
        reviewer="user",
        reviewed_event_id=event.event_id,
        reviewed_event_sha256=event.digest,
    )
    assert event_store.current_task_source().event_id == event.event_id


def test_actionable_pending_reviews_hide_drafts_that_do_not_supersede_current_state(tmp_path: Path) -> None:
    _, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    first = task_event("event-task-review-source-001")
    current = task_event("event-task-review-current-002", supersedes=[first.event_id], objective="Current state")
    stale_payload = task_event("event-task-review-stale-003", supersedes=[first.event_id]).payload
    stale_payload["review"] = {"required": True, "reason_codes": ["user_review"], "status": "pending"}
    next_payload = task_event("event-task-review-next-004", supersedes=[current.event_id]).payload
    next_payload["review"] = {"required": True, "reason_codes": ["user_review"], "status": "pending"}
    stale = StateEvent.from_mapping(stale_payload, schema_path=schema)
    next_event = StateEvent.from_mapping(next_payload, schema_path=schema)
    for event in (first, current, stale, next_event):
        event_store.record(event)

    assert [event.event_id for event in event_store.actionable_pending_review_events()] == [next_event.event_id]


def test_status_exposes_one_current_step_and_actionable_review_queue(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    current = task_event("event-task-status-001", objective="Manage one task")
    event_store.record(current)

    result = state_manager_main(
        ["--root", str(tmp_path), "--policy", str(policy), "--schema", str(schema), "status", "--format", "json"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["task"]["objective"] == "Manage one task"
    assert payload["task"]["one_executable_step"] == "Run one read-only audit."
    assert payload["actionable_reviews"] == []


def test_status_surfaces_repository_review_without_active_task(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    current_task = tmp_path / "tasks/current_task.md"
    current_task.write_text(
        START_MARKER.format(block_id="current_task")
        + "\n# Current Task\n\nNo active task.\n"
        + END_MARKER.format(block_id="current_task")
        + "\n",
        encoding="utf-8",
    )
    candidate = tmp_path / "scratch/cache.txt"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("cache\n", encoding="utf-8")
    event = build_stale_item_event(
        project_root=tmp_path,
        path=candidate,
        disposition="delete",
        content_class="regenerable",
        reason="Delete a reproducible cache.",
        schema_path=schema,
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)

    payload = _control_status(tmp_path, policy, schema, tmp_path / "modules/state_handoff/events")

    assert payload["active"] is False
    assert payload["actionable_reviews"][0]["event_id"] == event.event_id


def test_sync_reuses_trusted_registry_excel_review_for_projection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    base_evidence_path = tmp_path / "docs" / "base.txt"
    base_evidence_path.write_text("base\n", encoding="utf-8")
    base = task_event("event-task-reuse-base-001", evidence=file_evidence(base_evidence_path, tmp_path))
    event_store.record(base)
    base_proposal = build_proposal(base, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=base_proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=base.event_id,
        reviewed_event_sha256=base.digest,
    )
    apply_proposal(
        base_proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
        safe_only=False,
    )

    workbook = tmp_path / "outputs" / "barrier.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"reviewed workbook")
    workbook_hash = sha256_file(workbook)
    receipt = tmp_path / "data" / "registry_promotion_receipts" / "barrier.json"
    receipt.parent.mkdir(parents=True)
    receipt_payload = {
        "registry_id": "barrier-001",
        "reviewer": "user",
        "reviewed_at": TIMESTAMP,
        "workbook_sha256_after": workbook_hash,
        "written_values_sha256": "b" * 64,
    }
    receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
    database = tmp_path / "data" / "project_registry.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE ts_validations (
                ts_validation_id TEXT PRIMARY KEY, grade TEXT, kinetic_eligible INTEGER
            );
            CREATE TABLE ts_barriers (
                barrier_set_id TEXT PRIMARY KEY, ts_validation_id TEXT, validation_status TEXT
            );
            CREATE TABLE excel_promotions (
                promotion_kind TEXT, registry_id TEXT, workbook_path TEXT,
                workbook_sha256_after TEXT, written_values_sha256 TEXT,
                reviewer TEXT, reviewed_at TEXT, receipt_path TEXT
            );
            """
        )
        connection.execute("INSERT INTO ts_validations VALUES ('validation-001', 'A', 1)")
        connection.execute("INSERT INTO ts_barriers VALUES ('barrier-001', 'validation-001', 'accepted')")
        connection.execute(
            "INSERT INTO excel_promotions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("barrier", "barrier-001", str(workbook), workbook_hash, "b" * 64, "user", TIMESTAMP, str(receipt)),
        )
    summary = tmp_path / "docs" / "registration_summary.json"
    summary.write_text(json.dumps({"status": "REGISTERED", "barrier_set_id": "barrier-001"}), encoding="utf-8")
    updated_payload = task_event(
        "event-task-reuse-update-002",
        evidence=[
            {
                "locator": summary.relative_to(tmp_path).as_posix(),
                "sha256": sha256_file(summary),
                "authority": "calculation_registry",
                "observed_at": TIMESTAMP,
            }
        ],
        supersedes=[base.event_id],
        objective="Registered reviewed barrier",
    ).payload
    updated_payload["review"] = {
        "required": True,
        "reason_codes": ["scientific_result_registration", "cross_module_change"],
        "status": "pending",
    }
    updated = StateEvent.from_mapping(updated_payload, schema_path=schema)
    event_store.record(updated)

    result = state_manager_main(
        ["--root", str(tmp_path), "--policy", str(policy), "--schema", str(schema), "sync", "--safe-only"]
    )
    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert output["pending_review"] == []
    assert "tasks/current_task.md" in output["applied"]
    assert event_store.event_decision(updated.event_id) == "approve"


def _concurrent_record_worker(
    root_text: str,
    schema_text: str,
    payload: dict[str, Any],
    start: multiprocessing.synchronize.Event,
) -> None:
    start.wait()
    root = Path(root_text)
    event_store = EventStore(
        events_dir=root / "modules/state_handoff/events",
        schema_path=Path(schema_text),
        project_root=root,
    )
    event_store.record(StateEvent.from_mapping(payload, schema_path=Path(schema_text)))


def test_concurrent_identical_event_writes_create_one_complete_file(tmp_path: Path) -> None:
    _, schema = init_repository(tmp_path)
    payload = task_event("event-task-concurrent-001").payload
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [
        context.Process(
            target=_concurrent_record_worker,
            args=(str(tmp_path), str(schema), payload, start),
        )
        for _ in range(3)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0
    path = tmp_path / "modules/state_handoff/events/event-task-concurrent-001.json"
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert list(path.parent.glob("*.tmp")) == []


def test_initial_task_adoption_requires_review_then_applies(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    current_task = tmp_path / "tasks/current_task.md"
    current_task.write_text("# Current Task\n\nLegacy unmanaged task.\n", encoding="utf-8")
    event = task_event("event-task-adopt-001")
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)

    assert proposal["review_required"] is True
    assert "initial_managed_view_adoption" in proposal["actions"][0]["reason_codes"]
    with pytest.raises(ReviewRequired):
        apply_proposal(
            proposal,
            event_store=event_store,
            project_root=tmp_path,
            policy_path=policy,
            safe_only=True,
        )
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
    )
    changed = apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )

    assert "tasks/current_task.md" in changed
    text = current_task.read_text(encoding="utf-8")
    assert START_MARKER.format(block_id="current_task") in text
    assert "Keep 状态 current" in text
    assert build_proposal(event, project_root=tmp_path, policy_path=policy)["actions"] == []


def test_task_lifecycle_requires_verification_before_acceptance(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    current_task = tmp_path / "tasks/current_task.md"
    current_task.write_text("# Current Task\n\nLegacy unmanaged task.\n", encoding="utf-8")
    task = task_event("event-task-lifecycle-001", phase="active")
    event_store = store(tmp_path, schema)
    event_store.record(task)
    adoption = build_proposal(task, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=adoption["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=task.event_id,
        reviewed_event_sha256=task.digest,
    )
    apply_proposal(adoption, event_store=event_store, project_root=tmp_path, policy_path=policy)
    evidence = tmp_path / "verification.log"
    evidence.write_text("verification evidence\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    premature = task_acceptance_event(
        task,
        validation_evidence=evidence,
        artifact=artifact,
        root=tmp_path,
    )
    with pytest.raises(ValueError, match="requires current phase verification"):
        event_store.record(premature)

    transition = build_task_transition_event(
        event_store=event_store,
        to_phase="verification",
        reason="Done When evidence is ready.",
        evidence_paths=[evidence],
        schema_path=schema,
        policy_path=policy,
    )
    event_store.record(transition)
    proposal = build_proposal(transition, project_root=tmp_path, policy_path=policy)
    assert proposal["review_required"] is False
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
        safe_only=True,
    )
    assert "Phase: `verification`" in current_task.read_text(encoding="utf-8")


def test_stale_item_command_builds_reviewed_exact_file_proposal(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    candidate = tmp_path / "obsolete-cache.txt"
    candidate.write_text("regenerable cache\n", encoding="utf-8")
    event = build_stale_item_event(
        project_root=tmp_path,
        path=candidate,
        disposition="delete",
        content_class="regenerable",
        reason="The cache is reproducible and no longer referenced.",
        schema_path=schema,
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)

    assert proposal["review_required"] is True
    assert proposal["actions"][0]["action_type"] == "delete_file"
    assert proposal["actions"][0]["target_path"] == "obsolete-cache.txt"
    with pytest.raises(ReviewRequired):
        apply_proposal(
            proposal,
            event_store=event_store,
            project_root=tmp_path,
            policy_path=policy,
            safe_only=True,
        )
    assert candidate.is_file()

    directory = tmp_path / "old-directory"
    directory.mkdir()
    with pytest.raises(ValueError, match="exact files only"):
        build_stale_item_event(
            project_root=tmp_path,
            path=directory,
            disposition="keep",
            content_class="unique",
            reason="Directory classification remains audit-only.",
            schema_path=schema,
        )


def test_batch_cleanup_proposal_binds_archive_delete_and_move_files(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    unique = tmp_path / "legacy/说明.txt"
    cache = tmp_path / "scratch/cache.txt"
    scientific = tmp_path / ".codex_tmp/job/CONTCAR"
    unique.parent.mkdir(parents=True)
    cache.parent.mkdir(parents=True)
    scientific.parent.mkdir(parents=True)
    unique.write_text("unique\n", encoding="utf-8")
    cache.write_text("cache\n", encoding="utf-8")
    scientific.write_text("structure\n", encoding="utf-8")
    manifest = tmp_path / "cleanup.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "repository_cleanup_manifest",
                "bundle_id": "cleanup-test-bundle",
                "reason": "Test one exact reviewed cleanup bundle.",
                "items": [
                    {"path": "legacy/说明.txt", "disposition": "archive", "content_class": "unique", "reason": "Preserve unique source."},
                    {"path": "scratch/cache.txt", "disposition": "delete", "content_class": "regenerable", "reason": "Delete reproducible cache."},
                    {"path": ".codex_tmp/job/CONTCAR", "target_path": "calculations/recovered/job/CONTCAR", "disposition": "move", "content_class": "unique", "reason": "Move unique scientific evidence."},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    event = build_stale_item_batch_event(
        project_root=tmp_path,
        manifest_path=manifest,
        schema_path=schema,
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)

    assert proposal["review_required"] is True
    assert [action["action_type"] for action in proposal["actions"]] == [
        "archive_file", "delete_file", "move_file", "write_text"
    ]
    assert all(
        action.get("source_expected_sha256")
        for action in proposal["actions"]
        if action["action_type"] in {"archive_file", "move_file"}
    )
    with pytest.raises(ReviewRequired):
        apply_proposal(proposal, event_store=event_store, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
    )
    apply_proposal(proposal, event_store=event_store, project_root=tmp_path, policy_path=policy)
    assert build_proposal(event, project_root=tmp_path, policy_path=policy)["actions"] == []

    date = str(event.payload["occurred_at"])[:10]
    archive = tmp_path / f"modules/state_handoff/archive/{date}/{event.event_id}/legacy/说明.txt"
    assert archive.read_text(encoding="utf-8") == "unique\n"
    assert not cache.exists()
    moved = tmp_path / "calculations/recovered/job/CONTCAR"
    assert moved.read_text(encoding="utf-8") == "structure\n"
    bundle_manifest = archive.parents[1] / "bundle_manifest.json"
    assert json.loads(bundle_manifest.read_text(encoding="utf-8"))["event_id"] == event.event_id


def test_safe_state_projection_preserves_history_and_is_idempotent(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    evidence_path = tmp_path / "evidence.txt"
    evidence_path.write_text("scheduler snapshot\n", encoding="utf-8")
    current_state = tmp_path / "docs/02_CURRENT_STATE.md"
    payload = event_payload(
        "event-state-gate-001",
        "state_observed",
        "state",
        "transition-current-gate",
        {
            "block_id": "transition-current-gate",
            "section": "## Active TS",
            "title": "Current Gate — 2026-08-02",
            "facts": ["Job `9654834` was `RUN` at the recorded checkpoint."],
            "next_action": "Monitor through the owning module.",
        },
        evidence=file_evidence(evidence_path, tmp_path),
    )
    event = StateEvent.from_mapping(payload)
    initial_block = render_state_block(event)
    current_state.write_text(
        "# Current State\n\n## Active TS\n\n"
        + initial_block.replace("9654834", "9650000")
        + "\n\n### Historical Evidence\n\nHISTORICAL KEEP\n",
        encoding="utf-8",
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)

    assert proposal["review_required"] is False
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
        safe_only=True,
    )
    result = current_state.read_text(encoding="utf-8")
    assert "9654834" in result
    assert "HISTORICAL KEEP" in result
    assert build_proposal(event, project_root=tmp_path, policy_path=policy)["actions"] == []


def test_end_checkpoint_closes_task_only_after_complete_acceptance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    task, event_store = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    acceptance = task_acceptance_event(
        task,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
    )
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_text(
        json.dumps(acceptance.payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    checkpoint_result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "checkpoint",
            "--phase",
            "end",
            "--event",
            str(acceptance_path),
        ]
    )
    checkpoint_output = json.loads(capsys.readouterr().out)
    assert checkpoint_result == 0
    assert checkpoint_output["acceptance_event_id"] == acceptance.event_id
    assert checkpoint_output["review_required"] is False

    sync_result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "sync",
            "--safe-only",
        ]
    )
    sync_output = json.loads(capsys.readouterr().out)
    assert sync_result == 0
    assert sync_output["pending_review"] == []
    current_task_text = (tmp_path / "tasks/current_task.md").read_text(encoding="utf-8")
    assert "No active task" in current_task_text
    assert "`configs/execution_backends.yaml`" in current_task_text
    audit = audit_repository(project_root=tmp_path, policy_path=policy, phase="end")
    assert "current_task_step_count" not in {
        finding["code"] for finding in audit["findings"]
    }
    history_types = [event.event_type for event in event_store.history("task-current")]
    assert "task_acceptance_recorded" in history_types
    assert "task_completed" in history_types
    historical = (tmp_path / "docs/08_HISTORICAL_RESULTS.md").read_text(encoding="utf-8")
    assert "<!-- state-handoff:item history:task-completed-" in historical
    assert "The formal task acceptance passed." in historical


def test_task_completion_atomically_routes_structured_handoff_views(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    task, event_store = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed with reviewed handoff\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    evidence_hash = sha256_file(validation_log)
    acceptance = task_acceptance_event(
        task,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
        requires_user_review=True,
        risk_status="accepted_open_risks",
        handoff={
            "history": {
                "title": "State manager handoff accepted",
                "summary": "The task closed with structured routing.",
                "outcome": "All lifecycle views received their owned records.",
                "evidence_sha256": [evidence_hash],
            },
            "backlog_items": [
                {
                    "id": "B-STATE-001",
                    "priority": "P2",
                    "category": "Infrastructure",
                    "module": "state_handoff",
                    "summary": "Follow up the managed-view migration",
                    "next_action": "Review the next checkpoint.",
                    "done_when": "The migration has an accepted checkpoint.",
                    "evidence_sha256": [evidence_hash],
                }
            ],
            "errors": [
                {
                    "id": "E-STATE-001",
                    "summary": "One reviewed limitation remains",
                    "impact": "The limitation blocks automatic closure.",
                    "next_action": "Resolve it in the owning task.",
                    "owner": "state_handoff",
                    "evidence_sha256": [evidence_hash],
                }
            ],
            "decisions": [
                {
                    "id": "D-STATE-001",
                    "title": "Use structured task handoff",
                    "decision": "Project accepted task output by record type.",
                    "reason": "This keeps current state compact.",
                    "consequence": "Future closure events own lifecycle routing.",
                    "evidence_sha256": [evidence_hash],
                }
            ],
        },
    )
    event_store.record(acceptance)
    completion = derive_task_completion_event(
        acceptance,
        event_store=event_store,
        schema_path=schema,
    )
    event_store.record(completion)
    proposal = build_proposal(completion, project_root=tmp_path, policy_path=policy)

    assert proposal["review_required"] is True
    targets = {action["target_path"] for action in proposal["actions"]}
    assert {
        "tasks/current_task.md",
        "tasks/backlog.md",
        "docs/04_ERROR_LOG.md",
        "docs/03_DECISIONS_LOG.md",
        "docs/08_HISTORICAL_RESULTS.md",
        "data/state_handoff/projection_manifest.json",
    } <= targets
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=completion.event_id,
        reviewed_event_sha256=completion.digest,
    )
    changed = apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )

    assert len(changed) == 6
    assert "backlog:B-STATE-001" in (tmp_path / "tasks/backlog.md").read_text(encoding="utf-8")
    assert "error:E-STATE-001" in (tmp_path / "docs/04_ERROR_LOG.md").read_text(encoding="utf-8")
    assert "decision:D-STATE-001" in (tmp_path / "docs/03_DECISIONS_LOG.md").read_text(encoding="utf-8")
    assert f"history:{completion.event_id}" in (
        tmp_path / "docs/08_HISTORICAL_RESULTS.md"
    ).read_text(encoding="utf-8")
    assert build_proposal(completion, project_root=tmp_path, policy_path=policy)["actions"] == []


def test_handoff_decision_cannot_bypass_user_review(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    task, _ = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    digest = sha256_file(validation_log)

    with pytest.raises(ValueError, match="handoff decisions require user review"):
        task_acceptance_event(
            task,
            validation_evidence=validation_log,
            artifact=artifact,
            root=tmp_path,
            handoff={
                "history": {
                    "title": "Rejected handoff",
                    "summary": "A decision was not reviewed.",
                    "outcome": "Validation rejects the event.",
                    "evidence_sha256": [digest],
                },
                "backlog_items": [],
                "errors": [],
                "decisions": [
                    {
                        "id": "D-UNREVIEWED-001",
                        "title": "Unreviewed decision",
                        "decision": "Do not accept this.",
                        "reason": "It lacks review.",
                        "consequence": "The checkpoint is invalid.",
                        "evidence_sha256": [digest],
                    }
                ],
            },
        )


def test_first_lifecycle_view_adoption_preserves_legacy_and_requires_review(
    tmp_path: Path,
) -> None:
    policy, schema = init_repository(tmp_path)
    history_path = tmp_path / "docs/08_HISTORICAL_RESULTS.md"
    history_path.write_text("# Historical Results\n\nLEGACY MUST STAY\n", encoding="utf-8")
    task, event_store = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    acceptance = task_acceptance_event(
        task,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
    )
    event_store.record(acceptance)
    completion = derive_task_completion_event(
        acceptance,
        event_store=event_store,
        schema_path=schema,
    )
    event_store.record(completion)
    proposal = build_proposal(completion, project_root=tmp_path, policy_path=policy)
    history_action = next(
        action
        for action in proposal["actions"]
        if action["target_path"] == "docs/08_HISTORICAL_RESULTS.md"
    )

    assert history_action["requires_review"] is True
    assert "initial_managed_view_adoption" in history_action["reason_codes"]
    with pytest.raises(ReviewRequired):
        apply_proposal(
            proposal,
            event_store=event_store,
            project_root=tmp_path,
            policy_path=policy,
            safe_only=True,
        )
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=completion.event_id,
        reviewed_event_sha256=completion.digest,
    )
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )
    projected = history_path.read_text(encoding="utf-8")
    assert "LEGACY MUST STAY" in projected
    assert START_MARKER.format(block_id="task_history_events") in projected


def test_end_checkpoint_accepts_current_task_from_initial_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    task_path = tmp_path / "tasks/current_task.md"
    state_path = tmp_path / "docs/02_CURRENT_STATE.md"
    task_path.write_text(
        "# Current Task\n\n## Objective\n\nBaseline task.\n\n"
        "## One Executable Step\n\nRun validation.\n\n"
        "## Done When\n\n- Validation passes.\n",
        encoding="utf-8",
    )
    state_path.write_text(
        "# Current State\n\n## Active Workflow\n\n"
        "### Current Gate — 2026-08-02\n\n- Baseline task is active.\n",
        encoding="utf-8",
    )
    baseline = build_baseline_event(tmp_path)
    event_store = store(tmp_path, schema)
    event_store.record(baseline)
    baseline_proposal = build_proposal(
        baseline,
        project_root=tmp_path,
        policy_path=policy,
    )
    event_store.record_review(
        proposal_id=baseline_proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=baseline.event_id,
        reviewed_event_sha256=baseline.digest,
    )
    apply_proposal(
        baseline_proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )
    assert event_store.current_task_source().event_id == baseline.event_id

    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed\n", encoding="utf-8")
    transition = build_task_transition_event(
        event_store=event_store,
        to_phase="verification",
        reason="All Done When evidence is ready for formal acceptance.",
        evidence_paths=[validation_log],
        schema_path=schema,
        policy_path=policy,
    )
    event_store.record(transition)
    transition_proposal = build_proposal(
        transition,
        project_root=tmp_path,
        policy_path=policy,
    )
    apply_proposal(
        transition_proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
        safe_only=True,
    )
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    acceptance = task_acceptance_event(
        transition,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
    )
    acceptance_path = tmp_path / "baseline-acceptance.json"
    acceptance_path.write_text(
        json.dumps(acceptance.payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert (
        state_manager_main(
            [
                "--root",
                str(tmp_path),
                "--policy",
                str(policy),
                "--schema",
                str(schema),
                "checkpoint",
                "--phase",
                "end",
                "--event",
                str(acceptance_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        state_manager_main(
            [
                "--root",
                str(tmp_path),
                "--policy",
                str(policy),
                "--schema",
                str(schema),
                "sync",
                "--safe-only",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert "No active task" in task_path.read_text(encoding="utf-8")
    assert baseline.event_id in {
        event.event_id for event in event_store.effective_events()
    }
    assert event_store.current_task_source() is None


def test_end_checkpoint_rejects_incomplete_done_when_coverage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    task, event_store = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    acceptance = task_acceptance_event(
        task,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
    )
    payload = json.loads(json.dumps(acceptance.payload))
    payload["payload"]["done_when_results"][0]["criterion"] = "Different criterion"
    acceptance_path = tmp_path / "acceptance-invalid.json"
    acceptance_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "checkpoint",
            "--phase",
            "end",
            "--event",
            str(acceptance_path),
        ]
    )
    error = capsys.readouterr().err
    assert result == 2
    assert "cover every Done When criterion" in error
    assert all(
        event.event_type not in {"task_acceptance_recorded", "task_completed"}
        for event in event_store.load_all()
    )


def test_acceptance_rejects_artifact_without_exact_path_hash_evidence(
    tmp_path: Path,
) -> None:
    policy, schema = init_repository(tmp_path)
    task, _ = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    acceptance = task_acceptance_event(
        task,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
    )
    payload = json.loads(json.dumps(acceptance.payload))
    payload["payload"]["artifacts"][0]["path"] = "different-result.json"

    with pytest.raises(ValueError, match="exact path-and-hash evidence"):
        StateEvent.from_mapping(payload, schema_path=schema)


def test_end_checkpoint_with_accepted_risk_requires_user_review(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    task, _ = adopt_current_task(tmp_path, policy, schema)
    validation_log = tmp_path / "validation.log"
    validation_log.write_text("1 passed with reviewed risk\n", encoding="utf-8")
    artifact = tmp_path / "result.json"
    artifact.write_text('{"status":"verified"}\n', encoding="utf-8")
    acceptance = task_acceptance_event(
        task,
        validation_evidence=validation_log,
        artifact=artifact,
        root=tmp_path,
        requires_user_review=True,
        risk_status="accepted_open_risks",
    )
    acceptance_path = tmp_path / "acceptance-review.json"
    acceptance_path.write_text(
        json.dumps(acceptance.payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    checkpoint_result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "checkpoint",
            "--phase",
            "end",
            "--event",
            str(acceptance_path),
        ]
    )
    checkpoint_output = json.loads(capsys.readouterr().out)
    assert checkpoint_result == 1
    assert checkpoint_output["review_required"] is True
    assert "No active task" not in (tmp_path / "tasks/current_task.md").read_text(
        encoding="utf-8"
    )

    sync_result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "sync",
            "--safe-only",
        ]
    )
    sync_output = json.loads(capsys.readouterr().out)
    assert sync_result == 1
    assert sync_output["pending_review"][0]["proposal_id"] == checkpoint_output["proposal_id"]


def test_task_completed_cannot_bypass_formal_acceptance(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    task, event_store = adopt_current_task(tmp_path, policy, schema)
    completion = StateEvent.from_mapping(
        event_payload(
            "event-task-completed-bypass-001",
            "task_completed",
            "task",
            "task-current",
            {
                "completion_summary": "Attempted direct closure.",
                "task_event_id": task.event_id,
                "task_event_sha256": task.digest,
                "acceptance_event_id": "event-acceptance-missing-001",
                "acceptance_event_sha256": "0" * 64,
                "handoff": {
                    "history": {
                        "title": "Attempted closure",
                        "summary": "Direct closure must fail.",
                        "outcome": "Rejected.",
                        "evidence_sha256": ["0" * 64],
                    },
                    "backlog_items": [],
                    "errors": [],
                    "decisions": [],
                },
            },
            supersedes=[task.event_id],
        ),
        schema_path=schema,
    )

    with pytest.raises(FileNotFoundError, match="unknown state event"):
        event_store.record(completion)


def test_module_map_audits_only_owned_row_but_apply_checks_whole_file(
    tmp_path: Path,
) -> None:
    policy, schema = init_repository(tmp_path)
    module_map = tmp_path / "docs/06_MODULE_MAP.md"
    original = (
        "| Module | Status | Depends on | Current gate |\n"
        "|---|---|---|---|\n"
        "| `transition_state_search` | Active | VASP | Old gate |\n"
        "| `adsorption_workflow` | Planned | retrieval | Waiting |\n"
    )
    module_map.write_text(original, encoding="utf-8")
    evidence_path = tmp_path / "module-evidence.txt"
    evidence_path.write_text("reviewed module evidence\n", encoding="utf-8")
    event = StateEvent.from_mapping(
        event_payload(
            "event-module-row-scope-001",
            "module_gate_changed",
            "module",
            "transition_state_search",
            {
                "module": "transition_state_search",
                "status": "Active",
                "depends_on": "VASP",
                "current_gate": "New reviewed gate",
            },
            evidence=file_evidence(evidence_path, tmp_path),
            review_required=True,
        ),
        schema_path=schema,
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=event.event_id,
        reviewed_event_sha256=event.digest,
    )

    module_map.write_text(
        original.replace("`adsorption_workflow` | Planned", "`adsorption_workflow` | Active"),
        encoding="utf-8",
    )
    with pytest.raises(StaleProposal, match="proposal target changed"):
        apply_proposal(
            proposal,
            event_store=event_store,
            project_root=tmp_path,
            policy_path=policy,
        )

    module_map.write_text(original, encoding="utf-8")
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )
    manifest = json.loads(
        (tmp_path / "data/state_handoff/projection_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    projection_key = "docs/06_MODULE_MAP.md#module_row:transition_state_search"
    assert manifest["projections"][projection_key]["managed_unit"] == {
        "kind": "module_row",
        "id": "transition_state_search",
    }
    assert "docs/06_MODULE_MAP.md" not in manifest["projections"]

    projected = module_map.read_text(encoding="utf-8")
    module_map.write_text(
        projected.replace("`adsorption_workflow` | Planned", "`adsorption_workflow` | Active"),
        encoding="utf-8",
    )
    unrelated_report = audit_repository(project_root=tmp_path, policy_path=policy)
    assert "managed_projection_drift" not in {
        finding["code"] for finding in unrelated_report["findings"]
    }

    module_map.write_text(
        module_map.read_text(encoding="utf-8").replace(
            "New reviewed gate", "Manually changed gate"
        ),
        encoding="utf-8",
    )
    owned_report = audit_repository(project_root=tmp_path, policy_path=policy)
    assert "managed_projection_drift" in {
        finding["code"] for finding in owned_report["findings"]
    }


def test_apply_rejects_target_changed_after_proposal(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    evidence_path = tmp_path / "evidence.txt"
    evidence_path.write_text("source\n", encoding="utf-8")
    current_task = tmp_path / "tasks/current_task.md"
    current_task.write_text(
        START_MARKER.format(block_id="current_task")
        + "\n# Current Task\n\nOld\n"
        + END_MARKER.format(block_id="current_task")
        + "\n",
        encoding="utf-8",
    )
    event = task_event(
        "event-task-stale-001",
        evidence=file_evidence(evidence_path, tmp_path),
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    current_task.write_text(current_task.read_text(encoding="utf-8") + "manual change\n", encoding="utf-8")

    with pytest.raises(StaleProposal, match="changed after proposal"):
        apply_proposal(
            proposal,
            event_store=event_store,
            project_root=tmp_path,
            policy_path=policy,
            safe_only=True,
        )


def test_unique_untracked_archive_requires_approval_and_preserves_manifest(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    source = tmp_path / "旧说明.txt"
    source.write_text("unique 内容\n", encoding="utf-8")
    payload = event_payload(
        "event-repo-archive-001",
        "repository_item_classified",
        "repository_item",
        "legacy-note",
        {
            "path": "旧说明.txt",
            "disposition": "archive",
            "tracking_status": "untracked",
            "content_class": "unique",
        },
        evidence=file_evidence(source, tmp_path),
        review_required=True,
    )
    event = StateEvent.from_mapping(payload)
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    with pytest.raises(ReviewRequired):
        apply_proposal(proposal, event_store=event_store, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
    )
    apply_proposal(proposal, event_store=event_store, project_root=tmp_path, policy_path=policy)

    target = tmp_path / "modules/state_handoff/archive/2026-08-02/event-repo-archive-001/旧说明.txt"
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "unique 内容\n"
    manifest = json.loads((target.parent / "archive_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == sha256_file(target)
    assert manifest["proposal_id"] == proposal["proposal_id"]


def test_calculation_file_cannot_be_deleted_even_after_approval(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    source = tmp_path / "calculations/case/temporary.txt"
    source.parent.mkdir(parents=True)
    source.write_text("calculation evidence\n", encoding="utf-8")
    event = StateEvent.from_mapping(
        event_payload(
            "event-repo-delete-001",
            "repository_item_classified",
            "repository_item",
            "calculation-file",
            {
                "path": "calculations/case/temporary.txt",
                "disposition": "delete",
                "tracking_status": "untracked",
                "content_class": "regenerable",
            },
            evidence=file_evidence(source, tmp_path),
            review_required=True,
        )
    )
    event_store = store(tmp_path, schema)
    event_store.record(event)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
    )
    with pytest.raises(ValueError, match="forbidden under calculations"):
        apply_proposal(proposal, event_store=event_store, project_root=tmp_path, policy_path=policy)
    assert source.exists()


def test_read_only_audit_detects_known_repository_drift(tmp_path: Path) -> None:
    policy, _ = init_repository(tmp_path, include_module=False)
    (tmp_path / "tasks/current_task.md").write_text(
        "# Current Task\n\n## One Executable Step\n\n"
        "Monitor job `9654834`.\n\n## Authoritative References\n\n"
        "- modules/transition_state_search/README.md\n",
        encoding="utf-8",
    )
    overloaded = "\n".join(f"- historical checkpoint {index}" for index in range(205))
    (tmp_path / "docs/02_CURRENT_STATE.md").write_text(
        "# Current State\n\nState updated: 2026-07-27 CST.\n\n"
        "## Active TS\n\n### Current Gate — 2026-08-02 Evidence Snapshot\n\n"
        "- Job `9654834` was `RUN`.\n\n## Historical Flow\n\n"
        + overloaded
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/06_MODULE_MAP.md").write_text(
        "| Module | Status | Depends on | Current gate |\n"
        "|---|---|---|---|\n"
        "| `transition_state_search` | Active | VASP | Old job `9654240` was `RUN` |\n",
        encoding="utf-8",
    )
    for relative in ("tasks/backlog.md", "docs/03_DECISIONS_LOG.md", "docs/08_HISTORICAL_RESULTS.md"):
        (tmp_path / relative).write_text("# Placeholder\n", encoding="utf-8")
    (tmp_path / "docs/04_ERROR_LOG.md").write_text(
        "# Error Log\n\nJob `9654834` is scheduler `EXIT`.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".codex_tmp").mkdir()
    (tmp_path / ".codex_tmp/cache.txt").write_text("cache\n", encoding="utf-8")

    report = audit_repository(project_root=tmp_path, policy_path=policy)
    codes = {finding["code"] for finding in report["findings"]}

    assert {
        "state_handoff_module_missing",
        "current_task_unmanaged",
        "current_state_header_stale",
        "duplicate_or_historical_overload",
        "module_gate_stale",
        "current_status_conflict",
        "unexpected_root_item",
    } <= codes


def test_status_audit_ignores_conditional_next_actions() -> None:
    text = (
        "The same-path pilot was submitted as job `9654860` under a reviewed path. "
        "It was scheduler `RUN` at the recorded checkpoint.\n\n"
        "Monitor job `9654860` to terminal state. If it is `DONE`, inspect outputs; "
        "if it is `PEND` or `RUN`, wait; if it is `EXIT`, preserve evidence."
    )

    assert _latest_status_mentions(text) == {"9654860": "RUN"}


def test_event_supersession_leaves_one_effective_entity(tmp_path: Path) -> None:
    _, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    first = task_event("event-task-chain-001")
    second = task_event(
        "event-task-chain-002",
        supersedes=[first.event_id],
        objective="Updated objective",
    )
    event_store.record(first)
    event_store.record(second)

    latest = event_store.latest_by_entity()
    assert latest[("task", "task-current")].event_id == second.event_id
    assert [event.event_id for event in event_store.history("task-current")] == [
        first.event_id,
        second.event_id,
    ]


def test_entity_reconciliation_supersedes_all_conflicting_effective_events(
    tmp_path: Path,
) -> None:
    _, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    first = task_event("event-task-conflict-001", objective="Older task state")
    second = task_event("event-task-conflict-002", objective="Approved current task state")
    event_store.record(first)
    event_store.record(second)

    reconciled = build_entity_reconciliation_event(
        event_store=event_store,
        entity_kind="task",
        entity_id="task-current",
        keep_event_id=second.event_id,
    )
    repeated = build_entity_reconciliation_event(
        event_store=event_store,
        entity_kind="task",
        entity_id="task-current",
        keep_event_id=second.event_id,
    )
    assert repeated.payload == reconciled.payload
    assert reconciled.payload["supersedes"] == [first.event_id, second.event_id]
    event_store.record(reconciled)

    latest = event_store.latest_by_entity()
    assert latest[("task", "task-current")].event_id == reconciled.event_id
    assert reconciled.payload["payload"]["objective"] == "Approved current task state"


def test_entity_reconciliation_can_refresh_user_approved_local_evidence(tmp_path: Path) -> None:
    _, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)
    evidence_path = tmp_path / "docs" / "evidence.json"
    evidence_path.write_text('{"state":"first"}\n', encoding="utf-8")
    evidence = file_evidence(evidence_path, tmp_path)
    first = task_event("event-task-refresh-001", evidence=evidence)
    second = task_event("event-task-refresh-002", evidence=evidence, objective="Keep approved state")
    event_store.record(first)
    event_store.record(second)
    evidence_path.write_text('{"state":"current"}\n', encoding="utf-8")

    refreshed = build_entity_reconciliation_event(
        event_store=event_store,
        entity_kind="task",
        entity_id="task-current",
        keep_event_id=second.event_id,
        refresh_evidence=True,
    )

    assert refreshed.event_id != second.event_id
    assert refreshed.payload["evidence"][0]["sha256"] == sha256_file(evidence_path)
    event_store.record(refreshed)


def test_rejected_event_is_historical_and_does_not_repeat_review(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy, schema = init_repository(tmp_path)
    current_task = tmp_path / "tasks/current_task.md"
    current_task.write_text("# Current Task\n\nLegacy unmanaged task.\n", encoding="utf-8")
    event_store = store(tmp_path, schema)

    accepted = task_event("event-task-reject-base-001")
    event_store.record(accepted)
    accepted_proposal = build_proposal(
        accepted,
        project_root=tmp_path,
        policy_path=policy,
    )
    event_store.record_review(
        proposal_id=accepted_proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=accepted.event_id,
        reviewed_event_sha256=accepted.digest,
    )
    apply_proposal(
        accepted_proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )

    rejected_payload = task_event(
        "event-task-reject-new-001",
        supersedes=[accepted.event_id],
        objective="Rejected replacement",
    ).payload
    rejected_payload["review"] = {
        "required": True,
        "reason_codes": ["user_review"],
        "status": "pending",
    }
    rejected = StateEvent.from_mapping(rejected_payload, schema_path=schema)
    event_store.record(rejected)
    rejected_proposal = build_proposal(
        rejected,
        project_root=tmp_path,
        policy_path=policy,
    )
    ProposalStore(tmp_path, policy).save(rejected_proposal)
    review_result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "review",
            "--proposal",
            rejected_proposal["proposal_id"],
            "--decision",
            "reject",
        ]
    )
    assert review_result == 0
    capsys.readouterr()

    assert event_store.event_decision(rejected.event_id) == "reject"
    assert event_store.latest_by_entity()[("task", "task-current")].event_id == accepted.event_id
    assert rejected.event_id in {
        event.event_id for event in event_store.history("task-current")
    }

    result = state_manager_main(
        [
            "--root",
            str(tmp_path),
            "--policy",
            str(policy),
            "--schema",
            str(schema),
            "sync",
            "--safe-only",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output == {"applied": [], "pending_review": []}


def test_reject_review_requires_hash_bound_event_linkage(tmp_path: Path) -> None:
    _, schema = init_repository(tmp_path)
    event_store = store(tmp_path, schema)

    with pytest.raises(ValueError, match="requires reviewed event linkage"):
        event_store.record_review(
            proposal_id="proposal-unlinked-reject",
            decision="reject",
            reviewer="user",
        )


def test_baseline_preview_is_stable_and_adopts_only_current_views(tmp_path: Path) -> None:
    policy, schema = init_repository(tmp_path)
    task = tmp_path / "tasks/current_task.md"
    state = tmp_path / "docs/02_CURRENT_STATE.md"
    task.write_text(
        "# Current Task\n\n## Objective\n\nManage state.\n\n"
        "## Current Evidence Snapshot\n\n- Evidence one.\n\n"
        "## One Executable Step\n\nRun audit.\n\n"
        "## Submission Boundary\n\n"
        "Do not submit calculations.\nPreserve this exact boundary text.\n\n"
        "## Done When\n\n- Audit is reviewed.\n\n"
        "## Authoritative References\n\n- configs/state_handoff.yaml\n",
        encoding="utf-8",
    )
    state.write_text(
        "# Current State\n\n## Active Workflow\n\n"
        "### Current Gate — 2026-08-02 Evidence Snapshot\n\n"
        "- Job `9654834` was `RUN`.\n"
        "- Retry remains blocked.\n\n"
        "### Historical Evidence\n\nHISTORY MUST STAY\n",
        encoding="utf-8",
    )
    before = {task: sha256_file(task), state: sha256_file(state)}
    first = build_baseline_event(tmp_path)
    second = build_baseline_event(tmp_path)

    assert first.event_id == second.event_id
    assert first.digest == second.digest
    assert first.payload["payload"]["task"]["submission_boundary"] == (
        "Do not submit calculations.\nPreserve this exact boundary text."
    )
    assert {path: sha256_file(path) for path in before} == before
    proposal = build_proposal(first, project_root=tmp_path, policy_path=policy)
    assert proposal["review_required"] is True
    assert {action["target_path"] for action in proposal["actions"]} == {
        "tasks/current_task.md",
        "docs/02_CURRENT_STATE.md",
        "data/state_handoff/projection_manifest.json",
    }

    event_store = store(tmp_path, schema)
    event_store.record(first)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
    )
    apply_proposal(proposal, event_store=event_store, project_root=tmp_path, policy_path=policy)

    projected_task = task.read_text(encoding="utf-8")
    assert START_MARKER.format(block_id="current_task") in projected_task
    assert (
        "## Submission Boundary\n\n"
        "Do not submit calculations.\nPreserve this exact boundary text."
    ) in projected_task
    assert "state-handoff:start active-workflow-current-gate" in state.read_text(encoding="utf-8")
    assert "HISTORY MUST STAY" in state.read_text(encoding="utf-8")
    assert build_proposal(first, project_root=tmp_path, policy_path=policy)["actions"] == []


def test_lifecycle_view_adoption_preserves_legacy_content_and_is_idempotent(
    tmp_path: Path,
) -> None:
    policy, schema = init_repository(tmp_path)
    targets = {
        "tasks/backlog.md": "task_backlog_events",
        "docs/04_ERROR_LOG.md": "task_error_events",
        "docs/03_DECISIONS_LOG.md": "task_decision_events",
        "docs/08_HISTORICAL_RESULTS.md": "task_history_events",
    }
    for relative in targets:
        (tmp_path / relative).write_text(
            f"# Legacy view\n\nLEGACY CONTENT: {relative}\n",
            encoding="utf-8",
        )

    event = build_lifecycle_views_adoption_event(tmp_path, policy)
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    assert proposal["review_required"] is True
    assert {action["target_path"] for action in proposal["actions"]} == {
        *targets,
        "data/state_handoff/projection_manifest.json",
    }

    event_store = store(tmp_path, schema)
    event_store.record(event)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=event.event_id,
        reviewed_event_sha256=event.digest,
    )
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )

    for relative, block_id in targets.items():
        text = (tmp_path / relative).read_text(encoding="utf-8")
        assert f"LEGACY CONTENT: {relative}" in text
        assert START_MARKER.format(block_id=block_id) in text
        assert END_MARKER.format(block_id=block_id) in text
    assert build_proposal(event, project_root=tmp_path, policy_path=policy)["actions"] == []


def test_state_history_compaction_archives_exact_history_and_is_idempotent(
    tmp_path: Path,
) -> None:
    policy, schema = init_repository(tmp_path)
    state = tmp_path / "docs/02_CURRENT_STATE.md"
    history_lines = [f"- Historical observation {index}" for index in range(250)]
    history = "### Historical Evidence\n\n" + "\n".join(history_lines) + "\n"
    state.write_text(
        "# Current State\n\n"
        "## Active Fe(110) CO Dissociation Test\n\n"
        "<!-- state-handoff:start active-fe-current-gate -->\n"
        "### Current Gate — 2026-08-03 Evidence Snapshot\n\n"
        "- Current fact remains.\n"
        "<!-- state-handoff:end active-fe-current-gate -->\n\n"
        f"{history}\n"
        "## Another Current Section\n\n- Keep this.\n",
        encoding="utf-8",
    )
    archive_relative = "docs/history/active_fe110_co_history_through_20260803.md"
    event = build_state_history_compaction_event(
        project_root=tmp_path,
        section_heading="## Active Fe(110) CO Dissociation Test",
        archive_path=archive_relative,
    )
    proposal = build_proposal(event, project_root=tmp_path, policy_path=policy)
    assert proposal["review_required"] is True
    assert {action["target_path"] for action in proposal["actions"]} == {
        "docs/02_CURRENT_STATE.md",
        archive_relative,
    }

    event_store = store(tmp_path, schema)
    event_store.record(event)
    event_store.record_review(
        proposal_id=proposal["proposal_id"],
        decision="approve",
        reviewer="user",
        reviewed_event_id=event.event_id,
        reviewed_event_sha256=event.digest,
    )
    apply_proposal(
        proposal,
        event_store=event_store,
        project_root=tmp_path,
        policy_path=policy,
    )

    compacted = state.read_text(encoding="utf-8")
    archived = (tmp_path / archive_relative).read_text(encoding="utf-8")
    assert history.rstrip() in archived
    assert "Historical observation 249" not in compacted
    assert "Current fact remains." in compacted
    assert "## Another Current Section" in compacted
    assert build_proposal(event, project_root=tmp_path, policy_path=policy)["actions"] == []
