from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from scripts.artifact_io import sha256_file

from .models import StateEvent


def _inside(root: Path, value: str, *, require_file: bool = True) -> Path | None:
    path = Path(value)
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    if require_file and not resolved.is_file():
        return None
    return resolved


def _registration_summary(event: StateEvent, root: Path) -> dict[str, Any] | None:
    for evidence in event.payload["evidence"]:
        if evidence["authority"] != "calculation_registry":
            continue
        if Path(str(evidence["locator"])).name != "registration_summary.json":
            continue
        path = _inside(root, str(evidence["locator"]))
        if path is None or sha256_file(path) != evidence["sha256"]:
            return None
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None
    return None


def registry_excel_review_is_reusable(
    event: StateEvent,
    actions: list[dict[str, Any]],
    *,
    project_root: Path,
    policy: dict[str, Any],
) -> bool:
    """Verify that a scientific event only projects an already reviewed result."""

    config = policy.get("registry_excel_review_reuse", {})
    if not config.get("enabled") or event.event_type not in set(config.get("allowed_event_types", [])):
        return False
    if "scientific_result_registration" not in event.payload["review"]["reason_codes"]:
        return False
    allowed_targets = set(config.get("allowed_targets", [])) | {policy["paths"]["projection_manifest"]}
    if not actions or any(action["action_type"] != "write_text" or action["target_path"] not in allowed_targets for action in actions):
        return False
    summary = _registration_summary(event, project_root)
    if summary is None or summary.get("status") != "REGISTERED" or not summary.get("barrier_set_id"):
        return False
    database = _inside(project_root, str(config.get("database", "")))
    if database is None:
        return False
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT b.barrier_set_id, b.validation_status, v.grade, v.kinetic_eligible,
                   p.workbook_path, p.workbook_sha256_after, p.written_values_sha256,
                   p.reviewer, p.reviewed_at, p.receipt_path, p.registry_id
            FROM ts_barriers AS b
            JOIN ts_validations AS v ON v.ts_validation_id=b.ts_validation_id
            JOIN excel_promotions AS p
              ON p.promotion_kind='barrier' AND p.registry_id=b.barrier_set_id
            WHERE b.barrier_set_id=?
            """,
            (summary["barrier_set_id"],),
        ).fetchone()
    if row is None:
        return False
    record = dict(row)
    if record["validation_status"] != "accepted" or record["grade"] != "A" or record["kinetic_eligible"] != 1:
        return False
    if record["reviewer"] not in set(config.get("trusted_reviewers", [])) or not record["reviewed_at"]:
        return False
    workbook = _inside(project_root, str(record["workbook_path"]))
    receipt_path = _inside(project_root, str(record["receipt_path"]))
    if workbook is None or receipt_path is None or sha256_file(workbook) != record["workbook_sha256_after"]:
        return False
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if not isinstance(receipt, dict):
        return False
    return all(
        (
            receipt.get("registry_id") == record["registry_id"],
            receipt.get("reviewer") == record["reviewer"],
            receipt.get("reviewed_at") == record["reviewed_at"],
            receipt.get("workbook_sha256_after") == record["workbook_sha256_after"],
            receipt.get("written_values_sha256") == record["written_values_sha256"],
        )
    )
