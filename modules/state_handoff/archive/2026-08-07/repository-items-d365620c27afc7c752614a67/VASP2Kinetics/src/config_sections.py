"""Reusable validation for scalar, command, and workflow config sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_models import SimulationSettings, WorkflowSettings
from .exceptions import ConfigurationError


def require_text(data: dict[str, Any], key: str, section: str) -> str:
    """Return one required non-empty text value."""

    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"Configuration value '{section}.{key}' must be a non-empty string."
        )
    return value.strip()


def resolve_project_path(project_root: Path, value: str) -> Path:
    """Resolve one configured path relative to the selected project root."""

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _require_command(data: dict[str, Any], key: str) -> tuple[str, ...]:
    """Load one executable command without shell parsing or interpolation."""

    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, list) and value and all(
        isinstance(part, str) and part.strip() for part in value
    ):
        return tuple(value)
    raise ConfigurationError(
        f"Configuration value 'simulation.{key}' must be a non-empty "
        "string or string list."
    )


def load_simulation_settings(data: dict[str, Any]) -> SimulationSettings:
    """Validate the external-command section as one bounded concern."""

    timeout = data.get("timeout")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ConfigurationError(
            "Configuration value 'simulation.timeout' must be a positive number."
        )
    return SimulationSettings(
        catkinas_command=_require_command(data, "catkinas_command"),
        zacros_command=_require_command(data, "zacros_command"),
        timeout=float(timeout),
    )


def load_workflow_settings(data: dict[str, Any], root: Path) -> WorkflowSettings:
    """Validate the explicit simulator choice and workflow-owned paths."""

    software = require_text(data, "software", "workflow").upper()
    if software not in {"CATKINAS", "ZACROS"}:
        raise ConfigurationError(
            "Configuration value 'workflow.software' must be CATKINAS or ZACROS."
        )
    return WorkflowSettings(
        software=software,
        output_root=resolve_project_path(
            root,
            require_text(data, "output_root", "workflow"),
        ),
    )
