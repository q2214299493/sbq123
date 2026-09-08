from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .audit import audit_repository
from .baseline import build_baseline_event
from .checkpoints import derive_task_completion_event
from .lifecycle import build_task_transition_event, effective_phase
from .lifecycle_views import build_lifecycle_views_adoption_event
from .imports import build_current_gate_import, build_current_task_import
from .models import ROOT, StateEvent
from .proposals import (
    ProposalStore,
    ReviewRequired,
    StaleProposal,
    apply_proposal,
    build_proposal,
)
from .reconciliation import build_entity_reconciliation_event
from .review_reuse import registry_excel_review_is_reusable
from .store import EventStore
from .stale_items import build_stale_item_batch_event, build_stale_item_event
from .state_compaction import build_state_history_compaction_event


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    root = Path(args.root).resolve()
    policy = Path(args.policy).resolve() if args.policy else root / "configs" / "state_handoff.yaml"
    schema = Path(args.schema).resolve() if args.schema else root / "configs" / "state_handoff_event.schema.json"
    import yaml

    config = yaml.safe_load(policy.read_text(encoding="utf-8"))
    events = root / config["paths"]["events"]
    return root, policy, schema, events


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="repo-state",
        description="Evidence-bound repository task, history, and stale-item manager.",
    )
    root.add_argument("--root", default=str(ROOT), help="Repository root.")
    root.add_argument("--policy", help="State-handoff YAML policy.")
    root.add_argument("--schema", help="State-event JSON schema.")
    commands = root.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="Read-only repository-state audit.")
    audit.add_argument("--phase", choices=("start", "end"), default="start")
    audit.add_argument("--format", choices=("text", "json"), default="text")
    audit.add_argument("--strict", action="store_true", help="Return 1 for any finding.")

    propose = commands.add_parser("propose", help="Record an event and cache its hash-bound proposal.")
    propose.add_argument("--event", type=Path, required=True)

    baseline = commands.add_parser("baseline", help="Preview or record one initial managed-view adoption proposal.")
    baseline.add_argument("--record", action="store_true", help="Record the pending event and cache the proposal.")

    adopt_views = commands.add_parser(
        "adopt-lifecycle-views",
        help="Preview or record first adoption of the four lifecycle views.",
    )
    adopt_views.add_argument("--record", action="store_true")

    compact_state = commands.add_parser(
        "compact-current-state",
        help="Preview or record a reviewed historical-section compaction.",
    )
    compact_state.add_argument("--section", required=True)
    compact_state.add_argument("--archive", required=True)
    compact_state.add_argument("--record", action="store_true")

    reconcile_entity = commands.add_parser(
        "reconcile-entity",
        help="Reconcile one conflicting entity chain without rewriting old events.",
    )
    reconcile_entity.add_argument("--kind", required=True)
    reconcile_entity.add_argument("--entity", required=True)
    reconcile_entity.add_argument("--keep", required=True)
    reconcile_entity.add_argument(
        "--refresh-evidence",
        action="store_true",
        help="Bind the reconciliation to the current hashes of its local authoritative evidence.",
    )
    reconcile_entity.add_argument("--record", action="store_true")

    sync = commands.add_parser("sync", help="Project effective events into managed views.")
    sync.add_argument("--safe-only", action="store_true", default=False)

    status = commands.add_parser(
        "status",
        help="Show one operational view of the current task, quality gate, history, and actionable reviews.",
    )
    status.add_argument("--format", choices=("text", "json"), default="text")

    checkpoint = commands.add_parser(
        "checkpoint",
        help="Record a formal task-end acceptance and create its closure proposal.",
    )
    checkpoint.add_argument("--phase", choices=("end",), required=True)
    checkpoint.add_argument("--event", type=Path, required=True)

    task = commands.add_parser("task", help="Inspect or transition the current task lifecycle.")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_commands.add_parser("status", help="Show the effective task phase and source event.")
    transition = task_commands.add_parser("transition", help="Record a validated task phase transition.")
    transition.add_argument("--to", choices=("open", "active", "blocked", "verification"), required=True)
    transition.add_argument("--reason", required=True)
    transition.add_argument("--evidence", type=Path, action="append", required=True)
    transition.add_argument("--apply-safe", action="store_true")

    stale_item = commands.add_parser("stale-item", help="Classify one exact stale repository file.")
    stale_commands = stale_item.add_subparsers(dest="stale_command", required=True)
    classify = stale_commands.add_parser("classify", help="Create a reviewed keep/archive/delete proposal.")
    classify.add_argument("--path", type=Path, required=True)
    classify.add_argument("--disposition", choices=("keep", "archive", "delete"), required=True)
    classify.add_argument("--content-class", choices=("unique", "regenerable", "duplicate"), required=True)
    classify.add_argument("--reason", required=True)
    classify_batch = stale_commands.add_parser(
        "classify-batch",
        help="Create one reviewed proposal from an exact path/hash cleanup manifest.",
    )
    classify_batch.add_argument("--manifest", type=Path, required=True)

    reconcile = commands.add_parser(
        "reconcile-current",
        help="Create reviewed imports for the existing current task and Current Gate.",
    )
    reconcile.add_argument("--record", action="store_true")

    review = commands.add_parser("review", help="Record an immutable user review decision.")
    review.add_argument("--proposal", required=True)
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reviewer", default="user")
    review.add_argument("--reason", default="")

    apply = commands.add_parser("apply", help="Apply one approved or review-free proposal.")
    apply.add_argument("--proposal", required=True)
    apply.add_argument("--safe-only", action="store_true")

    history = commands.add_parser("history", help="Show immutable history for one entity.")
    history.add_argument("--entity", required=True)
    return root


def _text_audit(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        f"phase={report['phase']} errors={counts['error']} warnings={counts['warning']} review_required={counts['review_required']}"
    ]
    for finding in report["findings"]:
        paths = f" [{', '.join(finding['paths'])}]" if finding["paths"] else ""
        lines.append(f"{finding['severity'].upper()} {finding['code']}: {finding['summary']}{paths}")
    return "\n".join(lines)


def _store(root: Path, schema: Path, events: Path) -> EventStore:
    return EventStore(events_dir=events, schema_path=schema, project_root=root)


def _audit(args: argparse.Namespace, root: Path, policy: Path) -> int:
    report = audit_repository(project_root=root, policy_path=policy, phase=args.phase)
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_text_audit(report))
    if args.strict and report["findings"]:
        return 1
    return 1 if report["counts"]["error"] else 0


def _propose(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    event = StateEvent.from_path(args.event, schema_path=schema)
    store = _store(root, schema, events)
    store.record(event)
    proposal = build_proposal(event, project_root=root, policy_path=policy)
    ProposalStore(root, policy).save(proposal)
    print(json.dumps(_proposal_summary(proposal), indent=2, ensure_ascii=False))
    return 1 if proposal["review_required"] else 0


def _proposal_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": proposal["proposal_id"],
        "event_id": proposal["event_id"],
        "event_sha256": proposal["event_sha256"],
        "review_required": proposal["review_required"],
        "actions": [
            {
                "action_type": action["action_type"],
                "target_path": action["target_path"],
                "expected_sha256": action.get("expected_sha256"),
                "new_content_sha256": (
                    hashlib.sha256(action["new_content"].encode("utf-8")).hexdigest()
                    if "new_content" in action
                    else None
                ),
                "requires_review": action["requires_review"],
                "reason_codes": action["reason_codes"],
            }
            for action in proposal["actions"]
        ],
        "review_questions": proposal["review_questions"],
    }


def _baseline(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    event = build_baseline_event(root)
    proposal = build_proposal(event, project_root=root, policy_path=policy)
    if args.record:
        _store(root, schema, events).record(event)
        ProposalStore(root, policy).save(proposal)
    summary = _proposal_summary(proposal)
    summary["recorded"] = bool(args.record)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1


def _reviewed_preview(
    event: StateEvent,
    *,
    record: bool,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    proposal = build_proposal(event, project_root=root, policy_path=policy)
    if record:
        _store(root, schema, events).record(event)
        ProposalStore(root, policy).save(proposal)
    summary = _proposal_summary(proposal)
    summary["recorded"] = record
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if proposal["review_required"] else 0


def _sync(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    store = _store(root, schema, events)
    proposal_store = ProposalStore(root, policy)
    applied: list[str] = []
    pending: list[dict[str, Any]] = []
    candidates = {
        event.event_id: event
        for event in (
            list(store.latest_by_entity().values()) + store.actionable_pending_review_events()
        )
    }
    effective = sorted(
        candidates.values(),
        key=lambda event: (event.payload["recorded_at"], event.event_id),
    )
    for event in effective:
        proposal = build_proposal(event, project_root=root, policy_path=policy)
        if not proposal["actions"]:
            continue
        proposal_store.save(proposal)
        if proposal["review_required"]:
            decision = store.event_decision(event.event_id)
            if decision == "approve":
                applied.extend(
                    apply_proposal(
                        proposal,
                        event_store=store,
                        project_root=root,
                        policy_path=policy,
                        safe_only=False,
                    )
                )
                continue
            if decision is None and registry_excel_review_is_reusable(
                event,
                proposal["actions"],
                project_root=root,
                policy=proposal_store.policy,
            ):
                store.record_review(
                    proposal_id=proposal["proposal_id"],
                    decision="approve",
                    reviewer="registry_excel_receipt",
                    reason="Deterministic projection of an accepted registry result with a trusted Excel promotion receipt.",
                    reviewed_event_id=event.event_id,
                    reviewed_event_sha256=event.digest,
                )
                applied.extend(
                    apply_proposal(
                        proposal,
                        event_store=store,
                        project_root=root,
                        policy_path=policy,
                        safe_only=False,
                    )
                )
                continue
            pending.append(
                {
                    "proposal_id": proposal["proposal_id"],
                    "review_questions": proposal["review_questions"],
                }
            )
            continue
        applied.extend(
            apply_proposal(
                proposal,
                event_store=store,
                project_root=root,
                policy_path=policy,
                safe_only=args.safe_only,
            )
        )
    print(json.dumps({"applied": sorted(set(applied)), "pending_review": pending}, indent=2, ensure_ascii=False))
    return 1 if pending else 0


def _task_view_payload(event: StateEvent) -> dict[str, Any]:
    payload = event.payload["payload"]
    return dict(payload["task"]) if event.event_type == "baseline_adopted" else dict(payload)


def _actionable_reviews(
    store: EventStore,
    *,
    root: Path,
    policy: Path,
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    proposal_policy = ProposalStore(root, policy).policy
    for event in store.actionable_pending_review_events():
        proposal = build_proposal(event, project_root=root, policy_path=policy)
        if not proposal["actions"]:
            continue
        if registry_excel_review_is_reusable(
            event,
            proposal["actions"],
            project_root=root,
            policy=proposal_policy,
        ):
            continue
        reviews.append(
            {
                "proposal_id": proposal["proposal_id"],
                "event_id": event.event_id,
                "reasons": sorted(
                    {
                        reason
                        for action in proposal["actions"]
                        for reason in action["reason_codes"]
                        if action["requires_review"]
                    }
                ),
            }
        )
    return reviews


def _control_status(root: Path, policy: Path, schema: Path, events: Path) -> dict[str, Any]:
    store = _store(root, schema, events)
    current = store.current_task_source()
    audit = audit_repository(project_root=root, policy_path=policy, phase="start")
    reviews = _actionable_reviews(store, root=root, policy=policy)
    if current is None:
        return {
            "schema_version": 1,
            "active": False,
            "audit": audit["counts"],
            "actionable_reviews": reviews,
        }
    task = _task_view_payload(current)
    latest = store.latest_by_entity()
    module_id = str(current.payload["entity"].get("module", ""))
    module = latest.get(("module", module_id))
    gate_candidates = [
        event
        for (kind, _), event in latest.items()
        if kind == "state"
        and event.payload["entity"].get("module") == module_id
        and isinstance(event.payload["payload"], dict)
        and "next_action" in event.payload["payload"]
    ]
    gate = max(gate_candidates, key=lambda event: (event.payload["recorded_at"], event.event_id), default=None)
    return {
        "schema_version": 1,
        "active": True,
        "task": {
            "entity_id": current.payload["entity"]["id"],
            "source_event_id": current.event_id,
            "phase": effective_phase(current),
            "objective": task.get("objective"),
            "one_executable_step": task.get("one_executable_step"),
            "submission_boundary": task.get("submission_boundary"),
            "done_when": task.get("done_when", []),
            "history_event_count": len(store.history(str(current.payload["entity"]["id"]))),
        },
        "quality_gate": (
            None
            if gate is None
            else {
                "source_event_id": gate.event_id,
                "title": gate.payload["payload"].get("title"),
                "next_action": gate.payload["payload"].get("next_action"),
                "facts": gate.payload["payload"].get("facts", []),
            }
        ),
        "module": (
            None
            if module is None
            else {
                "source_event_id": module.event_id,
                "status": module.payload["payload"].get("status"),
                "current_gate": module.payload["payload"].get("current_gate"),
                "depends_on": module.payload["payload"].get("depends_on"),
            }
        ),
        "actionable_reviews": reviews,
        "audit": audit["counts"],
    }


def _text_control_status(status: dict[str, Any]) -> str:
    if not status["active"]:
        return "当前没有活动任务。"
    task = status["task"]
    lines = [
        f"当前任务：{task['objective']}",
        f"阶段：{task['phase']}",
        f"唯一下一步：{task['one_executable_step']}",
        f"历史事件：{task['history_event_count']}（repo-state history --entity {task['entity_id']}）",
    ]
    module = status["module"]
    if module is not None:
        lines.append(f"质量门槛：{module['status']}；{module['depends_on']}")
    lines.append(f"待审核提案：{len(status['actionable_reviews'])}")
    lines.append(
        "审计："
        f"{status['audit']['error']} 错误，{status['audit']['warning']} 警告，"
        f"{status['audit']['review_required']} 项需审核"
    )
    return "\n".join(lines)


def _checkpoint(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    acceptance = StateEvent.from_path(args.event, schema_path=schema)
    if acceptance.event_type != "task_acceptance_recorded":
        raise ValueError("checkpoint --phase end requires task_acceptance_recorded")
    store = _store(root, schema, events)
    store.record(acceptance)
    completion = derive_task_completion_event(
        acceptance,
        event_store=store,
        schema_path=schema,
    )
    store.record(completion)
    proposal = build_proposal(completion, project_root=root, policy_path=policy)
    if not proposal["actions"]:
        raise ValueError("task-end checkpoint produced no current-task closure action")
    ProposalStore(root, policy).save(proposal)
    summary = _proposal_summary(proposal)
    summary.update(
        {
            "phase": args.phase,
            "acceptance_event_id": acceptance.event_id,
            "completion_event_id": completion.event_id,
        }
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if proposal["review_required"] else 0


def _task_command(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    store = _store(root, schema, events)
    current = store.current_task_source()
    if args.task_command == "status":
        payload = (
            {"active": False, "phase": "completed", "source_event_id": None}
            if current is None
            else {
                "active": True,
                "phase": effective_phase(current),
                "source_event_id": current.event_id,
                "source_event_sha256": current.digest,
            }
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    event = build_task_transition_event(
        event_store=store,
        to_phase=args.to,
        reason=args.reason,
        evidence_paths=[(path if path.is_absolute() else root / path) for path in args.evidence],
        schema_path=schema,
        policy_path=policy,
    )
    store.record(event)
    proposal = build_proposal(event, project_root=root, policy_path=policy)
    ProposalStore(root, policy).save(proposal)
    summary = _proposal_summary(proposal)
    if args.apply_safe:
        summary["changed"] = apply_proposal(
            proposal,
            event_store=store,
            project_root=root,
            policy_path=policy,
            safe_only=True,
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if proposal["review_required"] else 0


def _stale_item_command(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    if args.stale_command == "classify-batch":
        supplied_manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
        event = build_stale_item_batch_event(
            project_root=root,
            manifest_path=supplied_manifest,
            schema_path=schema,
        )
        store = _store(root, schema, events)
        store.record(event)
        proposal = build_proposal(event, project_root=root, policy_path=policy)
        ProposalStore(root, policy).save(proposal)
        print(json.dumps(_proposal_summary(proposal), indent=2, ensure_ascii=False))
        return 1
    supplied = args.path if args.path.is_absolute() else root / args.path
    event = build_stale_item_event(
        project_root=root,
        path=supplied,
        disposition=args.disposition,
        content_class=args.content_class,
        reason=args.reason,
        schema_path=schema,
    )
    store = _store(root, schema, events)
    store.record(event)
    proposal = build_proposal(event, project_root=root, policy_path=policy)
    ProposalStore(root, policy).save(proposal)
    print(json.dumps(_proposal_summary(proposal), indent=2, ensure_ascii=False))
    return 1


def _reconcile_current(
    args: argparse.Namespace,
    root: Path,
    policy: Path,
    schema: Path,
    events: Path,
) -> int:
    store = _store(root, schema, events)
    task_event = build_current_task_import(
        project_root=root,
        event_store=store,
        schema_path=schema,
    )
    state_event = build_current_gate_import(
        project_root=root,
        event_store=store,
        schema_path=schema,
    )
    proposals = [
        build_proposal(task_event, project_root=root, policy_path=policy),
        build_proposal(state_event, project_root=root, policy_path=policy),
    ]
    if args.record:
        proposal_store = ProposalStore(root, policy)
        for event, proposal in zip((task_event, state_event), proposals, strict=True):
            store.record(event)
            proposal_store.save(proposal)
    print(
        json.dumps(
            {
                "recorded": bool(args.record),
                "proposals": [_proposal_summary(proposal) for proposal in proposals],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1


def dispatch(args: argparse.Namespace) -> int:  # noqa: C901 - explicit CLI command routing
    root, policy, schema, events = _paths(args)
    if args.command == "audit":
        return _audit(args, root, policy)
    if args.command == "propose":
        return _propose(args, root, policy, schema, events)
    if args.command == "baseline":
        return _baseline(args, root, policy, schema, events)
    if args.command == "adopt-lifecycle-views":
        event = build_lifecycle_views_adoption_event(root, policy)
        return _reviewed_preview(
            event,
            record=args.record,
            root=root,
            policy=policy,
            schema=schema,
            events=events,
        )
    if args.command == "compact-current-state":
        event = build_state_history_compaction_event(
            project_root=root,
            section_heading=args.section,
            archive_path=args.archive,
        )
        return _reviewed_preview(
            event,
            record=args.record,
            root=root,
            policy=policy,
            schema=schema,
            events=events,
        )
    if args.command == "reconcile-entity":
        event = build_entity_reconciliation_event(
            event_store=_store(root, schema, events),
            entity_kind=args.kind,
            entity_id=args.entity,
            keep_event_id=args.keep,
            refresh_evidence=args.refresh_evidence,
        )
        return _reviewed_preview(
            event,
            record=args.record,
            root=root,
            policy=policy,
            schema=schema,
            events=events,
        )
    if args.command == "sync":
        return _sync(args, root, policy, schema, events)
    if args.command == "status":
        payload = _control_status(root, policy, schema, events)
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.format == "json" else _text_control_status(payload))
        return 0
    if args.command == "checkpoint":
        return _checkpoint(args, root, policy, schema, events)
    if args.command == "task":
        return _task_command(args, root, policy, schema, events)
    if args.command == "stale-item":
        return _stale_item_command(args, root, policy, schema, events)
    if args.command == "reconcile-current":
        return _reconcile_current(args, root, policy, schema, events)
    store = _store(root, schema, events)
    proposal_store = ProposalStore(root, policy)
    if args.command == "review":
        proposal = proposal_store.load(args.proposal)
        path = store.record_review(
            proposal_id=args.proposal,
            decision=args.decision,
            reviewer=args.reviewer,
            reason=args.reason,
            reviewed_event_id=str(proposal["event_id"]),
            reviewed_event_sha256=str(proposal["event_sha256"]),
        )
        print(path)
        return 0
    if args.command == "apply":
        proposal = proposal_store.load(args.proposal)
        changed = apply_proposal(
            proposal,
            event_store=store,
            project_root=root,
            policy_path=policy,
            safe_only=args.safe_only,
        )
        print(json.dumps({"changed": changed}, indent=2, ensure_ascii=False))
        return 0
    if args.command == "history":
        payload = [event.payload for event in store.history(args.entity)]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    raise ValueError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return dispatch(args)
    except ReviewRequired as error:
        print(f"REVIEW_REQUIRED: {error}", file=sys.stderr)
        return 3
    except StaleProposal as error:
        print(f"STALE_PROPOSAL: {error}", file=sys.stderr)
        return 4
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
