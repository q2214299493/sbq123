"""Command-line test for Phase 6 static Zacros adapter generation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_zacros_generator import _record, _write_inputs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ZacrosCommandLineTests(unittest.TestCase):
    """Verify CLI use of dataset, validation, and surface inputs."""

    def test_cli_generates_static_zacros_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            configured_project = temp_path / "configured_project"
            config_path = configured_project / "config" / "config.yaml"
            input_directory = temp_path / "input"
            config_path.parent.mkdir(parents=True)
            input_directory.mkdir()
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, _, surface, _ = _write_inputs(
                input_directory,
                [record],
                {"r1": "PASS"},
                {"r1": "bridge"},
            )
            config_path.write_text(
                """
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
  phase_files: {parser: logs/parser.log, simulation: logs/simulation.log, workflow: logs/workflow.log}
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
  catkinas_command: path/to/catkinas
  zacros_command: path/to/zacros
  timeout: 3600
analysis:
  result_path: output
  output_path: output/results
report:
  output_path: output/report
  template_path: src/analysis/templates/report.md
workflow: {software: ZACROS, output_root: output}
""".lstrip(),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "main.py"),
                    "--config",
                    str(config_path),
                    "--generate-zacros",
                    "--input",
                    str(dataset),
                    "--surface",
                    str(surface),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output = configured_project / "output" / "zacros_project"
            generation_report = json.loads(
                (output / "generation_report.json").read_text(encoding="utf-8")
            )
            expected = {
                "lattice_input.dat",
                "mechanism_input.dat",
                "energetics_input.dat",
                "species_input.dat",
                "mapping.json",
            }
            generated_files_exist = all(
                (output / name).is_file() for name in expected
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(generation_report["generated"], 1)
        self.assertTrue(generated_files_exist)
