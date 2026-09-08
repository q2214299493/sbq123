"""Validate reviewed kinetic-parameter handoffs without importing them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from ..exceptions import KineticDataError
from .handoff_support import (
    HandoffValidationResult,
    canonical_json_sha256,
    file_sha256,
    find_nonfinite,
    load_strict_json,
    resolve_contract_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "kinetic_parameter_handoff.schema.json"
REQUIRED_APPROVED_ROLES = {
    "INITIAL_ENERGY",
    "FINAL_ENERGY",
    "TRANSITION_STATE_ENERGY",
    "FREQUENCY_EVIDENCE",
    "CONNECTIVITY_EVIDENCE",
    "VALIDATION_REPORT",
    "REVIEW_EVIDENCE",
}
ENERGY_KEYS = (
    "initial",
    "final",
    "transition_state",
    "reaction",
    "activation_forward",
    "activation_reverse",
)


def _schema_errors(data: Any, schema_path: Path) -> list[str]:
    """Return stable JSON Schema validation messages."""

    schema = load_strict_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for issue in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in issue.absolute_path) or "$"
        errors.append(f"SCHEMA_ERROR:{location}:{issue.message}")
    return errors


def _source_checks(
    data: dict[str, Any],
    base: Path,
    errors: list[str],
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    """Check unique source IDs, local file metadata, and required roles."""

    sources = data.get("sources")
    if not isinstance(sources, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if not isinstance(source_id, str):
            continue
        if source_id in by_id:
            errors.append(f"DUPLICATE_SOURCE_ID:{source_id}")
            continue
        by_id[source_id] = source
        role = source.get("role")
        if isinstance(role, str):
            roles.add(role)
        if source.get("storage") != "LOCAL":
            warnings.append(f"SOURCE_NOT_REHASHED_LOCALLY:{source_id}")
            continue
        path_value = source.get("path")
        if not isinstance(path_value, str):
            continue
        source_path = resolve_contract_path(base, path_value)
        if not source_path.is_file():
            errors.append(f"LOCAL_SOURCE_NOT_FOUND:{source_id}")
            continue
        expected_size = source.get("size_bytes")
        if isinstance(expected_size, int) and source_path.stat().st_size != expected_size:
            errors.append(f"SOURCE_SIZE_MISMATCH:{source_id}")
        expected_hash = source.get("sha256")
        if isinstance(expected_hash, str) and file_sha256(source_path) != expected_hash:
            errors.append(f"SOURCE_HASH_MISMATCH:{source_id}")
    if data.get("status") == "APPROVED":
        for role in sorted(REQUIRED_APPROVED_ROLES - roles):
            errors.append(f"APPROVED_SOURCE_ROLE_MISSING:{role}")
    return by_id


def _dataset_checks(
    data: dict[str, Any],
    base: Path,
    errors: list[str],
) -> None:
    """Verify the dataset file and canonical bound reaction record."""

    binding = data.get("dataset_binding")
    if not isinstance(binding, dict) or data.get("status") != "APPROVED":
        return
    path_value = binding.get("path")
    if not isinstance(path_value, str):
        return
    dataset_path = resolve_contract_path(base, path_value)
    if not dataset_path.is_file():
        errors.append("BOUND_DATASET_NOT_FOUND")
        return
    if file_sha256(dataset_path) != binding.get("sha256"):
        errors.append("BOUND_DATASET_HASH_MISMATCH")
        return
    raw = load_strict_json(dataset_path)
    if not isinstance(raw, dict):
        errors.append("BOUND_DATASET_ROOT_NOT_OBJECT")
        return
    if raw.get("schema_version") != binding.get("schema_version"):
        errors.append("BOUND_DATASET_SCHEMA_VERSION_MISMATCH")
    records = raw.get("records")
    if not isinstance(records, list):
        errors.append("BOUND_DATASET_RECORDS_NOT_LIST")
        return
    reaction_id = binding.get("reaction_id")
    matches = [
        record
        for record in records
        if isinstance(record, dict) and record.get("reaction_id") == reaction_id
    ]
    if len(matches) != 1:
        errors.append("BOUND_REACTION_RECORD_NOT_UNIQUE")
        return
    if canonical_json_sha256(matches[0]) != binding.get("reaction_record_sha256"):
        errors.append("BOUND_REACTION_RECORD_HASH_MISMATCH")


def _energy_checks(
    data: dict[str, Any],
    source_ids: set[str],
    errors: list[str],
) -> None:
    """Check source references and the three required energy identities."""

    energetics = data.get("energetics")
    if not isinstance(energetics, dict):
        return
    values = energetics.get("values")
    if not isinstance(values, dict):
        return
    for key in ENERGY_KEYS:
        item = values.get(key)
        if not isinstance(item, dict):
            continue
        refs = item.get("source_ids")
        if isinstance(refs, list):
            for source_id in refs:
                if isinstance(source_id, str) and source_id not in source_ids:
                    errors.append(f"ENERGY_SOURCE_NOT_FOUND:{key}:{source_id}")
    if data.get("status") != "APPROVED":
        return
    numbers = {
        key: values[key]["value"]
        for key in ENERGY_KEYS
        if isinstance(values.get(key), dict)
        and isinstance(values[key].get("value"), (int, float))
        and not isinstance(values[key].get("value"), bool)
    }
    if len(numbers) != len(ENERGY_KEYS):
        return
    tolerance = energetics.get("consistency_tolerance_eV")
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
        return
    expected = {
        "reaction": numbers["final"] - numbers["initial"],
        "activation_forward": numbers["transition_state"] - numbers["initial"],
        "activation_reverse": numbers["transition_state"] - numbers["final"],
    }
    for key, expected_value in expected.items():
        if abs(numbers[key] - expected_value) > float(tolerance):
            errors.append(f"ENERGY_IDENTITY_MISMATCH:{key}")


def _reference_checks(
    data: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """Check report and manual-review references against source IDs."""

    validation = data.get("validation")
    review = data.get("review")
    for section, key in (
        (validation, "validation_report_source_id"),
        (review, "evidence_source_id"),
    ):
        if not isinstance(section, dict):
            continue
        source_id = section.get(key)
        if isinstance(source_id, str) and source_id not in sources:
            errors.append(f"SOURCE_REFERENCE_NOT_FOUND:{key}:{source_id}")


def validate_handoff(
    data: Any,
    base_directory: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA,
) -> HandoffValidationResult:
    """Validate one handoff and determine strict downstream eligibility."""

    base = Path(base_directory).expanduser().resolve()
    schema = Path(schema_path).expanduser().resolve()
    errors = _schema_errors(data, schema)
    warnings: list[str] = []
    find_nonfinite(data, "$", errors)
    if not isinstance(data, dict):
        return HandoffValidationResult("FAILED", False, tuple(errors), ())
    sources = _source_checks(data, base, errors, warnings)
    _dataset_checks(data, base, errors)
    _energy_checks(data, set(sources), errors)
    _reference_checks(data, sources, errors)
    if data.get("status") != "APPROVED":
        warnings.append("HANDOFF_NOT_APPROVED")
    eligible = not errors and data.get("status") == "APPROVED"
    status = "ELIGIBLE" if eligible else ("FAILED" if errors else "VALID_NOT_ELIGIBLE")
    return HandoffValidationResult(
        status,
        eligible,
        tuple(dict.fromkeys(errors)),
        tuple(dict.fromkeys(warnings)),
    )


def validate_handoff_file(
    path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA,
) -> HandoffValidationResult:
    """Load and validate one handoff file relative to its parent directory."""

    source = Path(path).expanduser().resolve()
    return validate_handoff(load_strict_json(source), source.parent, schema_path)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one handoff and print a machine-readable result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    try:
        result = validate_handoff_file(args.handoff, args.schema)
    except KineticDataError as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if result.eligible:
        return 0
    return 2 if result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
