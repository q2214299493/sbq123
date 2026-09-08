"""Tests for the Phase 1 VASP2Kinetics foundation."""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.config import LoggingSettings, PhaseLogSettings, load_config
from src.exceptions import ConfigurationError
from src.logging_config import LOGGER_NAME, configure_logging

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    """Verify strict configuration loading."""

    def test_default_config_loads_and_resolves_paths(self) -> None:
        config = load_config(PROJECT_ROOT / "config" / "config.yaml")

        self.assertEqual(config.project.name, "VASP2Kinetics")
        self.assertEqual(config.project.version, "0.1.0")
        self.assertEqual(
            config.paths.data_path,
            (PROJECT_ROOT / "data").resolve(),
        )
        self.assertEqual(
            config.paths.output_path,
            (PROJECT_ROOT / "output").resolve(),
        )
        self.assertEqual(
            config.paths.raw_vasp_cases,
            (PROJECT_ROOT / "data" / "raw" / "vasp_cases").resolve(),
        )
        self.assertEqual(
            config.paths.processed_data,
            (PROJECT_ROOT / "data" / "processed").resolve(),
        )
        self.assertEqual(config.validator.energy_tolerance, 0.05)
        self.assertEqual(config.validator.allowed_elements, ("C", "H", "O", "Fe"))
        self.assertEqual(
            config.catkinas.input_path,
            (PROJECT_ROOT / "data" / "processed" / "kinetic_dataset.json").resolve(),
        )
        self.assertEqual(
            config.catkinas.output_path,
            (PROJECT_ROOT / "output" / "catkinas_project").resolve(),
        )
        self.assertTrue(config.catkinas.allow_warning)
        self.assertEqual(
            config.zacros.surface_config,
            (PROJECT_ROOT / "surface_config.yaml").resolve(),
        )
        self.assertEqual(
            config.zacros.output_path,
            (PROJECT_ROOT / "output" / "zacros_project").resolve(),
        )
        self.assertTrue(config.zacros.allow_warning)
        self.assertEqual(config.simulation.catkinas_command, ("path/to/catkinas",))
        self.assertEqual(config.simulation.zacros_command, ("path/to/zacros",))
        self.assertEqual(config.simulation.timeout, 3600.0)
        self.assertEqual(
            config.analysis.result_path,
            (PROJECT_ROOT / "output").resolve(),
        )
        self.assertEqual(
            config.analysis.output_path,
            (PROJECT_ROOT / "output" / "results").resolve(),
        )
        self.assertEqual(
            config.report.output_path,
            (PROJECT_ROOT / "output" / "report").resolve(),
        )
        self.assertEqual(
            config.report.template_path,
            (PROJECT_ROOT / "src" / "analysis" / "templates" / "report.md").resolve(),
        )
        self.assertEqual(config.workflow.software, "CATKINAS")
        self.assertEqual(
            config.workflow.output_root,
            (PROJECT_ROOT / "output").resolve(),
        )
        self.assertEqual(
            config.logging.phase_files.parser,
            (PROJECT_ROOT / "logs" / "parser.log").resolve(),
        )
        self.assertEqual(
            config.logging.phase_files.simulation,
            (PROJECT_ROOT / "logs" / "simulation.log").resolve(),
        )
        self.assertEqual(
            config.logging.phase_files.workflow,
            (PROJECT_ROOT / "logs" / "workflow.log").resolve(),
        )

    def test_missing_config_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_config(PROJECT_ROOT / "config" / "missing.yaml")

    def test_missing_required_value_is_not_defaulted(self) -> None:
        content = """
project:
  name: VASP2Kinetics
paths:
  raw_vasp_cases: data/raw/vasp_cases
  processed_data: data/processed
logging:
  level: INFO
  console: true
  file: null
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_config(path)


class LoggingTests(unittest.TestCase):
    """Verify deterministic logger configuration."""

    def tearDown(self) -> None:
        logger = logging.getLogger(LOGGER_NAME)
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()

    def test_reconfiguration_does_not_duplicate_handlers(self) -> None:
        settings = LoggingSettings(
            level="INFO",
            console=True,
            file=None,
            phase_files=PhaseLogSettings(
                parser=PROJECT_ROOT / "logs" / "parser.log",
                simulation=PROJECT_ROOT / "logs" / "simulation.log",
                workflow=PROJECT_ROOT / "logs" / "workflow.log",
            ),
        )

        configure_logging(settings)
        logger = configure_logging(settings)

        self.assertEqual(len(logger.handlers), 1)
        self.assertFalse(logger.propagate)


class CommandLineTests(unittest.TestCase):
    """Verify the Phase 1 command entry point."""

    def test_main_initializes_foundation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "main.py"),
                "--config",
                str(PROJECT_ROOT / "config" / "config.yaml"),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("VASP2Kinetics 0.1.0 application initialized", completed.stderr)


if __name__ == "__main__":
    unittest.main()
