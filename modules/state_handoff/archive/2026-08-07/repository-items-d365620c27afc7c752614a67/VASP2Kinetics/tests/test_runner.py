"""Tests for Phase 7 external simulation process management."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.runner.catkinas_runner import CatkinasRunner
from src.runner.zacros_runner import ZacrosRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _runner_paths(root: Path, name: str) -> tuple[Path, Path]:
    return root / name, root / "execution_history.json"


class RunnerTests(unittest.TestCase):
    """Cover process success and every required explicit failure state."""

    def test_normal_external_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input"
            input_path.mkdir()
            sentinel = input_path / "sentinel.dat"
            sentinel.write_text("unchanged\n", encoding="utf-8")
            output, history = _runner_paths(root, "catkinas_run")
            runner = CatkinasRunner(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.getcwd())",
                ],
                5,
                output,
                history,
            )

            result = runner.run(input_path)
            status = json.loads(
                (output / "run_status.json").read_text(encoding="utf-8")
            )
            execution_history = json.loads(history.read_text(encoding="utf-8"))

            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(result.return_code, 0)
            self.assertIn(str(input_path.resolve()), result.stdout.strip())
            self.assertEqual((output / "stdout.log").read_text(), result.stdout)
            self.assertEqual((output / "stderr.log").read_text(), result.stderr)
            self.assertEqual(status["status"], "SUCCESS")
            self.assertEqual(status["software"], "CATKINAS")
            self.assertEqual(len(execution_history), 1)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged\n")

    def test_executable_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input"
            input_path.mkdir()
            output, history = _runner_paths(root, "catkinas_run")
            runner = CatkinasRunner(
                [str(root / "missing-executable")],
                5,
                output,
                history,
            )

            result = runner.run(input_path)

            self.assertEqual(result.status, "EXECUTABLE_NOT_FOUND")
            self.assertIsNone(result.return_code)
            self.assertTrue((output / "stderr.log").read_text(encoding="utf-8"))

    def test_input_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output, history = _runner_paths(root, "zacros_run")
            runner = ZacrosRunner(
                [sys.executable, "-c", "print('must not run')"],
                5,
                output,
                history,
            )

            result = runner.run(root / "missing-input")

            self.assertEqual(result.status, "INPUT_NOT_FOUND")
            self.assertIsNone(result.return_code)
            self.assertEqual((output / "stdout.log").read_text(), "")

    def test_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input"
            input_path.mkdir()
            output, history = _runner_paths(root, "zacros_run")
            runner = ZacrosRunner(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                0.05,
                output,
                history,
            )

            result = runner.run(input_path)

            self.assertEqual(result.status, "TIMEOUT")
            self.assertIsNone(result.return_code)
            self.assertGreaterEqual(result.runtime, 0.04)

    def test_nonzero_return_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input"
            input_path.mkdir()
            output, history = _runner_paths(root, "zacros_run")
            runner = ZacrosRunner(
                [sys.executable, "-c", "import sys; sys.exit(7)"],
                5,
                output,
                history,
            )

            result = runner.run(input_path)

            self.assertEqual(result.status, "FAILED")
            self.assertEqual(result.return_code, 7)


class RunnerCommandLineTests(unittest.TestCase):
    """Verify CLI dispatch, configured command use, and runner logging."""

    def test_run_catkinas_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            input_path = root / "catkinas_project"
            config_path = project / "config" / "config.yaml"
            input_path.mkdir()
            config_path.parent.mkdir(parents=True)
            command = json.dumps(
                [sys.executable, "-c", "print('CLI_RUN')"],
            )
            config_path.write_text(
                f"""
project:
  name: VASP2Kinetics
  version: 0.1.0
paths:
  data_path: data
  output_path: output
  raw_vasp_cases: data/raw/vasp_cases
  processed_data: data/processed
logging:
  level: INFO
  console: true
  file: null
  phase_files: {{parser: logs/parser.log, simulation: logs/simulation.log, workflow: logs/workflow.log}}
validator:
  energy_tolerance: 0.05
  allowed_elements: [C, H, O, Fe]
catkinas:
  input_path: data/processed/kinetic_dataset.json
  output_path: output/catkinas_project
  allow_warning: true
zacros:
  surface_config: surface_config.yaml
  output_path: output/zacros_project
  allow_warning: true
simulation:
  catkinas_command: {command}
  zacros_command: path/to/zacros
  timeout: 5
analysis:
  result_path: output
  output_path: output/results
report:
  output_path: output/report
  template_path: src/analysis/templates/report.md
workflow: {{software: CATKINAS, output_root: output}}
""".lstrip(),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "main.py"),
                    "--config",
                    str(config_path),
                    "--run-catkinas",
                    "--input",
                    str(input_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output = project / "output" / "catkinas_run"
            status = json.loads(
                (output / "run_status.json").read_text(encoding="utf-8")
            )
            runner_log = (project / "logs" / "simulation.log").read_text(
                encoding="utf-8"
            )
            stdout_log = (output / "stdout.log").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(status["status"], "SUCCESS")
        self.assertEqual(stdout_log, "CLI_RUN\n")
        self.assertIn("Simulation started", runner_log)
        self.assertIn("Simulation ended", runner_log)


if __name__ == "__main__":
    unittest.main()
