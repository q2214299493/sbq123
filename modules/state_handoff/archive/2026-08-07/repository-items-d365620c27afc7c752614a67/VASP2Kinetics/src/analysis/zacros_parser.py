"""Parse explicit and native Zacros outputs without mechanism interpretation."""

from __future__ import annotations

import logging
import math
from pathlib import Path

from .parser_utils import (
    ParseFormatError,
    load_reaction_mapping,
    map_reaction_values,
    read_key_value_file,
    read_scalar_file,
    resolve_input_context,
    result_status,
)
from .result_schema import Conditions, ResultSource, SimulationResult

LOGGER = logging.getLogger("vasp2kinetics.analysis.zacros")
_EXPECTED_FILES = {
    "conditions.dat",
    "coverage.dat",
    "event_frequency.dat",
    "mapping.json",
    "procstat_output.txt",
    "selectivity.dat",
    "specnum_output.txt",
    "tof.dat",
}


def _parse_procstat(path: Path) -> dict[str, float]:
    """Extract final Zacros event frequencies from process statistics."""

    try:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        raise ParseFormatError("PROCSTAT_READ_ERROR") from exc
    if not lines or not lines[0].split() or lines[0].split()[0] != "Overall":
        raise ParseFormatError("PROCSTAT_FORMAT_ERROR")
    event_count = len(lines[0].split()) - 1
    indices = [
        index for index, line in enumerate(lines) if line.startswith("configuration")
    ]
    if event_count <= 0 or not indices or indices[-1] + 2 >= len(lines):
        raise ParseFormatError("PROCSTAT_FORMAT_ERROR")
    tokens = lines[indices[-1]].split()
    waiting_times = lines[indices[-1] + 1].split()
    counts = lines[indices[-1] + 2].split()
    if (
        len(tokens) != 4
        or len(waiting_times) != event_count + 1
        or len(counts) != event_count + 1
    ):
        raise ParseFormatError("PROCSTAT_FORMAT_ERROR")
    try:
        configuration_number = int(tokens[1])
        total_events = int(tokens[2])
        time_value = float(tokens[3])
        waiting_values = [float(value) for value in waiting_times]
        count_values = [int(value) for value in counts]
    except ValueError as exc:
        raise ParseFormatError("PROCSTAT_INVALID_NUMBER") from exc
    if not math.isfinite(time_value) or any(
        not math.isfinite(value) for value in waiting_values
    ):
        raise ParseFormatError("PROCSTAT_INVALID_NUMBER")
    event_values = count_values[1:]
    if (
        configuration_number <= 0
        or total_events < 0
        or any(value < 0 for value in count_values)
        or count_values[0] != total_events
        or count_values[0] != sum(event_values)
    ):
        raise ParseFormatError("PROCSTAT_INVALID_NUMBER")
    if time_value < 0 or (time_value == 0 and any(event_values)):
        raise ParseFormatError("PROCSTAT_INVALID_TIME")
    if time_value == 0:
        return {str(index): 0.0 for index in range(1, event_count + 1)}
    return {
        str(index): value / time_value
        for index, value in enumerate(event_values, start=1)
    }


def _specnum_temperature(path: Path) -> float:
    """Read the final explicit temperature from species-number output."""

    try:
        lines = [
            line.split()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        raise ParseFormatError("SPECNUM_READ_ERROR") from exc
    if len(lines) < 2 or "Temperature" not in lines[0]:
        raise ParseFormatError("SPECNUM_FORMAT_ERROR")
    if len(lines[-1]) != len(lines[0]):
        raise ParseFormatError("SPECNUM_FORMAT_ERROR")
    try:
        temperature = float(lines[-1][lines[0].index("Temperature")])
    except ValueError as exc:
        raise ParseFormatError("SPECNUM_INVALID_NUMBER") from exc
    if not math.isfinite(temperature):
        raise ParseFormatError("SPECNUM_INVALID_NUMBER")
    return temperature


def _coverage(source: Path) -> tuple[dict[str, float], list[str], bool]:
    """Read normalized coverage data and its parse diagnostics."""

    path = source / "coverage.dat"
    if path.is_file():
        try:
            return read_key_value_file(path, "COVERAGE"), [], False
        except ParseFormatError as exc:
            return {}, [str(exc)], True
    if (source / "specnum_output.txt").is_file():
        return {}, ["COVERAGE_REQUIRES_EXPLICIT_NORMALIZATION"], False
    return {}, ["COVERAGE_FILE_NOT_FOUND"], False


def _reaction_rates(source: Path) -> tuple[dict[str, float], list[str], bool]:
    """Read explicitly supported event-frequency data."""

    try:
        if (source / "event_frequency.dat").is_file():
            raw = read_key_value_file(
                source / "event_frequency.dat",
                "EVENT_FREQUENCY",
            )
        elif (source / "procstat_output.txt").is_file():
            raw = _parse_procstat(source / "procstat_output.txt")
        else:
            return {}, ["EVENT_FREQUENCY_FILE_NOT_FOUND"], False
        reverse, reaction_ids = load_reaction_mapping(
            source / "mapping.json",
            "zacros_id",
        )
        return map_reaction_values(raw, reverse, reaction_ids), [], False
    except ParseFormatError as exc:
        return {}, [str(exc)], True


def _tof(source: Path) -> tuple[float | None, list[str], bool]:
    """Read an explicitly exported TOF scalar."""

    path = source / "tof.dat"
    if not path.is_file():
        return None, ["TOF_FILE_NOT_FOUND"], False
    try:
        return read_scalar_file(path, "TOF"), [], False
    except ParseFormatError as exc:
        return None, [str(exc)], True


def _metadata(
    source: Path,
) -> tuple[Conditions, dict[str, float], list[str], bool]:
    """Read optional conditions and selectivity exports."""

    conditions = Conditions()
    selectivity: dict[str, float] = {}
    try:
        if (source / "conditions.dat").is_file():
            values = read_key_value_file(source / "conditions.dat", "CONDITIONS")
            if set(values) - {"temperature", "pressure"}:
                raise ParseFormatError("CONDITIONS_UNSUPPORTED_FIELD")
            conditions = Conditions(
                temperature=values.get("temperature"),
                pressure=values.get("pressure"),
            )
        elif (source / "specnum_output.txt").is_file():
            conditions = Conditions(
                temperature=_specnum_temperature(source / "specnum_output.txt")
            )
        if (source / "selectivity.dat").is_file():
            selectivity = read_key_value_file(
                source / "selectivity.dat",
                "SELECTIVITY",
            )
    except ParseFormatError as exc:
        return conditions, selectivity, [str(exc)], True
    return conditions, selectivity, [], False


def _failed_result(
    input_path: Path,
    errors: list[str],
) -> tuple[SimulationResult, dict[str, object]]:
    """Build a traceable failed Zacros parse result."""

    result = SimulationResult(
        simulation_id="",
        software="Zacros",
        status="FAILED",
        source=ResultSource(path=str(input_path)),
    )
    log = {
        "software": "Zacros",
        "input_path": str(input_path),
        "source_path": str(input_path),
        "status": "FAILED",
        "files": {},
        "errors": errors,
        "warnings": [],
    }
    return result, log


def parse_zacros_result(
    output_path: str | Path,
) -> tuple[SimulationResult, dict[str, object]]:
    """Parse Zacros event statistics and explicit normalized result exports."""

    input_path = Path(output_path).expanduser().resolve()
    if not input_path.is_dir():
        return _failed_result(input_path, ["OUTPUT_DIRECTORY_NOT_FOUND"])
    try:
        context = resolve_input_context(input_path, _EXPECTED_FILES - {"mapping.json"})
    except ParseFormatError as exc:
        return _failed_result(input_path, [str(exc)])

    source = context.source_path
    files = {name: (source / name).is_file() for name in sorted(_EXPECTED_FILES)}
    coverage, coverage_errors, coverage_fatal = _coverage(source)
    reaction_rates, rate_errors, rate_fatal = _reaction_rates(source)
    tof, tof_errors, tof_fatal = _tof(source)
    conditions, selectivity, metadata_errors, metadata_fatal = _metadata(source)
    errors = coverage_errors + rate_errors + tof_errors + metadata_errors
    warnings: list[str] = []
    fatal = coverage_fatal or rate_fatal or tof_fatal or metadata_fatal
    available = sum((bool(coverage), bool(reaction_rates), tof is not None))

    status = result_status(available, 3, fatal)
    result = SimulationResult(
        simulation_id=context.simulation_id,
        software="Zacros",
        status=status,
        conditions=conditions,
        coverage=coverage,
        reaction_rates=reaction_rates,
        tof=tof,
        selectivity=selectivity,
        source=ResultSource(path=str(source)),
    )
    parser_log: dict[str, object] = {
        "software": "Zacros",
        "input_path": str(input_path),
        "source_path": str(source),
        "status": status,
        "files": files,
        "errors": errors,
        "warnings": warnings,
    }
    LOGGER.info("Parsed Zacros output: %s", parser_log)
    return result, parser_log
