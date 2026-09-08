from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import sha256_file

from .models import ROOT, StateEvent


DEFAULT_POLICY = ROOT / "configs" / "state_handoff.yaml"
START_MARKER = "<!-- state-handoff:start {block_id} -->"
END_MARKER = "<!-- state-handoff:end {block_id} -->"
EXECUTION_BACKEND_CONSTRAINT = (
    "Execution backend roles and handoffs remain governed by "
    "`configs/execution_backends.yaml`."
)


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"invalid state-handoff policy: {path}")
    return payload


def _target_hash(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def _action(
    *,
    action_type: str,
    target: Path,
    root: Path,
    requires_review: bool,
    reason_codes: list[str],
    new_content: str | None = None,
    block_id: str | None = None,
    managed_unit: dict[str, str] | None = None,
    source: Path | None = None,
) -> dict[str, Any]:
    relative_target = target.resolve().relative_to(root.resolve())
    action: dict[str, Any] = {
        "action_type": action_type,
        "target_path": relative_target.as_posix(),
        "expected_sha256": _target_hash(target),
        "requires_review": requires_review,
        "reason_codes": sorted(set(reason_codes)),
    }
    if new_content is not None:
        action["new_content"] = new_content
    if block_id is not None:
        action["block_id"] = block_id
    if managed_unit is not None:
        action["managed_unit"] = managed_unit
    if source is not None:
        action["source_path"] = source.resolve().relative_to(root.resolve()).as_posix()
        action["source_expected_sha256"] = _target_hash(source)
    return action


def render_current_task(event: StateEvent) -> str:
    payload = event.payload["payload"]
    lines = [
        START_MARKER.format(block_id="current_task"),
        "# Current Task",
        "",
        "## Objective",
        "",
        str(payload["objective"]).strip(),
        "",
    ]
    evidence = payload.get("current_evidence", [])
    if evidence:
        lines.extend(["## Current Evidence Snapshot", ""])
        lines.extend(f"- {str(item).strip()}" for item in evidence)
        lines.append("")
    lines.extend(
        [
            "## Lifecycle Status",
            "",
            f"- Phase: `{payload.get('phase', 'active')}`",
        ]
    )
    transition = payload.get("lifecycle_transition")
    if transition:
        lines.append(f"- Latest transition: {_inline(transition['reason'])}")
    lines.append("")
    lines.extend(
        [
            "## One Executable Step",
            "",
            str(payload["one_executable_step"]).strip(),
        ]
    )
    submission_boundary = payload.get("submission_boundary")
    if submission_boundary:
        lines.extend(
            [
                "",
                "## Submission Boundary",
                "",
                str(submission_boundary).strip(),
            ]
        )
    lines.extend(["", "## Authoritative Constraint", "", EXECUTION_BACKEND_CONSTRAINT])
    lines.extend(["", "## Done When", ""])
    lines.extend(f"- {str(item).strip()}" for item in payload["done_when"])
    constraints = payload.get("constraints", [])
    if constraints:
        lines.extend(["", "## Constraints", ""])
        lines.extend(f"- {str(item).strip()}" for item in constraints)
    references = payload.get("authoritative_references", [])
    if references:
        lines.extend(["", "## Authoritative References", ""])
        lines.extend(f"- {str(item).strip()}" for item in references)
    lines.extend([END_MARKER.format(block_id="current_task"), ""])
    return "\n".join(lines)


def render_no_active_task(event: StateEvent) -> str:
    return "\n".join(
        [
            START_MARKER.format(block_id="current_task"),
            "# Current Task",
            "",
            "No active task. The latest completed task event is",
            f"`{event.event_id}`.",
            "",
            "## Authoritative Constraint",
            "",
            EXECUTION_BACKEND_CONSTRAINT,
            END_MARKER.format(block_id="current_task"),
            "",
        ]
    )


def render_state_block(event: StateEvent) -> str:
    payload = event.payload["payload"]
    block_id = str(payload["block_id"])
    lines = [
        START_MARKER.format(block_id=block_id),
        f"### {str(payload['title']).strip()}",
        "",
    ]
    lines.extend(f"- {str(fact).strip()}" for fact in payload["facts"])
    next_action = payload.get("next_action")
    if next_action:
        lines.extend(["", f"Next action: {str(next_action).strip()}"])
    lines.extend([END_MARKER.format(block_id=block_id)])
    return "\n".join(lines)


def replace_managed_block(text: str, block_id: str, rendered: str) -> tuple[str, bool]:
    start = START_MARKER.format(block_id=block_id)
    end = END_MARKER.format(block_id=block_id)
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != end_count or start_count > 1:
        raise ValueError(f"invalid managed block markers for {block_id}")
    if start_count == 0:
        return text, False
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    return pattern.sub(rendered.rstrip(), text, count=1), True


def insert_after_heading(text: str, heading: str, rendered: str) -> str:
    matches = list(re.finditer(rf"(?m)^{re.escape(heading)}\s*$", text))
    if len(matches) != 1:
        raise ValueError(f"target heading must occur exactly once: {heading}")
    insertion = matches[0].end()
    tail = text[insertion:]
    if tail.startswith("\r\n"):
        insertion += 2
    elif tail.startswith("\n"):
        insertion += 1
    return text[:insertion] + "\n" + rendered.rstrip() + "\n" + text[insertion:]


def module_row_text(text: str, module: str) -> str:
    pattern = re.compile(rf"(?m)^\| `{re.escape(module)}` \|.*$")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"module row must occur exactly once: {module}")
    return matches[0].group(0)


def _module_row(text: str, module: str, payload: dict[str, Any]) -> str:
    module_row_text(text, module)
    pattern = re.compile(rf"(?m)^\| `{re.escape(module)}` \|.*$")
    row = (
        f"| `{module}` | {payload['status']} | {payload['depends_on']} | "
        f"{payload['current_gate']} |"
    )
    return pattern.sub(row, text, count=1)


def _append_reviewed_event(text: str, event: StateEvent) -> str:
    marker = f"<!-- state-handoff:event {event.event_id} -->"
    if marker in text:
        return text
    markdown = str(event.payload["payload"].get("markdown", "")).strip()
    if not markdown:
        raise ValueError(f"{event.event_type} requires payload.markdown")
    return text.rstrip() + f"\n\n{marker}\n{markdown}\n"


def _task_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
) -> list[dict[str, Any]]:
    target = root / views["current_task"]
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    rendered = render_no_active_task(event) if event.event_type == "task_completed" else render_current_task(event)
    new_content, managed = replace_managed_block(current, "current_task", rendered)
    if not managed:
        new_content = rendered
    adopt_current = bool(event.payload["payload"].get("adopt_current_projection"))
    if new_content == current and (
        not adopt_current or _projection_owned_by_event(root, target, "current_task", event)
    ):
        return []
    reasons = list(event.payload["review"]["reason_codes"])
    if not managed:
        reasons.append("initial_managed_view_adoption")
    return [
        _action(
            action_type="write_text",
            target=target,
            root=root,
            requires_review=event.review_required or not managed,
            reason_codes=reasons,
            new_content=new_content,
            block_id="current_task",
        )
    ]


def _inline(value: Any) -> str:
    return " ".join(str(value).split())


def _evidence_text(value: dict[str, Any]) -> str:
    return ", ".join(f"`{digest}`" for digest in value["evidence_sha256"])


def _append_managed_entries(
    text: str,
    *,
    block_id: str,
    title: str,
    entries: list[tuple[str, str]],
) -> tuple[str, bool]:
    start = START_MARKER.format(block_id=block_id)
    end = END_MARKER.format(block_id=block_id)
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != end_count or start_count > 1:
        raise ValueError(f"invalid managed block markers for {block_id}")
    managed = start_count == 1
    if managed:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
        block = pattern.search(text).group(0)
    else:
        block = f"{start}\n## {title}\n\n{end}"

    for marker, markdown in entries:
        if marker in block:
            continue
        block = block.replace(end, f"{marker}\n{markdown.strip()}\n\n{end}", 1)

    if managed:
        return pattern.sub(block, text, count=1), True
    separator = "\n\n" if text.strip() else ""
    return text.rstrip() + separator + block + "\n", False


def _history_entries(event: StateEvent) -> list[tuple[str, str]]:
    handoff = event.payload["payload"]["handoff"]
    history = handoff["history"]
    marker = f"<!-- state-handoff:item history:{event.event_id} -->"
    markdown = "\n".join(
        [
            f"### {str(event.payload['occurred_at'])[:10]} — {_inline(history['title'])}",
            "",
            f"- Task: `{_inline(event.payload['entity']['id'])}`",
            f"- Outcome: {_inline(history['outcome'])}",
            f"- Summary: {_inline(history['summary'])}",
            f"- Acceptance event: `{_inline(event.payload['payload']['acceptance_event_id'])}`",
            f"- Evidence SHA-256: {_evidence_text(history)}",
        ]
    )
    return [(marker, markdown)]


def _backlog_entries(event: StateEvent) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for item in event.payload["payload"]["handoff"]["backlog_items"]:
        identifier = _inline(item["id"])
        marker = f"<!-- state-handoff:item backlog:{identifier} -->"
        module = _inline(item.get("module") or "Not assigned")
        markdown = "\n".join(
            [
                f"### {_inline(item['priority'])} — {_inline(item['summary'])} (`{identifier}`)",
                "",
                f"- Category: {_inline(item['category'])}",
                f"- Module: `{module}`",
                f"- Next action: {_inline(item['next_action'])}",
                f"- Done when: {_inline(item['done_when'])}",
                f"- Source task completion: `{event.event_id}`",
                f"- Evidence SHA-256: {_evidence_text(item)}",
            ]
        )
        entries.append((marker, markdown))
    return entries


def _error_entries(event: StateEvent) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for item in event.payload["payload"]["handoff"]["errors"]:
        identifier = _inline(item["id"])
        marker = f"<!-- state-handoff:item error:{identifier} -->"
        markdown = "\n".join(
            [
                f"### `{identifier}` — {_inline(item['summary'])}",
                "",
                f"- Impact: {_inline(item['impact'])}",
                f"- Next action: {_inline(item['next_action'])}",
                f"- Owner: {_inline(item['owner'])}",
                f"- Source task completion: `{event.event_id}`",
                f"- Evidence SHA-256: {_evidence_text(item)}",
            ]
        )
        entries.append((marker, markdown))
    return entries


def _decision_entries(event: StateEvent) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for item in event.payload["payload"]["handoff"]["decisions"]:
        identifier = _inline(item["id"])
        marker = f"<!-- state-handoff:item decision:{identifier} -->"
        markdown = "\n".join(
            [
                f"### {str(event.payload['occurred_at'])[:10]} — {_inline(item['title'])} (`{identifier}`)",
                "",
                f"- Decision: {_inline(item['decision'])}",
                f"- Reason: {_inline(item['reason'])}",
                f"- Consequence: {_inline(item['consequence'])}",
                f"- Source task completion: `{event.event_id}`",
                f"- Evidence SHA-256: {_evidence_text(item)}",
            ]
        )
        entries.append((marker, markdown))
    return entries


def _completion_view_action(
    event: StateEvent,
    *,
    root: Path,
    target: Path,
    block_id: str,
    title: str,
    entries: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    if not entries:
        return []
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    new_content, managed = _append_managed_entries(
        current,
        block_id=block_id,
        title=title,
        entries=entries,
    )
    if new_content == current:
        return []
    reasons = list(event.payload["review"]["reason_codes"]) + ["task_handoff_projection"]
    if not managed:
        reasons.append("initial_managed_view_adoption")
    return [
        _action(
            action_type="write_text",
            target=target,
            root=root,
            requires_review=event.review_required or not managed,
            reason_codes=reasons,
            new_content=new_content,
            block_id=block_id,
        )
    ]


def _task_completion_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
) -> list[dict[str, Any]]:
    actions = _task_actions(event, root=root, views=views)
    specifications = (
        ("historical_results", "task_history_events", "Managed Task History", _history_entries(event)),
        ("backlog", "task_backlog_events", "Managed Backlog", _backlog_entries(event)),
        ("error_log", "task_error_events", "Managed Open Errors", _error_entries(event)),
        ("decisions_log", "task_decision_events", "Managed Decisions", _decision_entries(event)),
    )
    for view_name, block_id, title, entries in specifications:
        actions.extend(
            _completion_view_action(
                event,
                root=root,
                target=root / views[view_name],
                block_id=block_id,
                title=title,
                entries=entries,
            )
        )
    return actions


def _lifecycle_view_adoption_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
) -> list[dict[str, Any]]:
    specifications = (
        ("backlog", "task_backlog_events", "Managed Backlog"),
        ("error_log", "task_error_events", "Managed Open Errors"),
        ("decisions_log", "task_decision_events", "Managed Decisions"),
        ("historical_results", "task_history_events", "Managed Task History"),
    )
    actions: list[dict[str, Any]] = []
    for view_name, block_id, title in specifications:
        target = root / views[view_name]
        current = target.read_text(encoding="utf-8")
        new_content, managed = _append_managed_entries(
            current,
            block_id=block_id,
            title=title,
            entries=[],
        )
        if managed or new_content == current:
            continue
        actions.append(
            _action(
                action_type="write_text",
                target=target,
                root=root,
                requires_review=True,
                reason_codes=["initial_managed_view_adoption"],
                new_content=new_content,
                block_id=block_id,
            )
        )
    return actions


def _state_history_compaction_actions(
    event: StateEvent,
    *,
    root: Path,
) -> list[dict[str, Any]]:
    payload = event.payload["payload"]
    source = root / str(payload["source_path"])
    archive = root / str(payload["archive_path"])
    current = source.read_text(encoding="utf-8")
    replacement = str(payload["replacement"])
    if replacement in current and archive.is_file():
        return []
    if sha256_file(source) != payload["source_sha256"]:
        raise ValueError("state history source changed before proposal generation")
    section_heading = str(payload["section_heading"])
    history_heading = str(payload["history_heading"])
    section_match = re.search(rf"(?m)^{re.escape(section_heading)}\s*$", current)
    if section_match is None:
        raise ValueError(f"state section is missing: {section_heading}")
    next_section = re.search(r"(?m)^## ", current[section_match.end() :])
    section_end = section_match.end() + next_section.start() if next_section else len(current)
    section = current[section_match.start() : section_end]
    history_match = re.search(rf"(?m)^{re.escape(history_heading)}\s*$", section)
    if history_match is None:
        raise ValueError(f"history subsection is missing: {history_heading}")
    history_start = section_match.start() + history_match.start()
    history_text = current[history_start:section_end].rstrip() + "\n"
    archive_content = "\n".join(
        [
            f"# Archived history from {section_heading.removeprefix('## ').strip()}",
            "",
            f"- Source: `{payload['source_path']}`",
            f"- Source SHA-256 before compaction: `{payload['source_sha256']}`",
            f"- Compaction event: `{event.event_id}`",
            "",
            history_text.rstrip(),
            "",
        ]
    )
    new_content = current[:history_start] + replacement.rstrip() + "\n\n" + current[section_end:].lstrip("\r\n")
    reasons = list(event.payload["review"]["reason_codes"])
    actions = [
        _action(
            action_type="write_text",
            target=archive,
            root=root,
            requires_review=True,
            reason_codes=reasons,
            new_content=archive_content,
        ),
        _action(
            action_type="write_text",
            target=source,
            root=root,
            requires_review=True,
            reason_codes=reasons,
            new_content=new_content,
        ),
    ]
    for action in actions:
        action["managed_projection"] = False
    return actions


def _state_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
) -> list[dict[str, Any]]:
    payload = event.payload["payload"]
    target = root / views["current_state"]
    current = target.read_text(encoding="utf-8")
    block_id = str(payload["block_id"])
    rendered = render_state_block(event)
    new_content, managed = replace_managed_block(current, block_id, rendered)
    if not managed:
        new_content = insert_after_heading(current, str(payload["section"]), rendered)
    if payload.get("project_state_header"):
        event_date = str(event.payload["occurred_at"])[:10]
        new_content, replaced = re.subn(
            r"(?m)^State updated:\s*\d{4}-\d{2}-\d{2}(\s+CST\.)",
            f"State updated: {event_date}\\1",
            new_content,
            count=1,
        )
        if replaced != 1:
            raise ValueError("Current-state header must occur exactly once for projection")
    adopt_current = bool(event.payload["payload"].get("adopt_current_projection"))
    if new_content == current and (
        not adopt_current or _projection_owned_by_event(root, target, block_id, event)
    ):
        return []
    reasons = list(event.payload["review"]["reason_codes"])
    if not managed:
        reasons.append("initial_managed_view_adoption")
    return [
        _action(
            action_type="write_text",
            target=target,
            root=root,
            requires_review=event.review_required or not managed,
            reason_codes=reasons,
            new_content=new_content,
            block_id=block_id,
        )
    ]


def _projection_owned_by_event(
    root: Path,
    target: Path,
    block_id: str,
    event: StateEvent,
) -> bool:
    policy_path = root / "configs" / "state_handoff.yaml"
    if not policy_path.is_file():
        return False
    policy = load_policy(policy_path)
    manifest_path = root / policy["paths"]["projection_manifest"]
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_name = target.resolve().relative_to(root.resolve()).as_posix()
    record = manifest.get("projections", {}).get(f"{target_name}#{block_id}", {})
    return (
        record.get("source_event_id") == event.event_id
        and record.get("source_event_sha256") == event.digest
    )


def _module_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
) -> list[dict[str, Any]]:
    payload = event.payload["payload"]
    target = root / views["module_map"]
    current = target.read_text(encoding="utf-8")
    module = str(payload["module"])
    new_content = _module_row(current, module, payload)
    if new_content == current:
        return []
    cross_module = module != "state_handoff"
    reasons = list(event.payload["review"]["reason_codes"])
    if cross_module:
        reasons.append("cross_module_change")
    return [
        _action(
            action_type="write_text",
            target=target,
            root=root,
            requires_review=event.review_required or cross_module,
            reason_codes=reasons,
            new_content=new_content,
            managed_unit={"kind": "module_row", "id": module},
        )
    ]


def _append_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
    view_name: str,
) -> list[dict[str, Any]]:
    target = root / views[view_name]
    current = target.read_text(encoding="utf-8")
    new_content = _append_reviewed_event(current, event)
    if new_content == current:
        return []
    reasons = list(event.payload["review"]["reason_codes"])
    reasons.append("reviewed_log_or_history_change")
    return [
        _action(
            action_type="write_text",
            target=target,
            root=root,
            requires_review=True,
            reason_codes=reasons,
            new_content=new_content,
        )
    ]


def _repository_actions(
    event: StateEvent,
    *,
    root: Path,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = event.payload["payload"]
    batch_items = payload.get("items")
    if batch_items is not None:
        date = str(event.payload["occurred_at"])[:10]
        bundle_root = root / policy["paths"]["archive"] / date / event.event_id
        manifest_content = json.dumps(
            {
                "schema_version": 1,
                "event_id": event.event_id,
                "event_sha256": event.digest,
                "source_manifest": payload["manifest_path"],
                "source_manifest_sha256": payload["manifest_sha256"],
                "items": batch_items,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        manifest_path = bundle_root / "bundle_manifest.json"
        if (
            manifest_path.is_file()
            and manifest_path.read_text(encoding="utf-8") == manifest_content
            and _batch_repository_postconditions_hold(
                batch_items,
                root=root,
                bundle_root=bundle_root,
            )
        ):
            return []
        actions: list[dict[str, Any]] = []
        for item in batch_items:
            actions.extend(
                _repository_item_actions(
                    event,
                    payload=item,
                    root=root,
                    policy=policy,
                    preserve_relative_archive_path=True,
                )
            )
        manifest_action = _action(
            action_type="write_text",
            target=manifest_path,
            root=root,
            requires_review=True,
            reason_codes=list(event.payload["review"]["reason_codes"]) + ["repository_cleanup_bundle_manifest"],
            new_content=manifest_content,
        )
        manifest_action["managed_projection"] = False
        actions.append(manifest_action)
        return actions
    return _repository_item_actions(
        event,
        payload=payload,
        root=root,
        policy=policy,
        preserve_relative_archive_path=False,
    )


def _batch_repository_postconditions_hold(
    items: list[dict[str, Any]],
    *,
    root: Path,
    bundle_root: Path,
) -> bool:
    for item in items:
        source = (root / str(item["path"])).resolve()
        try:
            relative_source = source.relative_to(root)
        except ValueError:
            return False
        disposition = item.get("disposition", "keep")
        if disposition == "delete":
            if source.exists():
                return False
            continue
        if disposition == "move":
            target = (root / str(item["target_path"])).resolve()
        elif disposition == "archive":
            target = bundle_root / relative_source
        else:
            return False
        try:
            target.relative_to(root)
        except ValueError:
            return False
        if source.exists() or not target.is_file():
            return False
        if sha256_file(target) != item.get("sha256"):
            return False
    return True


def _repository_item_actions(
    event: StateEvent,
    *,
    payload: dict[str, Any],
    root: Path,
    policy: dict[str, Any],
    preserve_relative_archive_path: bool,
) -> list[dict[str, Any]]:
    disposition = payload.get("disposition", "keep")
    if disposition == "keep":
        return []
    source = Path(str(payload["path"]))
    source = (source if source.is_absolute() else root / source).resolve()
    try:
        source.relative_to(root)
    except ValueError as error:
        raise ValueError("external repository items are audit-only in version 1") from error
    if not source.is_file():
        raise ValueError("version 1 archive/delete applies to files only")
    expected = payload.get("sha256")
    if expected is not None and sha256_file(source) != expected:
        raise ValueError(f"repository item changed after classification: {payload['path']}")
    reasons = list(event.payload["review"]["reason_codes"])
    if disposition == "delete":
        if payload["tracking_status"] == "untracked" and payload["content_class"] == "unique":
            raise ValueError("unique untracked content must be archived, not deleted")
        action = _action(
                action_type="delete_file",
                target=source,
                root=root,
                requires_review=True,
                reason_codes=reasons + ["destructive_delete"],
            )
        action["tracking_status"] = payload["tracking_status"]
        action["content_class"] = payload["content_class"]
        return [action]
    if disposition == "move":
        if payload["tracking_status"] != "untracked" or payload["content_class"] != "unique":
            raise ValueError("repository item move requires unique untracked content")
        target = (root / str(payload["target_path"])).resolve()
        action = _action(
            action_type="move_file",
            target=target,
            source=source,
            root=root,
            requires_review=True,
            reason_codes=reasons + ["move_unique_scientific_evidence"],
        )
        action["tracking_status"] = payload["tracking_status"]
        action["content_class"] = payload["content_class"]
        return [action]
    if disposition != "archive":
        raise ValueError(f"unsupported repository item disposition: {disposition}")
    if payload["tracking_status"] != "untracked" or payload["content_class"] != "unique":
        raise ValueError("archive is reserved for unique untracked content")
    date = str(event.payload["occurred_at"])[:10]
    archived_name = source.relative_to(root) if preserve_relative_archive_path else Path(source.name)
    target = root / policy["paths"]["archive"] / date / event.event_id / archived_name
    action = _action(
            action_type="archive_file",
            target=target,
            source=source,
            root=root,
            requires_review=True,
            reason_codes=reasons + ["archive_unique_untracked_content"],
        )
    action["tracking_status"] = payload["tracking_status"]
    action["content_class"] = payload["content_class"]
    if preserve_relative_archive_path:
        action["bundle_archive"] = True
    return [action]


def _derived_event(
    event: StateEvent,
    *,
    event_type: str,
    kind: str,
    entity_id: str,
    payload: dict[str, Any],
) -> StateEvent:
    value = dict(event.payload)
    value["event_type"] = event_type
    value["entity"] = {"kind": kind, "id": entity_id, "module": "state_handoff"}
    value["payload"] = payload
    return StateEvent(value)


def _baseline_state_action(
    event: StateEvent,
    block: dict[str, Any],
    *,
    root: Path,
    views: dict[str, str],
) -> dict[str, Any]:
    target = root / views["current_state"]
    current = target.read_text(encoding="utf-8")
    state_event = _derived_event(
        event,
        event_type="state_observed",
        kind="state",
        entity_id=str(block["block_id"]),
        payload=block,
    )
    rendered = render_state_block(state_event)
    source_heading = str(block["source_heading"])
    pattern = re.compile(
        rf"(?ms)^{re.escape(source_heading)}\s*$.*?(?=^### |^## |\Z)"
    )
    matches = list(pattern.finditer(current))
    if len(matches) != 1:
        raise ValueError(f"baseline Current Gate source must occur exactly once: {source_heading}")
    new_content = pattern.sub(rendered + "\n\n", current, count=1)
    return _action(
        action_type="write_text",
        target=target,
        root=root,
        requires_review=True,
        reason_codes=["initial_managed_view_adoption"],
        new_content=new_content,
        block_id=str(block["block_id"]),
    )


def _baseline_actions(
    event: StateEvent,
    *,
    root: Path,
    views: dict[str, str],
) -> list[dict[str, Any]]:
    task_text = (root / views["current_task"]).read_text(encoding="utf-8")
    task_managed = START_MARKER.format(block_id="current_task") in task_text
    state_text = (root / views["current_state"]).read_text(encoding="utf-8")
    state_managed = all(
        START_MARKER.format(block_id=str(block["block_id"])) in state_text
        for block in event.payload["payload"]["state_blocks"]
    )
    if task_managed and state_managed:
        return []
    task_event = _derived_event(
        event,
        event_type="task_opened",
        kind="task",
        entity_id="task-current",
        payload=event.payload["payload"]["task"],
    )
    actions = _task_actions(task_event, root=root, views=views)
    for block in event.payload["payload"]["state_blocks"]:
        actions.append(_baseline_state_action(event, block, root=root, views=views))
    return actions


def build_projection_actions(
    event: StateEvent,
    *,
    project_root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
) -> list[dict[str, Any]]:
    policy = load_policy(policy_path)
    views = policy["managed_views"]
    root = project_root.resolve()
    if event.event_type == "baseline_adopted":
        return _baseline_actions(event, root=root, views=views)
    if event.event_type == "task_acceptance_recorded":
        return []
    if event.event_type == "task_completed":
        return _task_completion_actions(event, root=root, views=views)
    if event.event_type == "lifecycle_views_adopted":
        return _lifecycle_view_adoption_actions(event, root=root, views=views)
    if event.event_type == "state_history_compacted":
        return _state_history_compaction_actions(event, root=root)
    if event.event_type in {"task_opened", "task_updated"}:
        return _task_actions(event, root=root, views=views)
    if event.event_type == "state_observed":
        return _state_actions(event, root=root, views=views)
    if event.event_type == "module_gate_changed":
        return _module_actions(event, root=root, views=views)
    append_targets = {
        "backlog_item_added": "backlog",
        "backlog_item_closed": "backlog",
        "error_opened": "error_log",
        "error_resolved": "error_log",
        "decision_recorded": "decisions_log",
        "history_recorded": "historical_results",
    }
    if event.event_type in append_targets:
        return _append_actions(event, root=root, views=views, view_name=append_targets[event.event_type])
    if event.event_type == "repository_item_classified":
        return _repository_actions(event, root=root, policy=policy)
    if event.event_type in {"repository_item_archived", "repository_item_deleted", "review_decision"}:
        return []
    raise ValueError(f"no projection handler for event type: {event.event_type}")


def proposal_preview(actions: list[dict[str, Any]]) -> str:
    compact = [
        {
            "action": action["action_type"],
            "target": action["target_path"],
            "review": action["requires_review"],
            "reasons": action["reason_codes"],
        }
        for action in actions
    ]
    return json.dumps(compact, indent=2, ensure_ascii=False)
