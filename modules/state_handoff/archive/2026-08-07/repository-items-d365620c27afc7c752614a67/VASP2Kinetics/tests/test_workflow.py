"""Tests for Phase 10 ordered execution and persistent state."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.exceptions import WorkflowError
from src.workflow.pipeline import STEP_NAMES, WorkflowPipeline
from src.workflow.state import WorkflowState, save_workflow_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_case_config(case: Path) -> None:
    """Write a complete case-local configuration for CLI tests."""

    (case / "config.yaml").write_text(
        """
project: {name: VASP2Kinetics, version: 0.1.0}
paths: {data_path: data, output_path: ../output, raw_vasp_cases: vasp, processed_data: processed}
logging: {level: INFO, console: true, file: null, phase_files: {parser: logs/parser.log, simulation: logs/simulation.log, workflow: logs/workflow.log}}
validator: {energy_tolerance: 0.05, allowed_elements: [C, H, O, Fe]}
catkinas: {input_path: processed/kinetic_dataset.json, output_path: catkinas_project, allow_warning: true}
zacros: {surface_config: surface.yaml, output_path: zacros_project, allow_warning: true}
simulation: {catkinas_command: catkinas, zacros_command: zacros, timeout: 5}
analysis: {result_path: results, output_path: results}
report: {output_path: report, template_path: report_template.md}
workflow: {software: CATKINAS, output_root: ../output}
""".lstrip(),
        encoding="utf-8",
    )


class FakeExecutor:
    """Record scheduled calls and optionally fail at one explicit step."""

    def __init__(self, failed_step: str | None = None) -> None:
        self.failed_step = failed_step
        self.calls: list[str] = []

    def execute_step(self, name: str) -> None:
        self.calls.append(name)
        if name == self.failed_step:
            raise WorkflowError(f"controlled failure: {name}")


class WorkflowPipelineTests(unittest.TestCase):
    """Verify success, fail-fast behavior, and safe restoration."""

    def _run_failure(self, failed_step: str) -> tuple[WorkflowState, FakeExecutor]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        executor = FakeExecutor(failed_step)
        state = WorkflowPipeline(Path(directory.name), executor).execute()
        return state, executor

    def test_complete_successful_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            executor = FakeExecutor()

            state = WorkflowPipeline(output, executor).execute()
            stored = json.loads(
                (output / "workflow_state.json").read_text(encoding="utf-8")
            )

        self.assertEqual(state.status, "SUCCESS")
        self.assertEqual(executor.calls, list(STEP_NAMES))
        self.assertTrue(all(step.status == "SUCCESS" for step in state.steps))
        self.assertEqual(stored["status"], "SUCCESS")

    def test_vasp_failure_stops_workflow(self) -> None:
        state, executor = self._run_failure("vasp_parser")

        self.assertEqual(state.status, "FAILED")
        self.assertEqual(state.failed_step, "vasp_parser")
        self.assertEqual(executor.calls, ["vasp_parser"])

    def test_validation_failure_stops_workflow(self) -> None:
        state, executor = self._run_failure("validator")

        self.assertEqual(state.failed_step, "validator")
        self.assertEqual(executor.calls, list(STEP_NAMES[:3]))
        self.assertEqual(state.step("input_generator").status, "PENDING")

    def test_simulation_failure_stops_workflow(self) -> None:
        state, executor = self._run_failure("simulation_runner")

        self.assertEqual(state.failed_step, "simulation_runner")
        self.assertEqual(executor.calls, list(STEP_NAMES[:5]))
        self.assertEqual(state.step("result_parser").status, "PENDING")

    def test_restores_successful_steps_and_runs_pending_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            state = WorkflowState.create(STEP_NAMES)
            for name in STEP_NAMES[:2]:
                state.start_step(name)
                state.complete_step(name)
            save_workflow_state(state, output / "workflow_state.json")
            executor = FakeExecutor()

            restored = WorkflowPipeline(output, executor).execute()

        self.assertEqual(restored.status, "SUCCESS")
        self.assertEqual(executor.calls, list(STEP_NAMES[2:]))


class WorkflowStatusCommandTests(unittest.TestCase):
    """Verify the read-only workflow status command."""

    def test_status_command_prints_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case = root / "cases" / "example"
            case.mkdir(parents=True)
            _write_case_config(case)
            output = case.parent / "output" / case.name
            state = WorkflowState.create(STEP_NAMES)
            save_workflow_state(state, output / "workflow_state.json")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "main.py"),
                    "--workflow-status",
                    "--case",
                    str(case),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        displayed = json.loads(completed.stdout)
        self.assertEqual(displayed["workflow_id"], state.workflow_id)
        self.assertEqual(displayed["status"], "RUNNING")

    def test_workflow_cli_records_real_vasp_parser_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case = root / "cases" / "missing_outcar"
            (case / "vasp").mkdir(parents=True)
            _write_case_config(case)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "main.py"),
                    "--workflow",
                    "--case",
                    str(case),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            state_path = case.parent / "output" / case.name / "workflow_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(state["status"], "FAILED")
        self.assertEqual(state["failed_step"], "vasp_parser")
        self.assertEqual(state["steps"][1]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
