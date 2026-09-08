"""Tests for Phase 5 static CATKINAS adapter generation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.catkinas.generator import generate_catkinas_project
from src.kinetics.schema import (
    CalculationInfo,
    Energetics,
    KineticDataset,
    QualityInfo,
    ReactionRecord,
    ReactionStatus,
    SpeciesInfo,
    SystemInfo,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record(
    reaction_id: str,
    reactant: list[str],
    product: list[str],
    source_path: Path,
    activation_energy: float | None = 0.98,
    reaction_energy: float | None = 0.2,
) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        system=SystemInfo(material="Fe", surface="Fe110", facet="110"),
        species=SpeciesInfo(reactant=reactant, product=product),
        energetics=Energetics(
            E_initial=None,
            E_final=None,
            E_reaction=reaction_energy,
            Ea_forward=activation_energy,
            Ea_reverse=None,
            candidate_TS_energy=None,
        ),
        calculation=CalculationInfo(
            method="VASP",
            functional="PBE",
            source_path=str(source_path),
        ),
        quality=QualityInfo(
            vasp_converged=True,
            ts_verified=False,
            scientific_review=False,
        ),
        status=ReactionStatus.UNVERIFIED,
    )


def _write_inputs(
    directory: Path,
    records: list[ReactionRecord],
    statuses: dict[str, str],
) -> tuple[Path, Path, Path]:
    dataset_path = directory / "kinetic_dataset.json"
    validation_path = directory / "validation_report.json"
    output_path = directory / "catkinas_project"
    dataset_path.write_text(
        json.dumps(KineticDataset(records=records).to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        json.dumps(
            {
                "dataset": str(dataset_path),
                "summary": {},
                "checks": [
                    {
                        "reaction_id": reaction_id,
                        "overall_status": status,
                    }
                    for reaction_id, status in statuses.items()
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return dataset_path, validation_path, output_path


class CatkinasGeneratorTests(unittest.TestCase):
    """Cover selection, file content, mapping, and failure reporting."""

    def test_normal_reaction_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record(
                "CO_dissociation_001",
                ["CO*"],
                ["C*", "O*"],
                temp_path,
            )
            dataset, validation, output = _write_inputs(
                temp_path,
                [record],
                {record.reaction_id: "PASS"},
            )
            dataset_before = dataset.read_bytes()
            validation_before = validation.read_bytes()

            report = generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=True,
            )
            species = (output / "species.dat").read_text(encoding="utf-8")
            reactions = (output / "reactions.dat").read_text(encoding="utf-8")
            parameters = (output / "parameters.dat").read_text(encoding="utf-8")
            mapping = json.loads((output / "mapping.json").read_text(encoding="utf-8"))
            dataset_after = dataset.read_bytes()
            validation_after = validation.read_bytes()

        self.assertEqual(report["generated"], 1)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(species.splitlines(), ["CO*", "C*", "O*"])
        self.assertIn("reaction: CO* = C* + O*", reactions)
        self.assertIn("barrier: 0.98", reactions)
        self.assertIn("activation_energy: 0.98", parameters)
        self.assertIn("reaction_energy: 0.2", parameters)
        self.assertEqual(mapping["CO_dissociation_001"]["catkinas_id"], 1)
        self.assertEqual(
            mapping["CO_dissociation_001"]["source_path"],
            str(temp_path),
        )
        self.assertEqual(dataset_after, dataset_before)
        self.assertEqual(validation_after, validation_before)

    def test_multiple_reactions_keep_sequential_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            second = _record("r2", ["C*", "H*"], ["CH*"], temp_path, 0.5, -0.1)
            dataset, validation, output = _write_inputs(
                temp_path,
                [first, second],
                {"r1": "PASS", "r2": "PASS"},
            )

            report = generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=True,
            )
            mapping = json.loads((output / "mapping.json").read_text(encoding="utf-8"))

        self.assertEqual(report["generated"], 2)
        self.assertEqual(mapping["r1"]["catkinas_id"], 1)
        self.assertEqual(mapping["r2"]["catkinas_id"], 2)

    def test_duplicate_species_are_removed_without_renaming(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            second = _record("r2", ["C*", "O*"], ["CO*"], temp_path)
            dataset, validation, output = _write_inputs(
                temp_path,
                [first, second],
                {"r1": "PASS", "r2": "PASS"},
            )

            generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=True,
            )
            species = (output / "species.dat").read_text(encoding="utf-8").splitlines()

        self.assertEqual(species, ["CO*", "C*", "O*"])

    def test_missing_activation_energy_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path, None)
            dataset, validation, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "WARNING"},
            )

            report = generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=True,
            )
            mapping = json.loads((output / "mapping.json").read_text(encoding="utf-8"))

        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["failed_reason"][0]["status"], "NOT_READY")
        self.assertEqual(
            report["failed_reason"][0]["reason"],
            "missing activation energy",
        )
        self.assertEqual(mapping, {})

    def test_failed_validation_reaction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, validation, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "FAILED"},
            )

            report = generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=True,
            )

        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["failed_reason"][0]["status"], "FAILED")
        self.assertEqual(
            report["failed_reason"][0]["reason"],
            "validation status FAILED",
        )

    def test_warning_reaction_is_generated_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, validation, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "WARNING"},
            )

            report = generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=True,
            )

        self.assertEqual(report["generated"], 1)
        self.assertEqual(report["warnings"], 1)
        self.assertEqual(report["warning_reactions"][0]["reaction_id"], "r1")

    def test_warning_reaction_is_rejected_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, validation, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "WARNING"},
            )

            report = generate_catkinas_project(
                dataset,
                validation,
                output,
                allow_warning=False,
            )

        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["failed_reason"][0]["reason"], "WARNING is not allowed")


class CatkinasCommandLineTests(unittest.TestCase):
    """Verify the required CLI and configured output path."""

    def test_cli_generates_static_adapter_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            configured_project = temp_path / "configured_project"
            config_path = configured_project / "config" / "config.yaml"
            input_directory = temp_path / "input"
            config_path.parent.mkdir(parents=True)
            input_directory.mkdir()
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, _, _ = _write_inputs(
                input_directory,
                [record],
                {"r1": "PASS"},
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
                    "--generate-catkinas",
                    "--input",
                    str(dataset),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output = configured_project / "output" / "catkinas_project"
            generation_report = json.loads(
                (output / "generation_report.json").read_text(encoding="utf-8")
            )
            generated_files = {
                name: (output / name).is_file()
                for name in (
                    "species.dat",
                    "reactions.dat",
                    "parameters.dat",
                    "mapping.json",
                )
            }

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(generation_report["generated"], 1)
        self.assertTrue(all(generated_files.values()))


if __name__ == "__main__":
    unittest.main()
