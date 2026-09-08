"""Execute existing VASP2Kinetics modules for one workflow case."""

from __future__ import annotations

import logging
from pathlib import Path

from ..analysis.analyzer import analyze_simulation_data, load_simulation_result
from ..analysis.catkinas_parser import parse_catkinas_result
from ..analysis.report import write_analysis_report
from ..analysis.result_writer import write_result_files
from ..analysis.zacros_parser import parse_zacros_result
from ..catkinas.generator import generate_catkinas_project
from ..config import AppConfig
from ..exceptions import WorkflowError
from ..kinetics.builder import (
    build_kinetic_record,
    load_reaction_definition,
    load_vasp_result,
)
from ..kinetics.registry import RegistryStatus, register
from ..kinetics.validator import validate_dataset, write_validation_report
from ..runner.catkinas_runner import CatkinasRunner
from ..runner.zacros_runner import ZacrosRunner
from ..vasp.parser import parse_vasp_case, write_vasp_result
from ..zacros.generator import generate_zacros_project

LOGGER = logging.getLogger("vasp2kinetics.workflow")


class WorkflowExecutor:
    """Dispatch each named step to its already implemented module."""

    def __init__(
        self,
        case_path: str | Path,
        output_path: str | Path,
        config: AppConfig,
    ) -> None:
        """Store resolved case/output paths and validated configuration."""

        self.case_path = Path(case_path).expanduser().resolve()
        self.output_path = Path(output_path).expanduser().resolve()
        self.config = config

    @property
    def project_path(self) -> Path:
        """Return the selected adapter project directory."""

        name = (
            "catkinas_project"
            if self.config.workflow.software == "CATKINAS"
            else "zacros_project"
        )
        return self.output_path / name

    @property
    def run_path(self) -> Path:
        """Return the selected simulator raw-output directory."""

        name = (
            "catkinas_run"
            if self.config.workflow.software == "CATKINAS"
            else "zacros_run"
        )
        return self.output_path / name

    def execute_step(self, name: str) -> None:
        """Execute exactly one known workflow step."""

        handlers = {
            "vasp_parser": self._parse_vasp,
            "kinetic_builder": self._build_kinetics,
            "validator": self._validate,
            "input_generator": self._generate_input,
            "simulation_runner": self._run_simulation,
            "result_parser": self._parse_result,
            "analysis_report": self._analyze,
        }
        handler = handlers.get(name)
        if handler is None:
            raise WorkflowError(f"UNKNOWN_WORKFLOW_STEP: {name}")
        handler()

    def _parse_vasp(self) -> None:
        """Execute the existing VASP parser and reject its explicit errors."""

        result = parse_vasp_case(self.case_path / "vasp")
        write_vasp_result(result, self.output_path / "vasp_result.json")
        error = result.get("error")
        if isinstance(error, str):
            raise WorkflowError(f"VASP_PARSER_FAILED: {error}")

    def _build_kinetics(self) -> None:
        """Build and register one existing Phase 3 kinetic record."""

        vasp_result = load_vasp_result(self.output_path / "vasp_result.json")
        reaction = load_reaction_definition(self.case_path / "reaction.yaml")
        record = build_kinetic_record(vasp_result, reaction)
        status = register(record, self.output_path / "kinetic_dataset.json")
        if status == RegistryStatus.DUPLICATE_ID:
            raise WorkflowError(f"KINETIC_BUILDER_FAILED: {status.value}")

    def _validate(self) -> None:
        """Run the existing validator and stop on failed reactions."""

        report = validate_dataset(
            self.output_path / "kinetic_dataset.json",
            self.config.validator.energy_tolerance,
            self.config.validator.allowed_elements,
        )
        write_validation_report(report, self.output_path / "validation_report.json")
        summary = report.get("summary")
        if not isinstance(summary, dict):
            raise WorkflowError("VALIDATION_FAILED: INVALID_SUMMARY")
        if summary.get("failed", 0):
            raise WorkflowError(f"VALIDATION_FAILED: {summary}")

    def _generate_input(self) -> None:
        """Generate input for the explicitly selected simulator."""

        dataset = self.output_path / "kinetic_dataset.json"
        validation = self.output_path / "validation_report.json"
        if self.config.workflow.software == "CATKINAS":
            report = generate_catkinas_project(
                dataset,
                validation,
                self.project_path,
                self.config.catkinas.allow_warning,
            )
        else:
            report = generate_zacros_project(
                dataset,
                validation,
                self.case_path / "surface.yaml",
                self.project_path,
                self.config.zacros.allow_warning,
            )
        failed = report.get("failed")
        generated = report.get("generated")
        if not isinstance(failed, int) or not isinstance(generated, int):
            raise WorkflowError("INPUT_GENERATION_FAILED: INVALID_REPORT")
        if failed or generated == 0:
            raise WorkflowError(f"INPUT_GENERATION_FAILED: {report}")

    def _run_simulation(self) -> None:
        """Run the selected external simulator exactly once."""

        runner_class = (
            CatkinasRunner
            if self.config.workflow.software == "CATKINAS"
            else ZacrosRunner
        )
        command = (
            self.config.simulation.catkinas_command
            if self.config.workflow.software == "CATKINAS"
            else self.config.simulation.zacros_command
        )
        runner = runner_class(
            command,
            self.config.simulation.timeout,
            self.run_path,
            self.output_path / "execution_history.json",
        )
        result = runner.run(self.project_path)
        if result.status != "SUCCESS":
            raise WorkflowError(f"SIMULATION_FAILED: {result.status}")

    def _parse_result(self) -> None:
        """Parse selected simulator output and require a complete result."""

        parser = (
            parse_catkinas_result
            if self.config.workflow.software == "CATKINAS"
            else parse_zacros_result
        )
        result, parser_log = parser(self.run_path)
        write_result_files(result, parser_log, self.output_path)
        if result.status != "SUCCESS":
            raise WorkflowError(f"RESULT_PARSER_FAILED: {result.status}")

    def _analyze(self) -> None:
        """Generate the existing Phase 9 analysis and Markdown report."""

        source = self.output_path / "simulation_result.json"
        raw = load_simulation_result(source)
        result = analyze_simulation_data(raw)
        write_analysis_report(
            result,
            raw,
            source,
            self.output_path,
            self.config.report.template_path,
        )
