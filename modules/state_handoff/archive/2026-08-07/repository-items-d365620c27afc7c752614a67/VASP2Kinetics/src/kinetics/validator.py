"""Read-only scientific checks for Phase 3 kinetic datasets."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..exceptions import KineticDataError, ResultWriteError
from .validation_structure import (
    FAILED,
    NOT_AVAILABLE,
    NOT_CHECKED,
    PASS,
    SOURCE_NOT_FOUND,
    WARNING,
    CheckResult,
    check_element_balance,
    check_required_fields,
    check_source,
)

LOGGER = logging.getLogger("vasp2kinetics.kinetics.validator")

def _energy_value(
    energetics: dict[str, Any],
    key: str,
) -> tuple[float | None, str]:
    """Read one optional energy value and return its availability state."""

    value = energetics.get(key)
    if value is None:
        return None, "missing"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "invalid"
    return float(value), "available"


def check_energy_balance(
    record: dict[str, Any],
    tolerance: float,
) -> CheckResult:
    """Check Ea_reverse = Ea_forward - E_reaction when all values exist."""

    energetics = record.get("energetics")
    if not isinstance(energetics, dict):
        return CheckResult(NOT_AVAILABLE, "Energetics section is not available.")

    values: dict[str, float] = {}
    missing: list[str] = []
    for key in ("Ea_forward", "Ea_reverse", "E_reaction"):
        value, state = _energy_value(energetics, key)
        if state == "invalid":
            return CheckResult(FAILED, f"Energy field '{key}' is not numeric.")
        if state == "missing":
            missing.append(key)
        elif value is not None:
            values[key] = value
    if missing:
        return CheckResult(
            NOT_AVAILABLE,
            f"Energy balance not checked; missing: {', '.join(missing)}.",
            {"missing": missing},
        )

    expected = values["Ea_forward"] - values["E_reaction"]
    difference = abs(values["Ea_reverse"] - expected)
    details = {
        "Ea_reverse_expected": expected,
        "Ea_reverse_recorded": values["Ea_reverse"],
        "difference": difference,
        "tolerance": tolerance,
    }
    if difference > tolerance:
        return CheckResult(FAILED, "Reverse barrier violates the energy relation.", details)
    return CheckResult(PASS, "Forward/reverse energy relation is consistent.", details)


def check_forward_barrier(record: dict[str, Any]) -> CheckResult:
    """Flag a negative forward barrier without changing it."""

    energetics = record.get("energetics")
    if not isinstance(energetics, dict):
        return CheckResult(NOT_AVAILABLE, "Energetics section is not available.")
    value, state = _energy_value(energetics, "Ea_forward")
    if state == "missing":
        return CheckResult(NOT_AVAILABLE, "Ea_forward is not available.")
    if state == "invalid" or value is None:
        return CheckResult(FAILED, "Ea_forward is not numeric.")
    if value < 0:
        return CheckResult(FAILED, "Ea_forward is negative.", {"Ea_forward": value})
    return CheckResult(PASS, "Ea_forward is non-negative.", {"Ea_forward": value})


def check_vasp_convergence(record: dict[str, Any]) -> CheckResult:
    """Check the stored Phase 2 VASP convergence flag."""

    quality = record.get("quality")
    value = quality.get("vasp_converged") if isinstance(quality, dict) else None
    if value is None:
        return CheckResult(NOT_AVAILABLE, "vasp_converged is not available.")
    if not isinstance(value, bool):
        return CheckResult(FAILED, "vasp_converged is not boolean.")
    if not value:
        return CheckResult(FAILED, "VASP result is recorded as not converged.")
    return CheckResult(PASS, "VASP result is recorded as converged.")


def check_ts_information(record: dict[str, Any]) -> CheckResult:
    """Check TS-related field presence without validating a TS."""

    energetics = record.get("energetics")
    quality = record.get("quality")
    candidate = energetics.get("candidate_TS_energy") if isinstance(energetics, dict) else None
    ts_verified = quality.get("ts_verified") if isinstance(quality, dict) else None

    if candidate is None:
        if ts_verified is True:
            return CheckResult(
                FAILED,
                "ts_verified is true but candidate_TS_energy is unavailable.",
            )
        return CheckResult(NOT_AVAILABLE, "candidate_TS_energy is not available.")
    if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
        return CheckResult(FAILED, "candidate_TS_energy is not numeric.")
    if not isinstance(ts_verified, bool):
        return CheckResult(FAILED, "TS verification status is not available.")
    return CheckResult(
        PASS,
        "TS candidate energy and verification-state field are present.",
        {"candidate_TS_energy": float(candidate), "ts_verified": ts_verified},
    )


def _overall_status(results: dict[str, CheckResult]) -> str:
    """Combine check states using the fixed failure-before-warning order."""

    statuses = {result.status for result in results.values()}
    if FAILED in statuses or SOURCE_NOT_FOUND in statuses:
        return FAILED
    if NOT_AVAILABLE in statuses or NOT_CHECKED in statuses:
        return WARNING
    return PASS


def validate_record(
    record: dict[str, Any],
    tolerance: float,
    allowed_elements: tuple[str, ...],
) -> dict[str, object]:
    """Run every independent check for one reaction record."""

    results = {
        "required_field": check_required_fields(record),
        "source": check_source(record),
        "element_balance": check_element_balance(record, allowed_elements),
        "energy_balance": check_energy_balance(record, tolerance),
        "barrier": check_forward_barrier(record),
        "vasp_convergence": check_vasp_convergence(record),
        "ts": check_ts_information(record),
    }
    reaction_id = record.get("reaction_id")
    return {
        "reaction_id": reaction_id if isinstance(reaction_id, str) else None,
        "checks": {name: result.status for name, result in results.items()},
        "messages": {name: result.message for name, result in results.items()},
        "details": {
            name: result.details for name, result in results.items() if result.details
        },
        "overall_status": _overall_status(results),
    }


def validate_dataset(
    path: str | Path,
    energy_tolerance: float,
    allowed_elements: tuple[str, ...],
) -> dict[str, object]:
    """Load a dataset and return a report without modifying the input."""

    dataset_path = Path(path).expanduser().resolve()
    if not dataset_path.is_file():
        raise KineticDataError(f"Kinetic dataset does not exist: {dataset_path}")
    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KineticDataError(f"Invalid JSON in kinetic dataset: {dataset_path}") from exc
    except OSError as exc:
        raise KineticDataError(f"Unable to read kinetic dataset: {dataset_path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("records"), list):
        raise KineticDataError("Kinetic dataset must contain a 'records' list.")

    reports: list[dict[str, object]] = []
    for raw_record in raw["records"]:
        record = raw_record if isinstance(raw_record, dict) else {}
        reports.append(validate_record(record, energy_tolerance, allowed_elements))

    statuses = [report["overall_status"] for report in reports]
    summary = {
        "total": len(reports),
        "passed": statuses.count(PASS),
        "warning": statuses.count(WARNING),
        "failed": statuses.count(FAILED),
    }
    LOGGER.info("Validated dataset=%s summary=%s", dataset_path, summary)
    return {
        "dataset": str(dataset_path),
        "summary": summary,
        "checks": reports,
    }


def write_validation_report(report: dict[str, object], path: str | Path) -> Path:
    """Write the validation report without touching the input dataset."""

    output_path = Path(path).expanduser().resolve()
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ResultWriteError(f"Unable to write validation report: {output_path}") from exc
    return output_path
