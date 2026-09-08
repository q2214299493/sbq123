from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_text

from .models import ROOT, StateEvent
from .projections import DEFAULT_POLICY, load_policy


VIEW_NAMES = ["backlog", "error_log", "decisions_log", "historical_results"]


def build_lifecycle_views_adoption_event(
    project_root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
) -> StateEvent:
    root = project_root.resolve()
    policy = load_policy(policy_path)
    paths = [root / policy["managed_views"][name] for name in VIEW_NAMES]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"lifecycle view is missing: {missing[0]}")
    hashes = [sha256_file(path) for path in paths]
    latest_mtime = max(path.stat().st_mtime for path in paths)
    observed_at = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    digest = sha256_text(":".join(hashes))
    evidence = [
        {
            "locator": path.relative_to(root).as_posix(),
            "sha256": digest_value,
            "authority": "repository_document",
            "observed_at": observed_at,
        }
        for path, digest_value in zip(paths, hashes, strict=True)
    ]
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"lifecycle-views-adopted-{digest[:24]}",
            "event_type": "lifecycle_views_adopted",
            "entity": {
                "kind": "state",
                "id": "managed-lifecycle-views",
                "module": "state_handoff",
            },
            "occurred_at": observed_at,
            "recorded_at": observed_at,
            "summary": "Adopt the four task lifecycle views without changing legacy content.",
            "payload": {"views": VIEW_NAMES},
            "evidence": evidence,
            "supersedes": [],
            "review": {
                "required": True,
                "reason_codes": ["initial_managed_view_adoption"],
                "status": "pending",
            },
        }
    )
