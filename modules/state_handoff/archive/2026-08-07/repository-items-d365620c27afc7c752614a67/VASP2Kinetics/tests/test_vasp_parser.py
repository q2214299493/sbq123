"""Tests for read-only VASP result parsing."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vasp.neb_parser import parse_neb
from src.vasp.oszicar_parser import parse_oszicar
from src.vasp.outcar_parser import parse_outcar
from src.vasp.parser import parse_vasp_case

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_complete_outcar(path: Path, energy: float) -> None:
    """Write a minimal format fixture containing real VASP output markers."""

    path.write_text(
        "\n".join(
            [
                "-------------------------------- Iteration    1(   1)  --------------------------------",
                "-------------------------------- Iteration    1(   2)  --------------------------------",
                f"  free  energy   TOTEN  =      {energy:.8f} eV",
                " reached required accuracy - stopping structural energy minimisation",
                " General timing and accounting informations for this job:",
                "",
            ]
        ),
        encoding="utf-8",
    )


class OutcarParserTests(unittest.TestCase):
    """Cover complete, missing, and empty OUTCAR inputs."""

    def test_normal_outcar_uses_last_toten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outcar = Path(temp_dir) / "OUTCAR"
            outcar.write_text(
                "\n".join(
                    [
                        " Iteration    1(   1)",
                        " free  energy   TOTEN  =      -123.00000000 eV",
                        " Iteration    1(   2)",
                        " free  energy   TOTEN  =      -123.45600000 eV",
                        " General timing and accounting informations for this job:",
                    ]
                ),
                encoding="utf-8",
            )

            result = parse_outcar(outcar)

        self.assertEqual(result["status"], "CONVERGED")
        self.assertEqual(result["energy_final"], -123.456)
        self.assertTrue(result["converged"])
        self.assertEqual(result["scf_steps"], 2)
        self.assertNotIn("error", result)

    def test_missing_outcar_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = parse_outcar(Path(temp_dir) / "OUTCAR")

        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertEqual(result["error"], "OUTCAR_NOT_FOUND")
        self.assertIsNone(result["energy_final"])

    def test_empty_outcar_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outcar = Path(temp_dir) / "OUTCAR"
            outcar.write_text("", encoding="utf-8")

            result = parse_outcar(outcar)

        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error"], "OUTCAR_EMPTY")


class OszicarParserTests(unittest.TestCase):
    """Cover explicit OSZICAR electronic and ionic records."""

    def test_normal_oszicar(self) -> None:
        content = """
 DAV:   1    -0.12300000E+03   -0.123E+03
 DAV:   2    -0.12340000E+03   -0.400E+00
   1 F= -.12340000E+03 E0= -.12339000E+03  d E =-.123400E+03
 RMM:   1    -0.12345000E+03   -0.500E-01
   2 F= -.12345000E+03 E0= -.12344000E+03  d E =-.500000E-01
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            oszicar = Path(temp_dir) / "OSZICAR"
            oszicar.write_text(content, encoding="utf-8")

            result = parse_oszicar(oszicar)

        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["electronic_steps"], 3)
        self.assertEqual(result["ionic_steps"], 2)
        self.assertEqual(result["final_energy"], -123.45)


class NebParserTests(unittest.TestCase):
    """Cover complete and incomplete numeric NEB image sets."""

    def test_normal_neb_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            neb_path = Path(temp_dir)
            for image_id, energy in ((0, -100.1), (1, -99.5), (2, -100.2)):
                image_path = neb_path / f"{image_id:02d}"
                image_path.mkdir()
                _write_complete_outcar(image_path / "OUTCAR", energy)

            result = parse_neb(neb_path)

        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(len(result["images"]), 3)
        self.assertEqual(result["highest_image"], 1)
        self.assertEqual(result["highest_energy"], -99.5)
        self.assertNotIn("error", result)

    def test_incomplete_neb_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            neb_path = Path(temp_dir)
            image_00 = neb_path / "00"
            image_01 = neb_path / "01"
            image_00.mkdir()
            image_01.mkdir()
            _write_complete_outcar(image_00 / "OUTCAR", -100.1)

            result = parse_neb(neb_path)

        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["error"], "NEB_IMAGE_DATA_INCOMPLETE")
        self.assertEqual(result["highest_image"], 0)
        self.assertEqual(result["images"][1]["error"], "OUTCAR_NOT_FOUND")
        self.assertIsNone(result["images"][1]["energy"])


class UnifiedParserTests(unittest.TestCase):
    """Verify unified output and the public command-line entry point."""

    def test_unified_result_contains_source_and_raw_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)
            _write_complete_outcar(case_path / "OUTCAR", -123.456)

            result = parse_vasp_case(case_path)

        self.assertEqual(result["calculation_id"], "unknown")
        self.assertEqual(result["type"], "vasp")
        self.assertEqual(result["energy"]["final"], -123.456)
        self.assertEqual(result["convergence"]["status"], "converged")
        self.assertEqual(result["oszicar"]["status"], "NOT_AVAILABLE")
        self.assertIsNone(result["neb"])
        self.assertEqual(result["source"]["path"], str(case_path.resolve()))

    def test_cli_writes_standard_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            case_path = temp_path / "case"
            project_path = temp_path / "configured_project"
            config_path = project_path / "config" / "config.yaml"
            case_path.mkdir()
            config_path.parent.mkdir(parents=True)
            _write_complete_outcar(case_path / "OUTCAR", -123.456)
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
                    "--parse-vasp",
                    str(case_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output_path = project_path / "data" / "processed" / "vasp_result.json"
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["energy"]["final"], -123.456)
        self.assertEqual(result["source"]["path"], str(case_path.resolve()))


if __name__ == "__main__":
    unittest.main()
