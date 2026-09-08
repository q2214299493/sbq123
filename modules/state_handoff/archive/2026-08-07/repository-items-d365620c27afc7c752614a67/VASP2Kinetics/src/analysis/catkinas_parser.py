"""Parse explicit CATKINAS result exports without scientific interpretation."""

from __future__ import annotations

import logging
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

LOGGER = logging.getLogger("vasp2kinetics.analysis.catkinas")
_EXPECTED_FILES = {
    "conditions.dat",
    "coverage.dat",
    "mapping.json",
    "reaction_rates.dat",
    "selectivity.dat",
    "tof.dat",
}


def _conditions(path: Path) -> Conditions:
    """Read optional CATKINAS conditions from an explicit export."""

    values = read_key_value_file(path, "CONDITIONS")
    if set(values) - {"temperature", "pressure"}:
        raise ParseFormatError("CONDITIONS_UNSUPPORTED_FIELD")
    return Conditions(
        temperature=values.get("temperature"),
        pressure=values.get("pressure"),
    )


def _failed_result(
    input_path: Path,
    simulation_id: str,
    errors: list[str],
) -> tuple[SimulationResult, dict[str, object]]:
    """Build a traceable failed CATKINAS parse result."""

    result = SimulationResult(
        simulation_id=simulation_id,
        software="CATKINAS",
        status="FAILED",
        source=ResultSource(path=str(input_path)),
    )
    return result, {
        "software": "CATKINAS",
        "input_path": str(input_path),
        "source_path": str(input_path),
        "status": "FAILED",
        "files": {},
        "errors": errors,
        "warnings": [],
    }


def parse_catkinas_result(
    output_path: str | Path,
) -> tuple[SimulationResult, dict[str, object]]:
    """Parse strict CATKINAS text exports and preserve Phase 5 reaction IDs."""

    input_path = Path(output_path).expanduser().resolve()
    if not input_path.is_dir():
        return _failed_result(input_path, "", ["OUTPUT_DIRECTORY_NOT_FOUND"])
    try:
        context = resolve_input_context(input_path, _EXPECTED_FILES - {"mapping.json"})
    except ParseFormatError as exc:
        return _failed_result(input_path, "", [str(exc)])

    source = context.source_path
    files = {name: (source / name).is_file() for name in sorted(_EXPECTED_FILES)}
    errors: list[str] = []
    warnings: list[str] = []
    fatal = False
    coverage: dict[str, float] = {}
    reaction_rates: dict[str, float] = {}
    selectivity: dict[str, float] = {}
    conditions = Conditions()
    tof: float | None = None
    available = 0

    coverage_path = source / "coverage.dat"
    if coverage_path.is_file():
        try:
            coverage = read_key_value_file(coverage_path, "COVERAGE")
            available += 1
        except ParseFormatError as exc:
            errors.append(str(exc))
            fatal = True
    else:
        errors.append("COVERAGE_FILE_NOT_FOUND")

    rates_path = source / "reaction_rates.dat"
    if rates_path.is_file():
        try:
            raw_rates = read_key_value_file(rates_path, "REACTION_RATES")
            reverse, reaction_ids = load_reaction_mapping(
                source / "mapping.json",
                "catkinas_id",
            )
            reaction_rates = map_reaction_values(raw_rates, reverse, reaction_ids)
            available += 1
        except ParseFormatError as exc:
            errors.append(str(exc))
            fatal = True
    else:
        errors.append("REACTION_RATES_FILE_NOT_FOUND")

    tof_path = source / "tof.dat"
    if tof_path.is_file():
        try:
            tof = read_scalar_file(tof_path, "TOF")
            available += 1
        except ParseFormatError as exc:
            errors.append(str(exc))
            fatal = True
    else:
        errors.append("TOF_FILE_NOT_FOUND")

    try:
        if (source / "conditions.dat").is_file():
            conditions = _conditions(source / "conditions.dat")
        if (source / "selectivity.dat").is_file():
            selectivity = read_key_value_file(
                source / "selectivity.dat",
                "SELECTIVITY",
            )
    except ParseFormatError as exc:
        errors.append(str(exc))
        fatal = True

    native_mat = list(source.glob("data*.mat")) or list(
        source.glob("result_*/data*.mat")
    )
    if native_mat:
        warnings.append("CATKINAS_NATIVE_MAT_NOT_PARSED")

    status = result_status(available, 3, fatal)
    result = SimulationResult(
        simulation_id=context.simulation_id,
        software="CATKINAS",
        status=status,
        conditions=conditions,
        coverage=coverage,
        reaction_rates=reaction_rates,
        tof=tof,
        selectivity=selectivity,
        source=ResultSource(path=str(source)),
    )
    parser_log: dict[str, object] = {
        "software": "CATKINAS",
        "input_path": str(input_path),
        "source_path": str(source),
        "status": status,
        "files": files,
        "errors": errors,
        "warnings": warnings,
    }
    LOGGER.info("Parsed CATKINAS output: %s", parser_log)
    return result, parser_log
