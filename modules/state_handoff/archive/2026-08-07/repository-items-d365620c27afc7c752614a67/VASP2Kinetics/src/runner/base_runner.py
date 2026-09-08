"""Common subprocess execution and auditable run lifecycle."""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Sequence

from .execution_log import (
    ExecutionRecord,
    append_execution_history,
    write_run_artifacts,
)

ExecutionStatus = Literal[
    "SUCCESS",
    "FAILED",
    "TIMEOUT",
    "EXECUTABLE_NOT_FOUND",
    "INPUT_NOT_FOUND",
]

LOGGER = logging.getLogger("vasp2kinetics.runner")


@dataclass(frozen=True)
class ExecutionResult:
    """Uninterpreted outcome of one external process invocation."""

    status: ExecutionStatus
    return_code: int | None
    stdout: str
    stderr: str
    runtime: float


def _stream_text(value: str | bytes | None) -> str:
    """Normalize captured subprocess output to text."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class BaseRunner:
    """Execute one configured command in an existing input directory."""

    software = "UNKNOWN"

    def __init__(
        self,
        command: Sequence[str],
        timeout: float,
        output_directory: str | Path,
        history_path: str | Path,
    ) -> None:
        """Validate and store one shell-free external command configuration."""

        if not command or any(
            not isinstance(part, str) or not part.strip() for part in command
        ):
            raise ValueError("command must contain non-empty strings.")
        if timeout <= 0:
            raise ValueError("timeout must be positive.")
        self.command = tuple(command)
        self.timeout = float(timeout)
        self.output_directory = Path(output_directory).expanduser().resolve()
        self.history_path = Path(history_path).expanduser().resolve()

    def execute_command(
        self,
        command: Sequence[str],
        working_directory: str | Path,
        timeout: float,
    ) -> ExecutionResult:
        """Execute without a shell and return raw streams plus process status."""

        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(command),
                cwd=Path(working_directory),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            return ExecutionResult(
                "EXECUTABLE_NOT_FOUND",
                None,
                "",
                str(exc),
                time.monotonic() - started,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                "TIMEOUT",
                None,
                _stream_text(exc.stdout),
                _stream_text(exc.stderr),
                time.monotonic() - started,
            )
        except OSError as exc:
            return ExecutionResult(
                "FAILED",
                None,
                "",
                str(exc),
                time.monotonic() - started,
            )

        status: ExecutionStatus = (
            "SUCCESS" if completed.returncode == 0 else "FAILED"
        )
        return ExecutionResult(
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
            time.monotonic() - started,
        )

    def run(self, input_path: str | Path) -> ExecutionResult:
        """Run once, save raw artifacts, and append execution history."""

        input_directory = Path(input_path).expanduser().resolve()
        simulation_id = f"{self.software.lower()}-{uuid.uuid4().hex}"
        start_time = datetime.now(timezone.utc)
        LOGGER.info(
            "Simulation started: id=%s software=%s input=%s",
            simulation_id,
            self.software,
            input_directory,
        )

        if not input_directory.is_dir():
            result = ExecutionResult(
                "INPUT_NOT_FOUND",
                None,
                "",
                f"Input directory does not exist: {input_directory}",
                0.0,
            )
        else:
            result = self.execute_command(
                self.command,
                input_directory,
                self.timeout,
            )

        end_time = datetime.now(timezone.utc)
        record = ExecutionRecord(
            simulation_id=simulation_id,
            software=self.software,
            input_path=str(input_directory),
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            status=result.status,
            return_code=result.return_code,
            runtime=result.runtime,
        )
        write_run_artifacts(
            self.output_directory,
            record,
            result.stdout,
            result.stderr,
        )
        append_execution_history(self.history_path, record)

        log_method = LOGGER.info if result.status == "SUCCESS" else LOGGER.error
        log_method(
            "Simulation ended: id=%s software=%s status=%s return_code=%s runtime=%.6f",
            simulation_id,
            self.software,
            result.status,
            result.return_code,
            result.runtime,
        )
        return result
