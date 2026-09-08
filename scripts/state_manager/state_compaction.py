from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_text

from .models import ROOT, StateEvent


def build_state_history_compaction_event(
    *,
    project_root: Path = ROOT,
    section_heading: str,
    archive_path: str,
    history_heading: str = "### Historical Evidence",
) -> StateEvent:
    root = project_root.resolve()
    source = root / "docs" / "02_CURRENT_STATE.md"
    text = source.read_text(encoding="utf-8")
    source_sha256 = sha256_file(source)
    section_matches = list(re.finditer(rf"(?m)^{re.escape(section_heading)}\s*$", text))
    if len(section_matches) != 1:
        raise ValueError(f"section must occur exactly once: {section_heading}")
    section_start = section_matches[0].start()
    next_section = re.search(r"(?m)^## ", text[section_matches[0].end() :])
    section_end = (
        section_matches[0].end() + next_section.start() if next_section else len(text)
    )
    section = text[section_start:section_end]
    history_matches = list(re.finditer(rf"(?m)^{re.escape(history_heading)}\s*$", section))
    if len(history_matches) != 1:
        raise ValueError(f"history subsection must occur exactly once: {history_heading}")
    digest = sha256_text(f"{source_sha256}:{section_heading}:{archive_path}")
    observed_at = datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", section)
    occurred_at = (
        f"{date_match.group(1)}T00:00:00+08:00" if date_match else observed_at
    )
    replacement = (
        f"{history_heading}\n\n"
        f"The detailed chronology through the current gate was moved intact to "
        f"`{archive_path}`.\n\n"
        "Current status and the next executable action are maintained only in the "
        "managed Current Gate above."
    )
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"state-history-compacted-{digest[:24]}",
            "event_type": "state_history_compacted",
            "entity": {
                "kind": "state",
                "id": "current-state-history-compaction",
                "module": "state_handoff",
            },
            "occurred_at": occurred_at,
            "recorded_at": observed_at,
            "summary": f"Move historical flow out of {section_heading}.",
            "payload": {
                "source_path": "docs/02_CURRENT_STATE.md",
                "source_sha256": source_sha256,
                "section_heading": section_heading,
                "history_heading": history_heading,
                "archive_path": archive_path,
                "replacement": replacement,
            },
            "evidence": [
                {
                    "locator": "docs/02_CURRENT_STATE.md",
                    "sha256": source_sha256,
                    "authority": "repository_document",
                    "observed_at": observed_at,
                }
            ],
            "supersedes": [],
            "review": {
                "required": True,
                "reason_codes": [
                    "create_history_archive",
                    "modify_unmanaged_markdown",
                ],
                "status": "pending",
            },
        }
    )
