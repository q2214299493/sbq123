"""Typed workflow state and atomic JSON persistence."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ..exceptions import WorkflowError

StepStatus = Literal["PENDING", "RUNNING", "SUCCESS", "FAILED"]
WorkflowStatus = Literal["RUNNING", "SUCCESS", "FAILED"]
_STEP_STATUSES = {"PENDING", "RUNNING", "SUCCESS", "FAILED"}
_WORKFLOW_STATUSES = {"RUNNING", "SUCCESS", "FAILED"}


def _now() -> str:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


@dataclass
class StepState:
    """Status and timestamps for one ordered workflow step."""

    name: str
    status: StepStatus = "PENDING"
    start_time: str | None = None
    end_time: str | None = None
    error_message: str | None = None

    @classmethod
    def from_dict(cls, raw: object) -> StepState:
        """Validate one stored step record."""

        if not isinstance(raw, dict):
            raise WorkflowError("WORKFLOW_STATE_INVALID_STEP")
        name = raw.get("name")
        status = raw.get("status")
        if not isinstance(name, str) or not name or status not in _STEP_STATUSES:
            raise WorkflowError("WORKFLOW_STATE_INVALID_STEP")
        return cls(
            name=name,
            status=status,
            start_time=_optional_text(raw.get("start_time")),
            end_time=_optional_text(raw.get("end_time")),
            error_message=_optional_text(raw.get("error_message")),
        )


@dataclass
class WorkflowState:
    """Persistent state for one non-branching workflow execution."""

    workflow_id: str
    current_step: str
    status: WorkflowStatus
    steps: list[StepState]
    start_time: str
    end_time: str | None = None
    failed_step: str | None = None
    error_message: str | None = None

    @classmethod
    def create(cls, step_names: tuple[str, ...]) -> WorkflowState:
        """Create a new RUNNING state with all steps pending."""

        return cls(
            workflow_id=uuid.uuid4().hex,
            current_step="",
            status="RUNNING",
            steps=[StepState(name=name) for name in step_names],
            start_time=_now(),
        )

    @classmethod
    def from_dict(cls, raw: object) -> WorkflowState:
        """Validate a stored workflow state without inventing fields."""

        if not isinstance(raw, dict):
            raise WorkflowError("WORKFLOW_STATE_ROOT_NOT_OBJECT")
        workflow_id = raw.get("workflow_id")
        current_step = raw.get("current_step")
        status = raw.get("status")
        start_time = raw.get("start_time")
        steps_raw = raw.get("steps")
        if (
            not isinstance(workflow_id, str)
            or not workflow_id
            or not isinstance(current_step, str)
            or status not in _WORKFLOW_STATUSES
            or not isinstance(start_time, str)
            or not start_time
            or not isinstance(steps_raw, list)
        ):
            raise WorkflowError("WORKFLOW_STATE_INVALID")
        steps = [StepState.from_dict(item) for item in steps_raw]
        names = [step.name for step in steps]
        if not names or len(names) != len(set(names)):
            raise WorkflowError("WORKFLOW_STATE_INVALID_STEPS")
        state = cls(
            workflow_id=workflow_id,
            current_step=current_step,
            status=status,
            steps=steps,
            start_time=start_time,
            end_time=_optional_text(raw.get("end_time")),
            failed_step=_optional_text(raw.get("failed_step")),
            error_message=_optional_text(raw.get("error_message")),
        )
        state._validate_consistency()
        return state

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable state record."""

        return asdict(self)

    def step(self, name: str) -> StepState:
        """Return one named step or fail on a corrupt pipeline definition."""

        for item in self.steps:
            if item.name == name:
                return item
        raise WorkflowError(f"WORKFLOW_STEP_NOT_FOUND: {name}")

    def _validate_consistency(self) -> None:
        """Reject contradictory or out-of-order stored state."""

        running = [step for step in self.steps if step.status == "RUNNING"]
        failed = [step for step in self.steps if step.status == "FAILED"]
        open_step_seen = False
        for step in self.steps:
            if step.status == "SUCCESS" and open_step_seen:
                raise WorkflowError("WORKFLOW_STATE_OUT_OF_ORDER")
            if step.status != "SUCCESS":
                open_step_seen = True
        if len(running) > 1 or len(failed) > 1:
            raise WorkflowError("WORKFLOW_STATE_INCONSISTENT")
        if self.status == "SUCCESS" and (
            self.current_step or any(step.status != "SUCCESS" for step in self.steps)
        ):
            raise WorkflowError("WORKFLOW_STATE_INCONSISTENT_SUCCESS")
        if self.status == "FAILED" and (
            len(failed) != 1
            or self.failed_step != failed[0].name
            or self.current_step != failed[0].name
        ):
            raise WorkflowError("WORKFLOW_STATE_INCONSISTENT_FAILURE")
        if self.status == "RUNNING" and failed:
            raise WorkflowError("WORKFLOW_STATE_INCONSISTENT_RUNNING")
        if running and self.current_step != running[0].name:
            raise WorkflowError("WORKFLOW_STATE_INCONSISTENT_CURRENT_STEP")

    def start_step(self, name: str) -> None:
        """Mark one pending step running."""

        step = self.step(name)
        if self.status != "RUNNING" or step.status != "PENDING":
            raise WorkflowError(f"WORKFLOW_STEP_NOT_PENDING: {name}")
        self.current_step = name
        step.status = "RUNNING"
        step.start_time = _now()

    def complete_step(self, name: str) -> None:
        """Mark the current running step successful."""

        step = self.step(name)
        if step.status != "RUNNING":
            raise WorkflowError(f"WORKFLOW_STEP_NOT_RUNNING: {name}")
        step.status = "SUCCESS"
        step.end_time = _now()

    def fail_step(self, name: str, message: str) -> None:
        """Mark the workflow and current step failed."""

        step = self.step(name)
        step.status = "FAILED"
        step.end_time = _now()
        step.error_message = message
        self.current_step = name
        self.status = "FAILED"
        self.failed_step = name
        self.error_message = message
        self.end_time = step.end_time

    def complete(self) -> None:
        """Mark the workflow successful only when every step succeeded."""

        if any(step.status != "SUCCESS" for step in self.steps):
            raise WorkflowError("WORKFLOW_HAS_INCOMPLETE_STEPS")
        self.current_step = ""
        self.status = "SUCCESS"
        self.end_time = _now()


def _optional_text(value: object) -> str | None:
    """Validate one optional state text field."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkflowError("WORKFLOW_STATE_INVALID_TEXT_FIELD")
    return value


def save_workflow_state(state: WorkflowState, path: str | Path) -> Path:
    """Atomically write the latest workflow state."""

    target = Path(path).expanduser().resolve()
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except (OSError, TypeError, ValueError) as exc:
        raise WorkflowError(f"WORKFLOW_STATE_WRITE_ERROR: {target}") from exc
    return target


def load_workflow_state(path: str | Path) -> WorkflowState:
    """Load and validate an existing workflow state file."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise WorkflowError(f"WORKFLOW_STATE_NOT_FOUND: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"WORKFLOW_STATE_INVALID_JSON: {source}") from exc
    except OSError as exc:
        raise WorkflowError(f"WORKFLOW_STATE_READ_ERROR: {source}") from exc
    return WorkflowState.from_dict(raw)
