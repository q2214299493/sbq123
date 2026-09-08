from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from scripts.artifact_io import canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "configs" / "state_handoff_event.schema.json"

EVENT_ENTITY_KINDS = {
    "task_opened": "task",
    "task_updated": "task",
    "task_acceptance_recorded": "task_acceptance",
    "task_completed": "task",
    "state_observed": "state",
    "module_gate_changed": "module",
    "backlog_item_added": "backlog",
    "backlog_item_closed": "backlog",
    "error_opened": "error",
    "error_resolved": "error",
    "decision_recorded": "decision",
    "history_recorded": "history",
    "repository_item_classified": "repository_item",
    "repository_item_archived": "repository_item",
    "repository_item_deleted": "repository_item",
    "baseline_adopted": "state",
    "lifecycle_views_adopted": "state",
    "state_history_compacted": "state",
    "review_decision": "proposal",
}

ALWAYS_REVIEW_EVENT_TYPES = {
    "decision_recorded",
    "error_opened",
    "error_resolved",
    "backlog_item_added",
    "backlog_item_closed",
    "history_recorded",
    "repository_item_classified",
    "repository_item_archived",
    "repository_item_deleted",
    "baseline_adopted",
    "lifecycle_views_adopted",
    "state_history_compacted",
}

SCIENTIFIC_CLAIM_KEYS = {
    "accepted",
    "barrier",
    "converged",
    "grade",
    "scientific_acceptance",
    "transition_state",
    "validated_ts",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value}")
    return parsed


def _contains_scientific_claim(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).strip().lower() in SCIENTIFIC_CLAIM_KEYS:
                return True
            if _contains_scientific_claim(item):
                return True
    elif isinstance(value, list):
        return any(_contains_scientific_claim(item) for item in value)
    return False


def validate_event(
    payload: Mapping[str, Any],
    *,
    schema_path: Path = DEFAULT_SCHEMA,
) -> dict[str, Any]:
    """Validate and normalize one immutable state event."""

    normalized = json.loads(json.dumps(payload))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(normalized), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"invalid state event: {details}")

    parse_datetime(normalized["occurred_at"])
    parse_datetime(normalized["recorded_at"])
    event_type = normalized["event_type"]
    expected_kind = EVENT_ENTITY_KINDS[event_type]
    if normalized["entity"]["kind"] != expected_kind:
        raise ValueError(
            f"event_type {event_type} requires entity.kind={expected_kind}"
        )
    if normalized["event_id"] in normalized["supersedes"]:
        raise ValueError("an event cannot supersede itself")

    review = normalized["review"]
    if review["required"] and review["status"] != "pending":
        raise ValueError("review-required events must start with pending status")
    if not review["required"] and review["status"] != "not_required":
        raise ValueError("review-free events must use not_required status")
    if event_type in ALWAYS_REVIEW_EVENT_TYPES and not review["required"]:
        raise ValueError(f"{event_type} always requires user review")
    if event_type == "task_acceptance_recorded" and review["required"]:
        raise ValueError(
            "task acceptance is a factual checkpoint record; request review on its closure proposal"
        )
    if _contains_scientific_claim(normalized["payload"]) and not review["required"]:
        raise ValueError("events containing scientific claims require user review")

    _validate_payload(normalized)
    if event_type == "task_acceptance_recorded":
        _validate_acceptance_evidence_bindings(normalized)
    return normalized


def _validate_payload(event: Mapping[str, Any]) -> None:
    event_type = str(event["event_type"])
    payload = event["payload"]
    validators = {
        "task_opened": _validate_task_payload,
        "task_updated": _validate_task_payload,
        "task_acceptance_recorded": _validate_task_acceptance_payload,
        "task_completed": _validate_completed_task_payload,
        "state_observed": _validate_state_payload,
        "module_gate_changed": _validate_module_payload,
        "backlog_item_added": _validate_markdown_payload,
        "backlog_item_closed": _validate_markdown_payload,
        "error_opened": _validate_markdown_payload,
        "error_resolved": _validate_markdown_payload,
        "decision_recorded": _validate_markdown_payload,
        "history_recorded": _validate_markdown_payload,
        "review_decision": _validate_review_payload,
        "repository_item_classified": _validate_classified_repository_item_payload,
        "repository_item_archived": _validate_repository_item_payload,
        "repository_item_deleted": _validate_repository_item_payload,
        "baseline_adopted": _validate_baseline_payload,
        "lifecycle_views_adopted": _validate_lifecycle_views_payload,
        "state_history_compacted": _validate_state_history_compaction_payload,
    }
    validator = validators.get(event_type)
    if validator is not None:
        validator(payload)


def _validate_lifecycle_views_payload(payload: Mapping[str, Any]) -> None:
    expected = ["backlog", "error_log", "decisions_log", "historical_results"]
    if payload.get("views") != expected:
        raise ValueError(f"lifecycle_views_adopted requires views={expected}")


def _validate_state_history_compaction_payload(payload: Mapping[str, Any]) -> None:
    required = {
        "source_path",
        "source_sha256",
        "section_heading",
        "history_heading",
        "archive_path",
        "replacement",
    }
    if set(payload) != required:
        raise ValueError("state_history_compacted payload fields are invalid")
    if payload["source_path"] != "docs/02_CURRENT_STATE.md":
        raise ValueError("state history compaction may only target docs/02_CURRENT_STATE.md")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_sha256"])):
        raise ValueError("state history compaction source hash is invalid")
    if not str(payload["section_heading"]).startswith("## "):
        raise ValueError("state history compaction requires a level-2 section")
    if not str(payload["history_heading"]).startswith("### "):
        raise ValueError("state history compaction requires a level-3 history heading")
    archive = Path(str(payload["archive_path"]))
    if archive.is_absolute() or archive.suffix.lower() != ".md":
        raise ValueError("state history archive must be a repository-relative Markdown file")
    if archive.parts[:2] != ("docs", "history") or ".." in archive.parts:
        raise ValueError("state history archive must be under docs/history")
    if not str(payload["replacement"]).strip():
        raise ValueError("state history compaction replacement must be non-empty")


def _validate_task_payload(payload: Mapping[str, Any]) -> None:
    required = {"objective", "one_executable_step", "done_when"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"task payload missing: {sorted(missing)}")
    if not isinstance(payload["done_when"], list) or not payload["done_when"]:
        raise ValueError("task done_when must be a non-empty list")
    if "submission_boundary" in payload and not str(payload["submission_boundary"]).strip():
        raise ValueError("task submission_boundary must be non-empty when present")
    if "phase" in payload and payload["phase"] not in {"open", "active", "blocked", "verification"}:
        raise ValueError("task phase is invalid")
    transition = payload.get("lifecycle_transition")
    if transition is not None:
        if not isinstance(transition, Mapping):
            raise ValueError("task lifecycle_transition must be an object")
        required_transition = {
            "from_phase", "to_phase", "reason", "source_event_id", "source_event_sha256"
        }
        if set(transition) != required_transition:
            raise ValueError("task lifecycle_transition fields are invalid")
        if transition["to_phase"] != payload.get("phase"):
            raise ValueError("task lifecycle_transition to_phase must equal task phase")
        if not str(transition["reason"]).strip():
            raise ValueError("task lifecycle_transition requires reason")
        if not re.fullmatch(r"[0-9a-f]{64}", str(transition["source_event_sha256"])):
            raise ValueError("task lifecycle_transition source hash is invalid")


def _validate_completed_task_payload(payload: Mapping[str, Any]) -> None:
    required = {
        "completion_summary",
        "task_event_id",
        "task_event_sha256",
        "acceptance_event_id",
        "acceptance_event_sha256",
        "handoff",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"task_completed payload missing: {sorted(missing)}")
    if not str(payload["completion_summary"]).strip():
        raise ValueError("task_completed requires completion_summary")
    for key in ("task_event_sha256", "acceptance_event_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(payload[key])):
            raise ValueError(f"{key} must be a lowercase SHA-256 digest")
    _validate_task_handoff(payload["handoff"], requires_user_review=True)


def _evidence_references(value: Mapping[str, Any], *, label: str) -> list[str]:
    references = value.get("evidence_sha256")
    if not isinstance(references, list) or not references:
        raise ValueError(f"{label} requires non-empty evidence_sha256")
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in references):
        raise ValueError(f"{label} evidence_sha256 contains an invalid digest")
    return [str(item) for item in references]


def _validate_task_acceptance_payload(payload: Mapping[str, Any]) -> None:
    required = {
        "task_entity_id",
        "task_event_id",
        "task_event_sha256",
        "completion_summary",
        "done_when_results",
        "validation_results",
        "artifact_policy",
        "artifacts",
        "risk_assessment",
        "handoff",
        "requires_user_review",
        "verdict",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"task acceptance payload missing: {sorted(missing)}")
    if payload["verdict"] != "accepted":
        raise ValueError("task acceptance verdict must be accepted before task closure")
    if not str(payload["completion_summary"]).strip():
        raise ValueError("task acceptance requires completion_summary")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["task_event_sha256"])):
        raise ValueError("task_event_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(payload["requires_user_review"], bool):
        raise ValueError("requires_user_review must be boolean")
    review_reasons = payload.get("review_reason_codes", [])
    if not isinstance(review_reasons, list) or any(
        not str(item).strip() for item in review_reasons
    ):
        raise ValueError("review_reason_codes must be a list of non-empty strings")
    _validate_done_when_results(payload["done_when_results"])
    _validate_validation_results(payload["validation_results"])
    _validate_artifact_results(payload)
    _validate_risk_assessment(payload)
    _validate_task_handoff(
        payload["handoff"],
        requires_user_review=payload["requires_user_review"],
        risk_status=str(payload["risk_assessment"]["status"]),
    )


def _non_empty_text(value: Mapping[str, Any], key: str, *, label: str) -> str:
    text = str(value.get(key, "")).strip()
    if not text:
        raise ValueError(f"{label} requires {key}")
    if "<!-- state-handoff:" in text:
        raise ValueError(f"{label}.{key} contains a reserved state-handoff marker")
    return text


def _validate_handoff_evidence(value: Mapping[str, Any], *, label: str) -> None:
    _evidence_references(value, label=label)


def _validate_handoff_collection(collection: str, items: Any) -> None:
    required_fields = {
        "backlog_items": ("id", "summary", "next_action", "done_when"),
        "errors": ("id", "summary", "impact", "next_action", "owner"),
        "decisions": ("id", "title", "decision", "reason", "consequence"),
    }
    allowed_fields = {
        "backlog_items": {
            "id", "priority", "category", "module", "summary", "next_action",
            "done_when", "evidence_sha256",
        },
        "errors": {
            "id", "summary", "impact", "next_action", "owner", "evidence_sha256",
        },
        "decisions": {
            "id", "title", "decision", "reason", "consequence", "evidence_sha256",
        },
    }
    if not isinstance(items, list):
        raise ValueError(f"task handoff {collection} must be a list")
    identifiers: set[str] = set()
    for index, item in enumerate(items):
        label = f"task handoff {collection}[{index}]"
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} must be an object")
        if not set(item) <= allowed_fields[collection]:
            raise ValueError(f"{label} has unsupported fields")
        for key in required_fields[collection]:
            _non_empty_text(item, key, label=label)
        identifier = str(item["id"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}", identifier):
            raise ValueError(f"{label}.id has an invalid stable identifier")
        if identifier in identifiers:
            raise ValueError(f"task handoff {collection} contains duplicate id: {identifier}")
        identifiers.add(identifier)
        _validate_handoff_evidence(item, label=label)
        if collection == "backlog_items":
            _validate_backlog_handoff_item(item, label=label)


def _validate_backlog_handoff_item(item: Mapping[str, Any], *, label: str) -> None:
    if item.get("priority") not in {"P1", "P2", "P3"}:
        raise ValueError(f"{label} has invalid priority")
    if item.get("category") not in {"Infrastructure", "Scientific Work"}:
        raise ValueError(f"{label} has invalid category")
    module = item.get("module")
    if module is not None and not str(module).strip():
        raise ValueError(f"{label}.module must be non-empty when present")


def _validate_task_handoff(
    handoff: Any,
    *,
    requires_user_review: bool,
    risk_status: str | None = None,
) -> None:
    if not isinstance(handoff, Mapping):
        raise ValueError("task handoff must be an object")
    required = {"history", "backlog_items", "errors", "decisions"}
    missing = required - set(handoff)
    if missing:
        raise ValueError(f"task handoff missing: {sorted(missing)}")
    extra = set(handoff) - required
    if extra:
        raise ValueError(f"task handoff has unsupported fields: {sorted(extra)}")

    history = handoff["history"]
    if not isinstance(history, Mapping):
        raise ValueError("task handoff history must be an object")
    history_fields = {"title", "summary", "outcome", "evidence_sha256"}
    if set(history) != history_fields:
        raise ValueError("task handoff history fields are invalid")
    for key in ("title", "summary", "outcome"):
        _non_empty_text(history, key, label="task handoff history")
    _validate_handoff_evidence(history, label="task handoff history")

    for collection in ("backlog_items", "errors", "decisions"):
        _validate_handoff_collection(collection, handoff[collection])

    if handoff["errors"]:
        if risk_status is not None and risk_status != "accepted_open_risks":
            raise ValueError("handoff errors require accepted_open_risks")
        if not requires_user_review:
            raise ValueError("handoff errors require user review")
    if handoff["decisions"] and not requires_user_review:
        raise ValueError("handoff decisions require user review")


def _validate_done_when_results(done_when: Any) -> None:
    if not isinstance(done_when, list) or not done_when:
        raise ValueError("task acceptance requires done_when_results")
    for index, result in enumerate(done_when):
        if not isinstance(result, Mapping) or not str(result.get("criterion", "")).strip():
            raise ValueError(f"done_when_results[{index}] requires criterion")
        if result.get("status") != "passed":
            raise ValueError(f"done_when_results[{index}] must be passed")
        _evidence_references(result, label=f"done_when_results[{index}]")


def _validate_validation_results(validations: Any) -> None:
    if not isinstance(validations, list) or not validations:
        raise ValueError("task acceptance requires validation_results")
    allowed_kinds = {"test", "inspection", "lint", "build"}
    for index, result in enumerate(validations):
        if not isinstance(result, Mapping):
            raise ValueError(f"validation_results[{index}] must be an object")
        if result.get("kind") not in allowed_kinds:
            raise ValueError(f"validation_results[{index}] has invalid kind")
        if not str(result.get("name", "")).strip() or not str(result.get("command", "")).strip():
            raise ValueError(f"validation_results[{index}] requires name and command")
        if result.get("status") != "passed" or result.get("exit_code") != 0:
            raise ValueError(f"validation_results[{index}] must pass with exit_code 0")
        _evidence_references(result, label=f"validation_results[{index}]")


def _validate_artifact_results(payload: Mapping[str, Any]) -> None:
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        raise ValueError("artifacts must be a list")
    artifact_policy = payload["artifact_policy"]
    if artifact_policy == "required":
        if not artifacts:
            raise ValueError("required artifact policy needs at least one artifact")
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, Mapping):
                raise ValueError(f"artifacts[{index}] must be an object")
            if artifact.get("status") != "present" or not str(artifact.get("path", "")).strip():
                raise ValueError(f"artifacts[{index}] must be present and have a path")
            digest = str(artifact.get("sha256", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"artifacts[{index}] requires sha256")
            if digest not in _evidence_references(artifact, label=f"artifacts[{index}]"):
                raise ValueError(f"artifacts[{index}] sha256 must be evidence-bound")
    elif artifact_policy == "none":
        if artifacts:
            raise ValueError("artifact_policy none requires an empty artifacts list")
        if not str(payload.get("no_artifacts_reason", "")).strip():
            raise ValueError("artifact_policy none requires no_artifacts_reason")
    else:
        raise ValueError("artifact_policy must be required or none")


def _validate_risk_assessment(payload: Mapping[str, Any]) -> None:
    risk = payload["risk_assessment"]
    if not isinstance(risk, Mapping):
        raise ValueError("risk_assessment must be an object")
    if risk.get("status") not in {"no_open_risks", "accepted_open_risks"}:
        raise ValueError("risk_assessment status is invalid")
    if not str(risk.get("summary", "")).strip():
        raise ValueError("risk_assessment requires summary")
    _evidence_references(risk, label="risk_assessment")
    if risk["status"] == "accepted_open_risks" and not payload["requires_user_review"]:
        raise ValueError("accepted open risks require user review")


def _validate_acceptance_evidence_bindings(event: Mapping[str, Any]) -> None:
    available = {str(item["sha256"]) for item in event["evidence"]}
    located = {
        (str(item["locator"]), str(item["sha256"])) for item in event["evidence"]
    }
    payload = event["payload"]
    referenced: set[str] = set()
    for result in payload["done_when_results"]:
        referenced.update(str(item) for item in result["evidence_sha256"])
    for result in payload["validation_results"]:
        referenced.update(str(item) for item in result["evidence_sha256"])
    for artifact in payload["artifacts"]:
        referenced.update(str(item) for item in artifact["evidence_sha256"])
    referenced.update(
        str(item) for item in payload["risk_assessment"]["evidence_sha256"]
    )
    handoff = payload["handoff"]
    referenced.update(str(item) for item in handoff["history"]["evidence_sha256"])
    for collection in ("backlog_items", "errors", "decisions"):
        for item in handoff[collection]:
            referenced.update(str(value) for value in item["evidence_sha256"])
    missing = referenced - available
    if missing:
        raise ValueError(
            f"task acceptance references evidence missing from the event envelope: {sorted(missing)}"
        )
    unbound_artifacts = [
        str(artifact["path"])
        for artifact in payload["artifacts"]
        if (str(artifact["path"]), str(artifact["sha256"])) not in located
    ]
    if unbound_artifacts:
        raise ValueError(
            "task acceptance artifacts lack exact path-and-hash evidence: "
            f"{sorted(unbound_artifacts)}"
        )


def _validate_state_payload(payload: Mapping[str, Any]) -> None:
    required = {"block_id", "section", "title", "facts"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"state payload missing: {sorted(missing)}")
    if not isinstance(payload["facts"], list) or not payload["facts"]:
        raise ValueError("state facts must be a non-empty list")


def _validate_module_payload(payload: Mapping[str, Any]) -> None:
    required = {"module", "status", "depends_on", "current_gate"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"module payload missing: {sorted(missing)}")
    if payload["status"] not in {"Planned", "Active", "Blocked", "Completed"}:
        raise ValueError("invalid module status")


def _validate_markdown_payload(payload: Mapping[str, Any]) -> None:
    if not str(payload.get("markdown", "")).strip():
        raise ValueError("log and history events require non-empty payload.markdown")


def _validate_review_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("decision") not in {"approve", "reject"}:
        raise ValueError("review_decision must be approve or reject")
    if not str(payload.get("proposal_id", "")).strip():
        raise ValueError("review_decision requires proposal_id")
    if not str(payload.get("reviewer", "")).strip():
        raise ValueError("review_decision requires reviewer")
    reviewed_event_id = payload.get("reviewed_event_id")
    reviewed_event_sha256 = payload.get("reviewed_event_sha256")
    if (reviewed_event_id is None) != (reviewed_event_sha256 is None):
        raise ValueError(
            "review_decision event linkage requires both reviewed_event_id and reviewed_event_sha256"
        )
    if payload.get("decision") == "reject" and reviewed_event_id is None:
        raise ValueError("reject review_decision requires reviewed event linkage")
    if reviewed_event_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", str(reviewed_event_sha256)
    ):
        raise ValueError("reviewed_event_sha256 must be a lowercase SHA-256 digest")


def _validate_repository_item_payload(payload: Mapping[str, Any]) -> None:
    if not str(payload.get("path", "")).strip():
        raise ValueError("repository item event requires path")


def _validate_repository_item_batch_entry(item: Mapping[str, Any]) -> tuple[str, str | None]:
    _validate_repository_item_payload(item)
    if item.get("disposition") not in {"archive", "delete", "move"}:
        raise ValueError("repository item batch disposition is invalid")
    if item.get("tracking_status") not in {"tracked", "untracked"}:
        raise ValueError("repository item batch tracking_status is invalid")
    if item.get("content_class") not in {"unique", "regenerable", "duplicate"}:
        raise ValueError("repository item batch content_class is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
        raise ValueError("repository item batch file hash is invalid")
    if not isinstance(item.get("size_bytes"), int) or item["size_bytes"] < 0:
        raise ValueError("repository item batch size is invalid")
    if not str(item.get("reason", "")).strip():
        raise ValueError("repository item batch entry requires reason")
    target = None
    if item.get("disposition") == "move":
        target = str(item.get("target_path", ""))
        if not target:
            raise ValueError("repository item batch move requires target_path")
    return str(item["path"]), target


def _validate_classified_repository_item_payload(payload: Mapping[str, Any]) -> None:
    items = payload.get("items")
    if items is not None:
        if not isinstance(items, list) or not items:
            raise ValueError("repository item batch requires a non-empty items list")
        if not str(payload.get("bundle_id", "")).strip():
            raise ValueError("repository item batch requires bundle_id")
        if not str(payload.get("manifest_path", "")).strip():
            raise ValueError("repository item batch requires manifest_path")
        if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("manifest_sha256", ""))):
            raise ValueError("repository item batch manifest hash is invalid")
        checked = [
            _validate_repository_item_batch_entry(item)
            for item in items
            if isinstance(item, Mapping)
        ]
        if len(checked) != len(items):
            raise ValueError("repository item batch entries must be objects")
        paths = [path for path, _ in checked]
        targets = [target for _, target in checked if target is not None]
        if len(paths) != len(set(paths)):
            raise ValueError("repository item batch paths must be unique")
        if len(targets) != len(set(targets)):
            raise ValueError("repository item batch move targets must be unique")
        return
    _validate_repository_item_payload(payload)
    if payload.get("disposition") not in {"keep", "archive", "delete"}:
        raise ValueError("repository item disposition must be keep, archive, or delete")
    if payload.get("tracking_status") not in {"tracked", "untracked"}:
        raise ValueError("repository item tracking_status must be tracked or untracked")
    if payload.get("content_class") not in {"unique", "regenerable", "duplicate"}:
        raise ValueError("repository item content_class is invalid")


def _validate_baseline_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload.get("task"), Mapping):
        raise ValueError("baseline_adopted requires task payload")
    _validate_task_payload(payload["task"])
    blocks = payload.get("state_blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("baseline_adopted requires state_blocks")
    for block in blocks:
        if not isinstance(block, Mapping):
            raise ValueError("baseline state block must be an object")
        _validate_state_payload(block)
        if not str(block.get("source_heading", "")).strip():
            raise ValueError("baseline state block requires source_heading")


@dataclass(frozen=True)
class StateEvent:
    payload: dict[str, Any]

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        schema_path: Path = DEFAULT_SCHEMA,
    ) -> "StateEvent":
        return cls(validate_event(payload, schema_path=schema_path))

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        schema_path: Path = DEFAULT_SCHEMA,
    ) -> "StateEvent":
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError(f"state event must be an object: {path}")
        return cls.from_mapping(value, schema_path=schema_path)

    @property
    def event_id(self) -> str:
        return str(self.payload["event_id"])

    @property
    def event_type(self) -> str:
        return str(self.payload["event_type"])

    @property
    def entity_key(self) -> tuple[str, str]:
        entity = self.payload["entity"]
        return str(entity["kind"]), str(entity["id"])

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.payload))

    @property
    def review_required(self) -> bool:
        return bool(self.payload["review"]["required"])
