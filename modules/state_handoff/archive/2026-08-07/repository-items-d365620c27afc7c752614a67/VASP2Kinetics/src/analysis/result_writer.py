"""Write unified simulation results and parser diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..exceptions import AnalysisError
from .result_schema import SimulationResult


def _write_json(path: Path, value: Any) -> None:
    """Write one UTF-8 indented JSON file."""

    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_result_files(
    result: SimulationResult,
    parser_log: dict[str, object],
    output_path: str | Path,
) -> tuple[Path, Path]:
    """Write both Phase 8 files without modifying any simulator output."""

    directory = Path(output_path).expanduser().resolve()
    result_path = directory / "simulation_result.json"
    log_path = directory / "parser_log.json"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _write_json(result_path, result.to_dict())
        _write_json(log_path, parser_log)
    except OSError as exc:
        raise AnalysisError(f"Unable to write analysis output: {directory}") from exc
    return result_path, log_path
