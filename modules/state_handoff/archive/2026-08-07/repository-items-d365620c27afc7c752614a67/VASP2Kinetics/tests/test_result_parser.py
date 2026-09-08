"""Tests for Phase 8 simulation-result parsing."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.analysis.catkinas_parser import parse_catkinas_result
from src.analysis.zacros_parser import parse_zacros_result

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _mapping(path: Path, software_id: str) -> None:
    path.write_text(
        json.dumps({"r1": {software_id: 1}}, indent=2) + "\n",
        encoding="utf-8",
    )


def _catkinas_files(path: Path, include_tof: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "coverage.dat").write_text("CO* 0.25\nO* 0.5\n", encoding="utf-8")
    (path / "reaction_rates.dat").write_text("1 2.5e-3\n", encoding="utf-8")
    if include_tof:
        (path / "tof.dat").write_text("1.2e-3\n", encoding="utf-8")
    (path / "conditions.dat").write_text(
        "temperature 500\npressure 1.0\n",
        encoding="utf-8",
    )
    (path / "selectivity.dat").write_text("CO2 0.8\n", encoding="utf-8")
    _mapping(path / "mapping.json", "catkinas_id")


def _zacros_files(path: Path, include_coverage: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if include_coverage:
        (path / "coverage.dat").write_text("CO* 0.20\nO* 0.34\n", encoding="utf-8")
    (path / "procstat_output.txt").write_text(
        """Overall r1
configuration 1 0 0.00
0.000 0.000
0 0
configuration 2 24 0.01
0.040 0.041
24 24
""",
        encoding="utf-8",
    )
    (path / "specnum_output.txt").write_text(
        """Entry Nevents Time Temperature Energy CO* CO2
1 0 0.0 500.0 -1.0 2 0
2 24 0.01 500.0 -2.0 4 3
""",
        encoding="utf-8",
    )
    (path / "tof.dat").write_text("3.0\n", encoding="utf-8")
    _mapping(path / "mapping.json", "zacros_id")


class SimulationResultParserTests(unittest.TestCase):
    """Cover normal, incomplete, and malformed simulation output."""

    def test_normal_catkinas_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "catkinas_project"
            run_output = root / "catkinas_run"
            _catkinas_files(source)
            run_output.mkdir()
            (run_output / "run_status.json").write_text(
                json.dumps(
                    {
                        "simulation_id": "catkinas-test-1",
                        "status": "SUCCESS",
                        "input_path": str(source),
                    }
                ),
                encoding="utf-8",
            )
            before = {item.name: item.read_bytes() for item in source.iterdir()}

            result, parser_log = parse_catkinas_result(run_output)
            after = {item.name: item.read_bytes() for item in source.iterdir()}

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.simulation_id, "catkinas-test-1")
        self.assertEqual(result.coverage, {"CO*": 0.25, "O*": 0.5})
        self.assertEqual(result.reaction_rates, {"r1": 2.5e-3})
        self.assertEqual(result.tof, 1.2e-3)
        self.assertEqual(result.selectivity, {"CO2": 0.8})
        self.assertEqual(result.conditions.temperature, 500.0)
        self.assertEqual(parser_log["errors"], [])
        self.assertEqual(before, after)

    def test_normal_zacros_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir)
            _zacros_files(source)

            result, parser_log = parse_zacros_result(source)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.coverage, {"CO*": 0.2, "O*": 0.34})
        self.assertEqual(result.reaction_rates, {"r1": 2400.0})
        self.assertEqual(result.tof, 3.0)
        self.assertEqual(result.conditions.temperature, 500.0)
        self.assertEqual(parser_log["errors"], [])

    def test_missing_tof_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir)
            _catkinas_files(source, include_tof=False)

            result, parser_log = parse_catkinas_result(source)

        self.assertEqual(result.status, "PARTIAL")
        self.assertIsNone(result.tof)
        self.assertIn("TOF_FILE_NOT_FOUND", parser_log["errors"])

    def test_missing_coverage_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir)
            _zacros_files(source, include_coverage=False)
            (source / "specnum_output.txt").unlink()

            result, parser_log = parse_zacros_result(source)

        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(result.coverage, {})
        self.assertIn("COVERAGE_FILE_NOT_FOUND", parser_log["errors"])

    def test_invalid_number_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir)
            _catkinas_files(source)
            (source / "coverage.dat").write_text("CO* invalid\n", encoding="utf-8")

            result, parser_log = parse_catkinas_result(source)

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.coverage, {})
        self.assertIn("COVERAGE_INVALID_NUMBER:1", parser_log["errors"])


class ResultParserCommandLineTests(unittest.TestCase):
    """Verify Phase 8 CLI output files."""

    def test_catkinas_cli_writes_result_and_parser_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            source = root / "catkinas_output"
            config_path = project / "config" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            _catkinas_files(source)
            config_path.write_text(
                """
project: {name: VASP2Kinetics, version: 0.1.0}
paths: {data_path: data, output_path: output, raw_vasp_cases: data/raw/vasp_cases, processed_data: data/processed}
logging: {level: INFO, console: true, file: null, phase_files: {parser: logs/parser.log, simulation: logs/simulation.log, workflow: logs/workflow.log}}
validator: {energy_tolerance: 0.05, allowed_elements: [C, H, O, Fe]}
catkinas:
  {input_path: data/processed/kinetic_dataset.json, output_path: output/catkinas_project, allow_warning: true}
zacros:
  {surface_config: surface_config.yaml, output_path: output/zacros_project, allow_warning: true}
simulation:
  {catkinas_command: path/to/catkinas, zacros_command: path/to/zacros, timeout: 5}
analysis: {result_path: output, output_path: output/results}
report: {output_path: output/report, template_path: src/analysis/templates/report.md}
workflow: {software: CATKINAS, output_root: output}
""".lstrip(),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "main.py"),
                    "--config",
                    str(config_path),
                    "--parse-catkinas-result",
                    "--input",
                    str(source),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output = project / "output" / "results"
            result = json.loads(
                (output / "simulation_result.json").read_text(encoding="utf-8")
            )
            parser_log_exists = (output / "parser_log.json").is_file()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(parser_log_exists)


if __name__ == "__main__":
    unittest.main()
