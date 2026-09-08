"""Tests for Phase 3 kinetic record construction and registration."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.exceptions import ReactionDefinitionError
from src.kinetics.builder import (
    ReactionDefinition,
    build_kinetic_record,
    load_reaction_definition,
)
from src.kinetics.registry import RegistryStatus, load, register
from src.kinetics.schema import ReactionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _reaction() -> ReactionDefinition:
    return ReactionDefinition(
        reaction_id="CO_dissociation_001",
        reactant=["CO*"],
        product=["C*", "O*"],
        material="Fe",
        surface="Fe110",
        facet="110",
        functional="PBE",
    )


def _vasp_result() -> dict[str, object]:
    return {
        "energy": {"final": -100.25},
        "convergence": {"status": "converged"},
        "neb": {"highest_energy": -99.10},
        "source": {"path": "C:/calculations/co_dissociation"},
    }


class BuilderTests(unittest.TestCase):
    """Verify strict one-way field mappings."""

    def test_normal_vasp_result_builds_record(self) -> None:
        record = build_kinetic_record(_vasp_result(), _reaction())

        self.assertEqual(record.reaction_id, "CO_dissociation_001")
        self.assertEqual(record.energetics.E_final, -100.25)
        self.assertEqual(record.energetics.candidate_TS_energy, -99.10)
        self.assertIsNone(record.energetics.E_initial)
        self.assertIsNone(record.energetics.E_reaction)
        self.assertIsNone(record.energetics.Ea_forward)
        self.assertIsNone(record.energetics.Ea_reverse)
        self.assertTrue(record.quality.vasp_converged)
        self.assertFalse(record.quality.ts_verified)
        self.assertEqual(record.status, ReactionStatus.UNVERIFIED)

    def test_missing_energy_remains_none(self) -> None:
        vasp_result = _vasp_result()
        vasp_result["energy"] = {"final": None}

        record = build_kinetic_record(vasp_result, _reaction())

        self.assertIsNone(record.energetics.E_final)

    def test_missing_neb_remains_none(self) -> None:
        vasp_result = _vasp_result()
        vasp_result["neb"] = None

        record = build_kinetic_record(vasp_result, _reaction())

        self.assertIsNone(record.energetics.candidate_TS_energy)


class RegistryTests(unittest.TestCase):
    """Verify append, load, and duplicate protection."""

    def test_duplicate_reaction_id_is_not_overwritten(self) -> None:
        record = build_kinetic_record(_vasp_result(), _reaction())
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_path = Path(temp_dir) / "kinetic_dataset.json"

            first_status = register(record, dataset_path)
            original_text = dataset_path.read_text(encoding="utf-8")
            second_status = register(record, dataset_path)
            loaded = load(dataset_path)

            self.assertEqual(first_status, RegistryStatus.REGISTERED)
            self.assertEqual(second_status, RegistryStatus.DUPLICATE_ID)
            self.assertEqual(dataset_path.read_text(encoding="utf-8"), original_text)
            self.assertEqual(len(loaded.records), 1)


class ReactionYamlTests(unittest.TestCase):
    """Reject invalid or unsupported reaction YAML."""

    def test_yaml_input_error(self) -> None:
        content = """
reaction_id: CO_dissociation_001
reactant: CO*
product:
  - C*
  - O*
automatic_mechanism: true
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            reaction_path = Path(temp_dir) / "reaction.yaml"
            reaction_path.write_text(content, encoding="utf-8")

            with self.assertRaises(ReactionDefinitionError):
                load_reaction_definition(reaction_path)


class KineticCommandLineTests(unittest.TestCase):
    """Verify the required Phase 3 command and output file."""

    def test_cli_builds_kinetic_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            project_path = temp_path / "configured_project"
            config_path = project_path / "config" / "config.yaml"
            input_path = temp_path / "vasp_result.json"
            reaction_path = temp_path / "reaction.yaml"
            config_path.parent.mkdir(parents=True)
            input_path.write_text(json.dumps(_vasp_result()), encoding="utf-8")
            reaction_path.write_text(
                """
reaction_id: CO_dissociation_001
reactant:
  - CO*
product:
  - C*
  - O*
surface: Fe110
""".lstrip(),
                encoding="utf-8",
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
  file: logs/kinetic_builder.log
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
                    "--build-kinetics",
                    "--input",
                    str(input_path),
                    "--reaction",
                    str(reaction_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output_path = project_path / "data" / "processed" / "kinetic_dataset.json"
            log_path = project_path / "logs" / "kinetic_builder.log"
            dataset = json.loads(output_path.read_text(encoding="utf-8"))
            log_text = log_path.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(dataset["records"]), 1)
        record = dataset["records"][0]
        self.assertEqual(record["status"], "UNVERIFIED")
        self.assertEqual(record["energetics"]["E_final"], -100.25)
        self.assertEqual(record["energetics"]["candidate_TS_energy"], -99.10)
        self.assertIsNone(record["energetics"]["Ea_forward"])
        self.assertIn(str(input_path), log_text)
        self.assertIn(str(reaction_path), log_text)
        self.assertIn("reaction_id=CO_dissociation_001", log_text)
        self.assertIn(str(output_path), log_text)


if __name__ == "__main__":
    unittest.main()
