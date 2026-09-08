from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scripts.artifact_io import canonical_json, sha256_bytes, sha256_file, write_json_atomic

from .models import ROOT, StateEvent, utc_now
from .projections import (
    DEFAULT_POLICY,
    END_MARKER,
    START_MARKER,
    build_projection_actions,
    load_policy,
    module_row_text,
)
from .store import EventStore


class ReviewRequired(RuntimeError):
    pass


class StaleProposal(RuntimeError):
    pass


class ProposalStore:
    def __init__(self, project_root: Path = ROOT, policy_path: Path = DEFAULT_POLICY) -> None:
        self.project_root = project_root.resolve()
        self.policy_path = policy_path
        self.policy = load_policy(policy_path)
        self.cache_dir = self.project_root / self.policy["paths"]["proposal_cache"]

    def path(self, proposal_id: str) -> Path:
        return self.cache_dir / f"{proposal_id}.json"

    def save(self, proposal: dict[str, Any]) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return write_json_atomic(self.path(str(proposal["proposal_id"])), proposal)

    def load(self, proposal_id: str) -> dict[str, Any]:
        path = self.path(proposal_id)
        if not path.is_file():
            raise FileNotFoundError(f"unknown proposal: {proposal_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"proposal must be an object: {path}")
        _validate_proposal_id(payload)
        return payload


def _proposal_core(event: StateEvent, actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": event.event_id,
        "event_sha256": event.digest,
        "actions": actions,
    }


def _proposal_id(core: dict[str, Any]) -> str:
    return f"proposal-{sha256_bytes(canonical_json(core))[:24]}"


def _validate_proposal_id(proposal: dict[str, Any]) -> None:
    core = {
        "schema_version": proposal.get("schema_version"),
        "event_id": proposal.get("event_id"),
        "event_sha256": proposal.get("event_sha256"),
        "actions": proposal.get("actions"),
    }
    expected = _proposal_id(core)
    if proposal.get("proposal_id") != expected:
        raise ValueError("proposal ID does not match its hash-bound content")


def _review_questions(reason_codes: list[str]) -> list[dict[str, Any]]:
    reasons = sorted(set(reason_codes))
    return [
        {
            "question_id": "approve_exact_changes",
            "question": "Approve the exact hash-bound repository-state changes in this proposal?",
            "options": [
                {"value": "approve", "label": "Approve exact changes"},
                {"value": "reject", "label": "Reject and preserve current files"},
            ],
            "reason_codes": reasons,
        }
    ]


def _manifest_action(
    event: StateEvent,
    actions: list[dict[str, Any]],
    *,
    project_root: Path,
    policy: dict[str, Any],
) -> dict[str, Any] | None:
    projected = [
        action
        for action in actions
        if action["action_type"] == "write_text"
        and action.get("managed_projection", True)
    ]
    if not projected:
        return None
    manifest_path = project_root / policy["paths"]["projection_manifest"]
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"schema_version": 1, "projections": {}}
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("projections"), dict):
        raise ValueError("invalid projection manifest")
    for action in projected:
        key = action["target_path"]
        if action.get("block_id"):
            key += f"#{action['block_id']}"
        managed_unit = action.get("managed_unit")
        if managed_unit:
            key += f"#{managed_unit['kind']}:{managed_unit['id']}"
        record = {
            "source_event_id": event.event_id,
            "source_event_sha256": event.digest,
            "target_sha256_before": action["expected_sha256"],
            "target_sha256_after": sha256_bytes(action["new_content"].encode("utf-8")),
        }
        block_id = action.get("block_id")
        if block_id:
            start = START_MARKER.format(block_id=block_id)
            end = END_MARKER.format(block_id=block_id)
            match = re.search(
                re.escape(start) + r".*?" + re.escape(end),
                action["new_content"],
                re.DOTALL,
            )
            if match:
                record["managed_block_sha256"] = sha256_bytes(match.group(0).encode("utf-8"))
        if managed_unit:
            if managed_unit.get("kind") != "module_row":
                raise ValueError(f"unsupported managed projection unit: {managed_unit}")
            row = module_row_text(action["new_content"], str(managed_unit["id"]))
            record["managed_unit"] = managed_unit
            record["managed_unit_sha256"] = sha256_bytes(row.encode("utf-8"))
            manifest["projections"].pop(action["target_path"], None)
        manifest["projections"][key] = record
    content = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    return {
        "action_type": "write_text",
        "target_path": manifest_path.resolve().relative_to(project_root.resolve()).as_posix(),
        "expected_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        "requires_review": any(action["requires_review"] for action in projected),
        "reason_codes": sorted(
            {
                reason
                for action in projected
                for reason in action["reason_codes"]
            }
        ),
        "new_content": content,
        "block_id": "projection_manifest",
    }


def build_proposal(
    event: StateEvent,
    *,
    project_root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    actions = build_projection_actions(
        event,
        project_root=project_root,
        policy_path=policy_path,
    )
    manifest = _manifest_action(event, actions, project_root=project_root, policy=policy)
    if manifest is not None:
        actions.append(manifest)
    missing_evidence = event.event_type != "review_decision" and not event.payload["evidence"]
    if missing_evidence:
        for action in actions:
            action["requires_review"] = True
            action["reason_codes"] = sorted(set(action["reason_codes"] + ["missing_evidence"]))
    reasons = sorted(
        {
            reason
            for action in actions
            for reason in action["reason_codes"]
            if action["requires_review"]
        }
        | (set(event.payload["review"]["reason_codes"]) if event.review_required else set())
    )
    core = _proposal_core(event, actions)
    proposal = {
        **core,
        "proposal_id": _proposal_id(core),
        "created_at": utc_now(),
        "review_required": event.review_required or any(action["requires_review"] for action in actions),
        "review_questions": _review_questions(reasons) if reasons else [],
    }
    return proposal


def _resolved(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"proposal path escapes repository: {relative}") from error
    return path


def _validate_expected_hash(path: Path, expected: str | None, *, label: str) -> None:
    actual = sha256_file(path) if path.is_file() else None
    if actual != expected:
        raise StaleProposal(f"{label} changed after proposal: {path}")


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _check_repository_item_policy(
    path: Path,
    *,
    project_root: Path,
    policy: dict[str, Any],
) -> None:
    relative = path.resolve().relative_to(project_root.resolve())
    parts = relative.parts
    excluded = {str(item).lower() for item in policy["repository_item_policy"]["excluded_roots"]}
    if parts and parts[0].lower() in excluded:
        raise ValueError(f"repository-item mutation forbidden under {parts[0]}")
    forbidden_names = {str(item).lower() for item in policy["repository_item_policy"]["forbidden_names"]}
    forbidden_suffixes = {str(item).lower() for item in policy["repository_item_policy"]["forbidden_suffixes"]}
    if path.name.lower() in forbidden_names or path.suffix.lower() in forbidden_suffixes:
        raise ValueError(f"sensitive or scientific file cannot be archived/deleted: {relative}")
    max_bytes = int(policy["budgets"]["archive_max_file_mb"]) * 1024 * 1024
    if path.is_file() and path.stat().st_size > max_bytes:
        raise ValueError(f"repository item exceeds archive/delete safety limit: {relative}")


def _check_move_policy(source: Path, target: Path, *, project_root: Path) -> None:
    source_relative = source.resolve().relative_to(project_root.resolve())
    target_relative = target.resolve().relative_to(project_root.resolve())
    if not source_relative.parts or source_relative.parts[0].lower() != ".codex_tmp":
        raise ValueError("repository-item move source must be under .codex_tmp")
    if not target_relative.parts or target_relative.parts[0].lower() != "calculations":
        raise ValueError("repository-item move target must be under calculations")


def _require_review_decision(
    proposal: dict[str, Any],
    *,
    event_store: EventStore,
    safe_only: bool,
) -> str | None:
    decision = event_store.proposal_decision(str(proposal["proposal_id"]))
    if not proposal["review_required"]:
        return decision
    if safe_only:
        raise ReviewRequired("proposal contains changes that require user review")
    if decision != "approve":
        state = "rejected" if decision == "reject" else "not approved"
        raise ReviewRequired(f"proposal is {state}")
    return decision


def _validate_actions(
    actions: list[dict[str, Any]],
    *,
    root: Path,
    policy: dict[str, Any],
) -> None:
    for action in actions:
        target = _resolved(root, action["target_path"])
        if action["action_type"] == "archive_file":
            source = _resolved(root, action["source_path"])
            _validate_tracking_status(source, action, root=root)
            _validate_expected_hash(
                source,
                action.get("source_expected_sha256"),
                label="archive source",
            )
            if target.exists():
                raise StaleProposal(f"archive target already exists: {target}")
            _check_repository_item_policy(source, project_root=root, policy=policy)
            continue
        if action["action_type"] == "move_file":
            source = _resolved(root, action["source_path"])
            _validate_tracking_status(source, action, root=root)
            _validate_expected_hash(
                source,
                action.get("source_expected_sha256"),
                label="move source",
            )
            if target.exists():
                raise StaleProposal(f"move target already exists: {target}")
            if action.get("content_class") != "unique":
                raise ValueError("repository-item move requires unique content")
            _check_move_policy(source, target, project_root=root)
            continue
        _validate_expected_hash(
            target,
            action.get("expected_sha256"),
            label="proposal target",
        )
        if action["action_type"] == "delete_file":
            _validate_tracking_status(target, action, root=root)
            _check_repository_item_policy(target, project_root=root, policy=policy)


def _validate_tracking_status(path: Path, action: dict[str, Any], *, root: Path) -> None:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(path.relative_to(root))],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    actual = "tracked" if completed.returncode == 0 else "untracked"
    if actual != action.get("tracking_status"):
        raise StaleProposal(f"Git tracking status changed for {path}: {actual}")


def _execute_archive(
    action: dict[str, Any],
    *,
    root: Path,
    target: Path,
    proposal: dict[str, Any],
    event: StateEvent,
    decision: str | None,
    archived: list[tuple[Path, Path]],
    changed: list[str],
) -> None:
    source = _resolved(root, action["source_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha256_file(source) != sha256_file(target):
        raise OSError(f"archive copy hash mismatch: {source}")
    if not action.get("bundle_archive"):
        manifest = {
            "schema_version": 1,
            "proposal_id": proposal["proposal_id"],
            "review_decision": decision,
            "source_path": action["source_path"],
            "source_sha256": sha256_file(source),
            "archived_path": action["target_path"],
            "event_id": event.event_id,
        }
        write_json_atomic(target.parent / "archive_manifest.json", manifest)
    source.unlink()
    archived.append((source, target))
    changed.extend([action["source_path"], action["target_path"]])


def _execute_action(
    action: dict[str, Any],
    *,
    root: Path,
    proposal: dict[str, Any],
    event: StateEvent,
    decision: str | None,
    backups: dict[Path, bytes | None],
    archived: list[tuple[Path, Path]],
    changed: list[str],
) -> None:
    target = _resolved(root, action["target_path"])
    action_type = action["action_type"]
    if action_type == "write_text":
        backups[target] = target.read_bytes() if target.is_file() else None
        _write_text_atomic(target, str(action["new_content"]))
        changed.append(action["target_path"])
        return
    if action_type == "delete_file":
        backups[target] = target.read_bytes()
        target.unlink()
        changed.append(action["target_path"])
        return
    if action_type == "archive_file":
        _execute_archive(
            action,
            root=root,
            target=target,
            proposal=proposal,
            event=event,
            decision=decision,
            archived=archived,
            changed=changed,
        )
        return
    if action_type == "move_file":
        source = _resolved(root, action["source_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256_file(source) != sha256_file(target):
            raise OSError(f"move copy hash mismatch: {source}")
        source.unlink()
        archived.append((source, target))
        changed.extend([action["source_path"], action["target_path"]])
        return
    raise ValueError(f"unsupported proposal action: {action_type}")


def _rollback(
    *,
    backups: dict[Path, bytes | None],
    archived: list[tuple[Path, Path]],
) -> None:
    for source, target in reversed(archived):
        if target.is_file() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, source)
        target.unlink(missing_ok=True)
        (target.parent / "archive_manifest.json").unlink(missing_ok=True)
    for path, content in reversed(list(backups.items())):
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def apply_proposal(
    proposal: dict[str, Any],
    *,
    event_store: EventStore,
    project_root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
    safe_only: bool = False,
) -> list[str]:
    _validate_proposal_id(proposal)
    event = event_store.get(str(proposal["event_id"]))
    if event.digest != proposal["event_sha256"]:
        raise StaleProposal("event content no longer matches proposal")
    event_store.verify_evidence(event)
    decision = _require_review_decision(proposal, event_store=event_store, safe_only=safe_only)
    root = project_root.resolve()
    policy = load_policy(policy_path)
    actions = list(proposal["actions"])
    _validate_actions(actions, root=root, policy=policy)
    backups: dict[Path, bytes | None] = {}
    archived: list[tuple[Path, Path]] = []
    changed: list[str] = []
    try:
        for action in actions:
            _execute_action(
                action,
                root=root,
                proposal=proposal,
                event=event,
                decision=decision,
                backups=backups,
                archived=archived,
                changed=changed,
            )
    except BaseException:
        _rollback(backups=backups, archived=archived)
        raise
    return changed
