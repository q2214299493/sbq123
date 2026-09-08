"""Typed application configuration records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectSettings:
    """Project identity fields."""

    name: str
    version: str


@dataclass(frozen=True)
class PathSettings:
    """Resolved application data paths."""

    data_path: Path
    output_path: Path
    raw_vasp_cases: Path
    processed_data: Path


@dataclass(frozen=True)
class PhaseLogSettings:
    """Dedicated log files for parser, simulation, and workflow activity."""

    parser: Path
    simulation: Path
    workflow: Path


@dataclass(frozen=True)
class LoggingSettings:
    """Logging severity and destinations."""

    level: str
    console: bool
    file: Path | None
    phase_files: PhaseLogSettings


@dataclass(frozen=True)
class ValidatorSettings:
    """Scientific-validator limits."""

    energy_tolerance: float
    allowed_elements: tuple[str, ...]


@dataclass(frozen=True)
class CatkinasSettings:
    """Static CATKINAS adapter settings."""

    input_path: Path
    output_path: Path
    allow_warning: bool


@dataclass(frozen=True)
class ZacrosSettings:
    """Static Zacros adapter settings."""

    surface_config: Path
    output_path: Path
    allow_warning: bool


@dataclass(frozen=True)
class SimulationSettings:
    """External simulator commands and timeout."""

    catkinas_command: tuple[str, ...]
    zacros_command: tuple[str, ...]
    timeout: float


@dataclass(frozen=True)
class AnalysisSettings:
    """Simulation-result input root and output directory."""

    result_path: Path
    output_path: Path


@dataclass(frozen=True)
class ReportSettings:
    """Phase 9 report output and Markdown template paths."""

    output_path: Path
    template_path: Path


@dataclass(frozen=True)
class WorkflowSettings:
    """Deterministic Phase 10 backend and workflow artifact paths."""

    software: str
    output_root: Path


@dataclass(frozen=True)
class AppConfig:
    """Fully validated application configuration."""

    project_root: Path
    project: ProjectSettings
    paths: PathSettings
    logging: LoggingSettings
    validator: ValidatorSettings
    catkinas: CatkinasSettings
    zacros: ZacrosSettings
    simulation: SimulationSettings
    analysis: AnalysisSettings
    report: ReportSettings
    workflow: WorkflowSettings
