"""Ordered, fail-fast workflow pipeline over existing project modules."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from ..config import AppConfig
from ..exceptions import VASP2KineticsError, WorkflowError
from ..logging_context import phase_log
from .executor import WorkflowExecutor
from .state import WorkflowState, load_workflow_state, save_workflow_state

LOGGER = logging.getLogger("vasp2kinetics.workflow")
STEP_NAMES = (
    "vasp_parser",
    "kinetic_builder",
    "validator",
    "input_generator",
    "simulation_runner",
    "result_parser",
    "analysis_report",
)


class StepExecutor(Protocol):
    """Minimal execution interface used by the pipeline and tests."""

    def execute_step(self, name: str) -> None:
        """Execute one named step or raise an exception."""


class WorkflowPipeline:
    """Run ordered steps, persist every transition, and stop on first failure."""

    def __init__(self, output_path: str | Path, executor: StepExecutor) -> None:
        """Bind one output directory and step executor."""

        self.output_path = Path(output_path).expanduser().resolve()
        self.state_path = self.output_path / "workflow_state.json"
        self.executor = executor

    def _initial_state(self) -> WorkflowState:
        """Create or strictly load the persisted state."""

        if not self.state_path.exists():
            state = WorkflowState.create(STEP_NAMES)
            save_workflow_state(state, self.state_path)
            return state
        state = load_workflow_state(self.state_path)
        if tuple(step.name for step in state.steps) != STEP_NAMES:
            raise WorkflowError("WORKFLOW_STATE_STEP_ORDER_MISMATCH")
        return state

    def execute(self) -> WorkflowState:
        """Execute pending steps and return the final persisted state."""

        state = self._initial_state()
        LOGGER.info(
            "Workflow started: id=%s status=%s output=%s",
            state.workflow_id,
            state.status,
            self.output_path,
        )
        if state.status in {"SUCCESS", "FAILED"}:
            LOGGER.info(
                "Workflow not executed because stored status is terminal: %s",
                state.status,
            )
            return state

        interrupted = next(
            (step for step in state.steps if step.status == "RUNNING"),
            None,
        )
        if interrupted is not None:
            message = "INTERRUPTED_STEP_REQUIRES_MANUAL_REVIEW"
            state.fail_step(interrupted.name, message)
            save_workflow_state(state, self.state_path)
            LOGGER.error("Workflow interrupted at %s", interrupted.name)
            LOGGER.error("Workflow ended: id=%s status=FAILED", state.workflow_id)
            return state

        for step_name in STEP_NAMES:
            step = state.step(step_name)
            if step.status == "SUCCESS":
                continue
            if step.status != "PENDING":
                raise WorkflowError(f"WORKFLOW_STATE_INVALID_STEP_STATUS: {step_name}")

            state.start_step(step_name)
            save_workflow_state(state, self.state_path)
            LOGGER.info("Workflow step started: %s", step_name)
            try:
                self.executor.execute_step(step_name)
            except Exception as exc:  # Persist unexpected failures before returning.
                message = f"{type(exc).__name__}: {exc}"
                state.fail_step(step_name, message)
                save_workflow_state(state, self.state_path)
                LOGGER.error(
                    "Workflow step failed: step=%s error=%s",
                    step_name,
                    message,
                )
                LOGGER.error(
                    "Workflow ended: id=%s status=FAILED",
                    state.workflow_id,
                )
                return state

            state.complete_step(step_name)
            save_workflow_state(state, self.state_path)
            LOGGER.info("Workflow step succeeded: %s", step_name)

        state.complete()
        save_workflow_state(state, self.state_path)
        LOGGER.info("Workflow ended: id=%s status=SUCCESS", state.workflow_id)
        return state


def case_output_path(case_path: Path, config: AppConfig) -> Path:
    """Resolve the configured output root plus the explicit case name."""

    return config.workflow.output_root / case_path.name


def run_workflow(case: str | Path, config: AppConfig, logger: logging.Logger) -> int:
    """Run or safely resume one case workflow."""

    case_path = Path(case).expanduser().resolve()
    if not case_path.is_dir():
        logger.error("WORKFLOW_CASE_NOT_FOUND: %s", case_path)
        return 2
    output = case_output_path(case_path, config)
    executor = WorkflowExecutor(case_path, output, config)
    pipeline = WorkflowPipeline(output, executor)
    try:
        with phase_log(logger, config.logging.phase_files.workflow):
            state = pipeline.execute()
    except VASP2KineticsError as exc:
        logger.error("%s", exc)
        return 2
    return 0 if state.status == "SUCCESS" else 1


def show_workflow_status(
    case: str | Path,
    config: AppConfig,
    logger: logging.Logger,
) -> int:
    """Print one persisted workflow state without changing it."""

    case_path = Path(case).expanduser().resolve()
    state_path = case_output_path(case_path, config) / "workflow_state.json"
    try:
        state = load_workflow_state(state_path)
    except WorkflowError as exc:
        logger.error("%s", exc)
        return 2
    print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    return 0
