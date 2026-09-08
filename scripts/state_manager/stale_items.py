from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.artifact_io import canonical_json, sha256_bytes, sha256_file

from .models import StateEvent, utc_now


def _tracking_status(path: Path, *, root: Path) -> str:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(path.relative_to(root))],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return "tracked" if completed.returncode == 0 else "untracked"


def build_stale_item_event(
    *,
    project_root: Path,
    path: Path,
    disposition: str,
    content_class: str,
    reason: str,
    schema_path: Path,
) -> StateEvent:
    root = project_root.resolve()
    target = path.resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise ValueError("stale-item classification is limited to repository paths") from error
    if not target.is_file():
        raise ValueError("stale-item classify currently supports exact files only")
    if disposition not in {"keep", "archive", "delete"}:
        raise ValueError(f"invalid stale-item disposition: {disposition}")
    if content_class not in {"unique", "regenerable", "duplicate"}:
        raise ValueError(f"invalid stale-item content class: {content_class}")
    if not reason.strip():
        raise ValueError("stale-item classification requires a reason")
    tracking_status = _tracking_status(target, root=root)
    if disposition == "archive" and (tracking_status != "untracked" or content_class != "unique"):
        raise ValueError("archive requires unique untracked content")
    if disposition == "delete" and tracking_status == "untracked" and content_class == "unique":
        raise ValueError("unique untracked content must be archived, not deleted")

    observed_at = utc_now()
    digest = sha256_file(target)
    payload = {
        "path": relative.as_posix(),
        "disposition": disposition,
        "tracking_status": tracking_status,
        "content_class": content_class,
        "reason": reason.strip(),
        "sha256": digest,
        "size_bytes": target.stat().st_size,
    }
    identity = sha256_bytes(canonical_json(payload))[:24]
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"repository-item-{identity}",
            "event_type": "repository_item_classified",
            "entity": {
                "kind": "repository_item",
                "id": relative.as_posix(),
                "module": "state_handoff",
            },
            "occurred_at": observed_at,
            "recorded_at": observed_at,
            "summary": f"Classify {relative.as_posix()} as {disposition}: {reason.strip()}",
            "payload": payload,
            "evidence": [
                {
                    "locator": relative.as_posix(),
                    "sha256": digest,
                    "authority": "repository_document",
                    "observed_at": observed_at,
                }
            ],
            "supersedes": [],
            "review": {
                "required": True,
                "reason_codes": ["repository_item_classification"],
                "status": "pending",
            },
        },
        schema_path=schema_path,
    )


def _batch_item(
    item: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    raw_path = item.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("batch repository item requires a non-empty path")
    target = (root / raw_path).resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise ValueError(f"batch repository item escapes the repository: {raw_path}") from error
    if not target.is_file():
        raise ValueError(f"batch repository item is not an exact file: {relative.as_posix()}")

    disposition = item.get("disposition")
    content_class = item.get("content_class")
    reason = item.get("reason")
    if disposition not in {"archive", "delete", "move"}:
        raise ValueError(f"invalid batch repository item disposition: {disposition}")
    if content_class not in {"unique", "regenerable", "duplicate"}:
        raise ValueError(f"invalid batch repository item content class: {content_class}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("batch repository item requires a reason")
    tracking_status = _tracking_status(target, root=root)
    if disposition == "archive" and (tracking_status != "untracked" or content_class != "unique"):
        raise ValueError("batch archive requires unique untracked content")
    if disposition == "delete" and tracking_status == "untracked" and content_class == "unique":
        raise ValueError("unique untracked content must be archived or moved, not deleted")
    normalized: dict[str, Any] = {
        "path": relative.as_posix(),
        "disposition": disposition,
        "tracking_status": tracking_status,
        "content_class": content_class,
        "reason": reason.strip(),
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
    }
    if disposition == "move":
        raw_destination = item.get("target_path")
        if not isinstance(raw_destination, str) or not raw_destination.strip():
            raise ValueError("batch move requires target_path")
        destination = (root / raw_destination).resolve()
        try:
            destination_relative = destination.relative_to(root)
        except ValueError as error:
            raise ValueError(f"batch move target escapes the repository: {raw_destination}") from error
        if destination.exists():
            raise ValueError(f"batch move target already exists: {destination_relative.as_posix()}")
        normalized["target_path"] = destination_relative.as_posix()
    return normalized


def _selector_items(selector: dict[str, Any], *, root: Path) -> list[dict[str, Any]]:
    raw_root = selector.get("root")
    git_status = selector.get("git_status")
    expected_count = selector.get("expected_count")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError("batch selector requires root")
    selector_root = (root / raw_root).resolve()
    try:
        relative_root = selector_root.relative_to(root)
    except ValueError as error:
        raise ValueError(f"batch selector root escapes the repository: {raw_root}") from error
    if not selector_root.is_dir():
        raise ValueError(f"batch selector root is not a directory: {relative_root.as_posix()}")
    if git_status not in {"untracked", "ignored"}:
        raise ValueError("batch selector git_status must be untracked or ignored")
    if not isinstance(expected_count, int) or expected_count < 1:
        raise ValueError("batch selector requires a positive expected_count")
    if selector.get("disposition") == "move":
        raise ValueError("batch selectors cannot infer move targets")
    command = ["git", "-c", "core.quotePath=false", "ls-files", "-z", "--others"]
    if git_status == "ignored":
        command.extend(["-i", "--exclude-standard"])
    else:
        command.append("--exclude-standard")
    command.extend(["--", relative_root.as_posix()])
    completed = subprocess.run(command, cwd=root, check=True, capture_output=True)
    paths = sorted(
        entry.decode("utf-8")
        for entry in completed.stdout.split(b"\0")
        if entry
    )
    excluded = selector.get("exclude_paths", [])
    if not isinstance(excluded, list) or any(not isinstance(item, str) for item in excluded):
        raise ValueError("batch selector exclude_paths must be a list of paths")
    excluded_set = {Path(item).as_posix() for item in excluded}
    paths = [path for path in paths if Path(path).as_posix() not in excluded_set]
    if len(paths) != expected_count:
        raise ValueError(
            f"batch selector count changed for {relative_root.as_posix()}: "
            f"expected {expected_count}, found {len(paths)}"
        )
    return [
        {
            "path": path,
            "disposition": selector.get("disposition"),
            "content_class": selector.get("content_class"),
            "reason": selector.get("reason"),
        }
        for path in paths
    ]


def build_stale_item_batch_event(
    *,
    project_root: Path,
    manifest_path: Path,
    schema_path: Path,
) -> StateEvent:
    root = project_root.resolve()
    manifest = manifest_path.resolve()
    try:
        relative_manifest = manifest.relative_to(root)
    except ValueError as error:
        raise ValueError("batch classification manifest must stay inside the repository") from error
    payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("batch classification manifest schema_version must be 1")
    if payload.get("document_kind") != "repository_cleanup_manifest":
        raise ValueError("invalid batch classification manifest document_kind")
    bundle_id = payload.get("bundle_id")
    reason = payload.get("reason")
    raw_items = payload.get("items", [])
    selectors = payload.get("selectors", [])
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise ValueError("batch classification manifest requires bundle_id")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("batch classification manifest requires reason")
    if not isinstance(raw_items, list) or not isinstance(selectors, list):
        raise ValueError("batch classification manifest items and selectors must be lists")
    if not raw_items and not selectors:
        raise ValueError("batch classification manifest requires items or selectors")
    expanded_items = list(raw_items)
    for selector in selectors:
        if not isinstance(selector, dict):
            raise ValueError("batch classification manifest selectors must be objects")
        expanded_items.extend(_selector_items(selector, root=root))
    items = [_batch_item(item, root=root) for item in expanded_items if isinstance(item, dict)]
    if len(items) != len(expanded_items):
        raise ValueError("batch classification manifest items must be objects")
    paths = [str(item["path"]) for item in items]
    if len(paths) != len(set(paths)):
        raise ValueError("batch classification manifest contains duplicate source paths")
    targets = [str(item["target_path"]) for item in items if "target_path" in item]
    if len(targets) != len(set(targets)):
        raise ValueError("batch classification manifest contains duplicate move targets")

    observed_at = utc_now()
    manifest_sha256 = sha256_file(manifest)
    event_payload = {
        "bundle_id": bundle_id.strip(),
        "manifest_path": relative_manifest.as_posix(),
        "manifest_sha256": manifest_sha256,
        "reason": reason.strip(),
        "items": items,
    }
    identity = sha256_bytes(canonical_json(event_payload))[:24]
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"repository-items-{identity}",
            "event_type": "repository_item_classified",
            "entity": {
                "kind": "repository_item",
                "id": bundle_id.strip(),
                "module": "state_handoff",
            },
            "occurred_at": observed_at,
            "recorded_at": observed_at,
            "summary": f"Classify {len(items)} exact repository files as one reviewed cleanup bundle.",
            "payload": event_payload,
            "evidence": [
                {
                    "locator": relative_manifest.as_posix(),
                    "sha256": manifest_sha256,
                    "authority": "repository_document",
                    "observed_at": observed_at,
                }
            ],
            "supersedes": [],
            "review": {
                "required": True,
                "reason_codes": ["repository_item_batch_classification"],
                "status": "pending",
            },
        },
        schema_path=schema_path,
    )
