"""Tests for Phase 9 numeric organization and Markdown reporting."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyzer import NOT_AVAILABLE, analyze_simulation_data
from src.analysis.report import write_analysis_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "src" / "analysis" / "templates" / "report.md"


def _simulation_result() -> dict[str, object]:
    return {
        "simulation_id": "sim-9-001",
        "software": "Zacros",
        "status": "SUCCESS",
        "conditions": {"temperature": 500.0, "pressure": 1.0},
        "coverage": {"CO*": 0.2, "O*": 0.5},
        "reaction_rates": {"r_low": 0.1, "r_high": 0.5},
        "tof": 0.02,
        "selectivity": {"CO2": 0.8},
        "source": {"path": "C:/simulation/zacros_run"},
    }


class AnalyzerTests(unittest.TestCase):
    """Cover present, missing, sorted, and empty simulation values."""

    def test_normal_tof_analysis(self) -> None:
        result = analyze_simulation_data(_simulation_result())

        self.assertEqual(result.simulation_id, "sim-9-001")
        self.assertEqual(result.software, "Zacros")
        self.assertEqual(result.summary.tof, 0.02)
        self.assertEqual(
            [item.species for item in result.summary.main_species],
            ["O*", "CO*"],
        )

    def test_reaction_rate_ranking_and_share(self) -> None:
        raw = _simulation_result()
        raw["reaction_rates"] = {
            "r_reverse": -0.4,
            "r_high": 0.5,
            "r_low": 0.1,
        }

        result = analyze_simulation_data(raw)

        self.assertEqual(
            [item.reaction_id for item in result.reaction_analysis],
            ["r_high", "r_low", "r_reverse"],
        )
        self.assertAlmostEqual(
            result.reaction_analysis[0].relative_contribution or 0.0,
            0.5,
        )

    def test_missing_selectivity_is_not_available(self) -> None:
        raw = _simulation_result()
        raw.pop("selectivity")

        result = analyze_simulation_data(raw)

        self.assertEqual(result.summary.selectivity, NOT_AVAILABLE)

    def test_empty_simulation_result_preserves_missing_values(self) -> None:
        result = analyze_simulation_data({})
        data = result.to_dict()

        self.assertEqual(data["simulation_id"], "")
        self.assertEqual(data["software"], "")
        self.assertIsNone(data["summary"]["TOF"])
        self.assertEqual(data["summary"]["main_species"], [])
        self.assertEqual(data["summary"]["selectivity"], NOT_AVAILABLE)
        self.assertEqual(data["reaction_analysis"], [])


class ReportTests(unittest.TestCase):
    """Verify required files, sections, neutral wording, and the CLI."""

    def test_report_generation(self) -> None:
        raw = _simulation_result()
        result = analyze_simulation_data(raw)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "simulation_result.json"
            original = json.dumps(raw, indent=2) + "\n"
            input_path.write_text(original, encoding="utf-8")

            analysis_path, report_path = write_analysis_report(
                result,
                raw,
                input_path,
                root / "output",
                TEMPLATE,
            )
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            report = report_path.read_text(encoding="utf-8")
            unchanged = input_path.read_text(encoding="utf-8")

        self.assertEqual(analysis["summary"]["TOF"], 0.02)
        self.assertIn("## 4. Reaction Rate Ranking", report)
        self.assertIn("highest calculated rate", report)
        self.assertIn("Validation summary is NOT_AVAILABLE", report)
        self.assertNotIn("rate determining step", report.lower())
        self.assertNotIn("rate-determining step", report.lower())
        for forbidden in ("发现", "证明", "确定"):
            self.assertNotIn(forbidden, report)
        self.assertEqual(unchanged, original)

    def test_analyze_cli_writes_both_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            config_path = project / "config" / "config.yaml"
            template_path = project / "report_template.md"
            input_path = root / "simulation_result.json"
            config_path.parent.mkdir(parents=True)
            template_path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
            input_path.write_text(
                json.dumps(_simulation_result()),
                encoding="utf-8",
            )
            config_path.write_text(
                """
project: {name: VASP2Kinetics, version: 0.1.0}
paths: {data_path: data, output_path: output, raw_vasp_cases: data/raw/vasp_cases, processed_data: data/processed}
logging: {level: INFO, console: true, file: null, phase_files: {parser: logs/parser.log, simulation: logs/simulation.log, workflow: logs/workflow.log}}
validator: {energy_tolerance: 0.05, allowed_elements: [C, H, O, Fe]}
catkinas: {input_path: data/processed/kinetic_dataset.json, output_path: output/catkinas_project, allow_warning: true}
zacros: {surface_config: surface_config.yaml, output_path: output/zacros_project, allow_warning: true}
simulation: {catkinas_command: catkinas, zacros_command: zacros, timeout: 5}
analysis: {result_path: output, output_path: output/results}
report: {output_path: output/report, template_path: report_template.md}
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
                    "--analyze",
                    "--input",
                    str(input_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            output = project / "output" / "report"

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "analysis_result.json").is_file())
            self.assertTrue((output / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
