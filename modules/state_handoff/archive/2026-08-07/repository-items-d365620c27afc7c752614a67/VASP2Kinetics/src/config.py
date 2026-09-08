"""Load and validate the VASP2Kinetics YAML configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config_models import (
    AnalysisSettings,
    AppConfig,
    CatkinasSettings,
    LoggingSettings,
    PhaseLogSettings,
    PathSettings,
    ProjectSettings,
    ReportSettings,
    ValidatorSettings,
    ZacrosSettings,
)
from .config_sections import (
    load_simulation_settings,
    load_workflow_settings,
    require_text,
    resolve_project_path,
)
from .exceptions import ConfigurationError

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return one required configuration mapping."""

    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration section '{key}' must be a mapping.")
    return value


def load_config(
    config_path: str | Path,
    project_root: str | Path | None = None,
) -> AppConfig:
    """Read and validate a YAML configuration file without inventing defaults."""

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f"Configuration file does not exist: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in configuration file: {path}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Unable to read configuration file: {path}") from exc

    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration root must be a mapping.")

    project_data = _require_mapping(raw, "project")
    paths_data = _require_mapping(raw, "paths")
    logging_data = _require_mapping(raw, "logging")
    phase_log_data = _require_mapping(logging_data, "phase_files")
    validator_data = _require_mapping(raw, "validator")
    catkinas_data = _require_mapping(raw, "catkinas")
    zacros_data = _require_mapping(raw, "zacros")
    simulation_data = _require_mapping(raw, "simulation")
    analysis_data = _require_mapping(raw, "analysis")
    report_data = _require_mapping(raw, "report")
    workflow_data = _require_mapping(raw, "workflow")

    resolved_root = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else path.parent.parent
    )
    project = ProjectSettings(
        name=require_text(project_data, "name", "project"),
        version=require_text(project_data, "version", "project"),
    )
    paths = PathSettings(
        data_path=resolve_project_path(
            resolved_root,
            require_text(paths_data, "data_path", "paths"),
        ),
        output_path=resolve_project_path(
            resolved_root,
            require_text(paths_data, "output_path", "paths"),
        ),
        raw_vasp_cases=resolve_project_path(
            resolved_root,
            require_text(paths_data, "raw_vasp_cases", "paths"),
        ),
        processed_data=resolve_project_path(
            resolved_root,
            require_text(paths_data, "processed_data", "paths"),
        ),
    )

    level = require_text(logging_data, "level", "logging").upper()
    if level not in _LOG_LEVELS:
        allowed = ", ".join(sorted(_LOG_LEVELS))
        raise ConfigurationError(
            f"Configuration value 'logging.level' must be one of: {allowed}."
        )

    console = logging_data.get("console")
    if not isinstance(console, bool):
        raise ConfigurationError(
            "Configuration value 'logging.console' must be true or false."
        )

    file_value = logging_data.get("file")
    if file_value is not None and (
        not isinstance(file_value, str) or not file_value.strip()
    ):
        raise ConfigurationError(
            "Configuration value 'logging.file' must be null or a non-empty path."
        )
    log_file = (
        resolve_project_path(resolved_root, file_value.strip())
        if isinstance(file_value, str)
        else None
    )
    if not console and log_file is None:
        raise ConfigurationError(
            "At least one logging destination must be enabled."
        )

    energy_tolerance = validator_data.get("energy_tolerance")
    if (
        isinstance(energy_tolerance, bool)
        or not isinstance(energy_tolerance, (int, float))
        or energy_tolerance < 0
    ):
        raise ConfigurationError(
            "Configuration value 'validator.energy_tolerance' "
            "must be a non-negative number."
        )

    allowed_elements = validator_data.get("allowed_elements")
    if not isinstance(allowed_elements, list) or not allowed_elements:
        raise ConfigurationError(
            "Configuration value 'validator.allowed_elements' "
            "must be a non-empty list."
        )
    if any(
        not isinstance(element, str) or not element.strip()
        for element in allowed_elements
    ):
        raise ConfigurationError(
            "Configuration value 'validator.allowed_elements' "
            "must contain non-empty strings."
        )
    normalized_elements = tuple(element.strip() for element in allowed_elements)
    if len(set(normalized_elements)) != len(normalized_elements):
        raise ConfigurationError(
            "Configuration value 'validator.allowed_elements' "
            "must not contain duplicates."
        )

    catkinas_input = resolve_project_path(
        resolved_root,
        require_text(catkinas_data, "input_path", "catkinas"),
    )
    catkinas_output = resolve_project_path(
        resolved_root,
        require_text(catkinas_data, "output_path", "catkinas"),
    )
    allow_warning = catkinas_data.get("allow_warning")
    if not isinstance(allow_warning, bool):
        raise ConfigurationError(
            "Configuration value 'catkinas.allow_warning' must be true or false."
        )

    zacros_surface = resolve_project_path(
        resolved_root,
        require_text(zacros_data, "surface_config", "zacros"),
    )
    zacros_output = resolve_project_path(
        resolved_root,
        require_text(zacros_data, "output_path", "zacros"),
    )
    zacros_allow_warning = zacros_data.get("allow_warning")
    if not isinstance(zacros_allow_warning, bool):
        raise ConfigurationError(
            "Configuration value 'zacros.allow_warning' must be true or false."
        )

    return AppConfig(
        project_root=resolved_root,
        project=project,
        paths=paths,
        logging=LoggingSettings(
            level=level,
            console=console,
            file=log_file,
            phase_files=PhaseLogSettings(
                parser=resolve_project_path(
                    resolved_root,
                    require_text(phase_log_data, "parser", "logging.phase_files"),
                ),
                simulation=resolve_project_path(
                    resolved_root,
                    require_text(
                        phase_log_data,
                        "simulation",
                        "logging.phase_files",
                    ),
                ),
                workflow=resolve_project_path(
                    resolved_root,
                    require_text(phase_log_data, "workflow", "logging.phase_files"),
                ),
            ),
        ),
        validator=ValidatorSettings(
            energy_tolerance=float(energy_tolerance),
            allowed_elements=normalized_elements,
        ),
        catkinas=CatkinasSettings(
            input_path=catkinas_input,
            output_path=catkinas_output,
            allow_warning=allow_warning,
        ),
        zacros=ZacrosSettings(
            surface_config=zacros_surface,
            output_path=zacros_output,
            allow_warning=zacros_allow_warning,
        ),
        simulation=load_simulation_settings(simulation_data),
        analysis=AnalysisSettings(
            result_path=resolve_project_path(
                resolved_root,
                require_text(analysis_data, "result_path", "analysis"),
            ),
            output_path=resolve_project_path(
                resolved_root,
                require_text(analysis_data, "output_path", "analysis"),
            ),
        ),
        report=ReportSettings(
            output_path=resolve_project_path(
                resolved_root,
                require_text(report_data, "output_path", "report"),
            ),
            template_path=resolve_project_path(
                resolved_root,
                require_text(report_data, "template_path", "report"),
            ),
        ),
        workflow=load_workflow_settings(workflow_data, resolved_root),
    )
