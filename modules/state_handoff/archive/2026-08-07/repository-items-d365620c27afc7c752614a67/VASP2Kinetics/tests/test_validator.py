"""Tests for the non-mutating Phase 4 scientific validator."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.kinetics.validator import validate_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ELEMENTS = ("C", "H", "O", "Fe")
TOLERANCE = 0.05


def _record(source_path: Path) -> dict[str, object]:
    return {
        "reaction_id": "CO_dissociation_001",
        "system": {
            "material": "Fe",
            "surface": "Fe110",
            "facet": "110",
        },
        "species": {
            "reactant": ["CO*"],
            "product": ["C*", "O*"],
        },
        "energetics": {
            "E_initial": -100.0,
            "E_final": -99.8,
            "E_reaction": 0.2,
            "Ea_forward": 1.0,
            "Ea_reverse": 0.8,
            "candidate_TS_energy": -99.0,
        },
        "calculation": {
            "method": "VASP",
            "functional": "PBE",
            "source_path": str(source_path),
        },
        "quality": {
            "vasp_converged": True,
            "ts_verified": False,
            "scientific_review": False,
        },
        "status": "UNVERIFIED",
    }


def _write_dataset(path: Path, record: dict[str, object]) -> bytes:
    content = (
        json.dumps(
            {"schema_version": "1.0", "records": [record]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(content)
    return content


class ValidatorTests(unittest.TestCase):
    """Cover required Phase 4 scientific checks."""

    def test_normal_reaction_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            _write_dataset(dataset_path, _record(temp_path))

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        self.assertEqual(report["summary"]["passed"], 1)
        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["overall_status"], "PASS")
        self.assertEqual(reaction_report["checks"]["element_balance"], "PASS")
        self.assertEqual(reaction_report["checks"]["energy_balance"], "PASS")

    def test_unbalanced_reaction_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path)
            record["species"]["product"] = ["C*"]
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["checks"]["element_balance"], "FAILED")
        self.assertEqual(reaction_report["overall_status"], "FAILED")

    def test_missing_energy_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path)
            record["energetics"]["E_reaction"] = None
            record["energetics"]["Ea_forward"] = None
            record["energetics"]["Ea_reverse"] = None
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(
            reaction_report["checks"]["energy_balance"],
            "NOT_AVAILABLE",
        )
        self.assertEqual(reaction_report["checks"]["barrier"], "NOT_AVAILABLE")
        self.assertEqual(reaction_report["overall_status"], "WARNING")

    def test_inconsistent_reverse_barrier_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path)
            record["energetics"]["Ea_reverse"] = 0.9
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["checks"]["energy_balance"], "FAILED")
        difference = reaction_report["details"]["energy_balance"]["difference"]
        self.assertAlmostEqual(difference, 0.1)

    def test_missing_source_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path / "does_not_exist")
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["checks"]["source"], "SOURCE_NOT_FOUND")
        self.assertEqual(reaction_report["overall_status"], "FAILED")

    def test_negative_forward_barrier_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path)
            record["energetics"]["Ea_forward"] = -0.1
            record["energetics"]["Ea_reverse"] = -0.3
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["checks"]["barrier"], "FAILED")
        self.assertEqual(reaction_report["overall_status"], "FAILED")

    def test_unconverged_vasp_flag_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path)
            record["quality"]["vasp_converged"] = False
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["checks"]["vasp_convergence"], "FAILED")
        self.assertEqual(reaction_report["overall_status"], "FAILED")

    def test_unsupported_formula_is_not_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "kinetic_dataset.json"
            record = _record(temp_path)
            record["species"]["reactant"] = ["N2*"]
            record["species"]["product"] = ["N*", "N*"]
            _write_dataset(dataset_path, record)

            report = validate_dataset(dataset_path, TOLERANCE, ALLOWED_ELEMENTS)

        reaction_report = report["checks"][0]
        self.assertEqual(reaction_report["checks"]["element_balance"], "NOT_CHECKED")
        self.assertEqual(reaction_report["overall_status"], "WARNING")


class ValidatorCommandLineTests(unittest.TestCase):
    """Verify CLI output and byte preservation of the input dataset."""

    def test_cli_writes_report_without_modifying_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            configured_project = temp_path / "configured_project"
            config_path = configured_project / "config" / "config.yaml"
            dataset_path = temp_path / "kinetic_dataset.json"
            config_path.parent.mkdir(parents=True)
            original = _write_dataset(dataset_path, _record(temp_path))
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
  allowed_elements:
    - C
    - H
    - O
    - Fe
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
                    "--validate",
                    "--input",
                    str(dataset_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output_path = (
                configured_project
                / "data"
                / "processed"
                / "validation_report.json"
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            unchanged = dataset_path.read_bytes()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(report["summary"]["passed"], 1)
        self.assertEqual(unchanged, original)


if __name__ == "__main__":
    unittest.main()
