"""Persist raw process output and append-only execution metadata."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..exceptions import RunnerError


@dataclass(frozen=True)
class ExecutionRecord:
    """Auditable metadata for one external process attempt."""

    simulation_id: str
    software: str
    input_path: str
    start_time: str
    end_time: str
    status: str
    return_code: int | None
    runtime: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


def _write_json(path: Path, value: Any) -> None:
    """Write one UTF-8 indented JSON file."""

    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_run_artifacts(
    output_directory: str | Path,
    record: ExecutionRecord,
    stdout: str,
    stderr: str,
) -> None:
    """Write the latest raw streams and status without interpreting them."""

    output_path = Path(output_directory)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "stdout.log").write_text(stdout, encoding="utf-8")
        (output_path / "stderr.log").write_text(stderr, encoding="utf-8")
        _write_json(output_path / "run_status.json", record.to_dict())
    except OSError as exc:
        raise RunnerError(
            f"Unable to write simulation run artifacts: {output_path}"
        ) from exc


def append_execution_history(
    history_path: str | Path,
    record: ExecutionRecord,
) -> None:
    """Append one record while rejecting malformed existing history."""

    path = Path(history_path)
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise RunnerError("Execution history root must be a list.")
            history = raw
        else:
            history = []
        history.append(record.to_dict())
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        _write_json(temporary_path, history)
        temporary_path.replace(path)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"Invalid JSON in execution history: {path}") from exc
    except OSError as exc:
        raise RunnerError(f"Unable to update execution history: {path}") from exc
