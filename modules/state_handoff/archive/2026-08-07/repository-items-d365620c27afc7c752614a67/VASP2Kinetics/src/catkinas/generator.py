"""Generate the bounded Phase 5 CATKINAS adapter package."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..exceptions import CatkinasGenerationError, RegistryError
from ..kinetics.registry import load
from ..kinetics.schema import ReactionRecord
from .mapping import MappingEntry, write_mapping
from .parameter_writer import write_parameter_file
from .reaction_writer import write_reaction_file
from .species_writer import write_species_file

LOGGER = logging.getLogger("vasp2kinetics.catkinas.generator")
_VALIDATION_STATES = {"PASS", "WARNING", "FAILED"}


def _load_validation_statuses(path: Path) -> dict[str, str]:
    """Load one strict reaction-to-validation-status mapping."""

    if not path.is_file():
        raise CatkinasGenerationError(
            f"Validation report does not exist: {path}"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatkinasGenerationError(
            f"Invalid JSON in validation report: {path}"
        ) from exc
    except OSError as exc:
        raise CatkinasGenerationError(
            f"Unable to read validation report: {path}"
        ) from exc

    checks = raw.get("checks") if isinstance(raw, dict) else None
    if not isinstance(checks, list):
        raise CatkinasGenerationError(
            "Validation report must contain a 'checks' list."
        )

    statuses: dict[str, str] = {}
    for item in checks:
        reaction_id = item.get("reaction_id") if isinstance(item, dict) else None
        status = item.get("overall_status") if isinstance(item, dict) else None
        if (
            not isinstance(reaction_id, str)
            or not reaction_id
            or status not in _VALIDATION_STATES
        ):
            raise CatkinasGenerationError(
                "Validation report contains an invalid reaction result."
            )
        if reaction_id in statuses:
            raise CatkinasGenerationError(
                f"Duplicate reaction ID in validation report: {reaction_id}"
            )
        statuses[reaction_id] = status
    return statuses


def _failure(reaction_id: str, status: str, reason: str) -> dict[str, str]:
    """Build one adapter generation issue record."""

    return {
        "reaction_id": reaction_id,
        "status": status,
        "reason": reason,
    }


def _select_records(
    records: list[ReactionRecord],
    validation_statuses: dict[str, str],
    allow_warning: bool,
) -> tuple[
    list[tuple[int, ReactionRecord, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Select only records eligible under existing validation and energy data."""

    ready: list[tuple[int, ReactionRecord, str]] = []
    failed: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for index, record in enumerate(records):
        reaction_id = record.reaction_id
        if reaction_id in seen_ids:
            failed.append(_failure(reaction_id, "FAILED", "duplicate reaction_id"))
            continue
        seen_ids.add(reaction_id)

        validation = validation_statuses.get(reaction_id)
        if validation is None:
            failed.append(_failure(reaction_id, "FAILED", "validation result not found"))
            continue
        if validation == "FAILED":
            failed.append(_failure(reaction_id, "FAILED", "validation status FAILED"))
            continue
        if validation == "WARNING" and not allow_warning:
            failed.append(_failure(reaction_id, "FAILED", "WARNING is not allowed"))
            continue
        if record.energetics.Ea_forward is None:
            failed.append(
                _failure(reaction_id, "NOT_READY", "missing activation energy")
            )
            continue
        if validation == "WARNING":
            warnings.append(
                _failure(reaction_id, "WARNING", "validation status WARNING")
            )
        ready.append((index, record, validation))
    return ready, failed, warnings


def _write_generation_report(report: dict[str, Any], path: Path) -> None:
    """Write the CATKINAS generation report as UTF-8 JSON."""

    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_catkinas_project(
    dataset_path: str | Path,
    validation_report_path: str | Path,
    output_path: str | Path,
    allow_warning: bool,
) -> dict[str, object]:
    """Generate static adapter files from eligible existing reaction records."""

    dataset_file = Path(dataset_path).expanduser().resolve()
    validation_file = Path(validation_report_path).expanduser().resolve()
    project_path = Path(output_path).expanduser().resolve()
    if not dataset_file.is_file():
        raise CatkinasGenerationError(f"Kinetic dataset does not exist: {dataset_file}")

    try:
        dataset = load(dataset_file)
    except RegistryError as exc:
        raise CatkinasGenerationError(str(exc)) from exc
    statuses = _load_validation_statuses(validation_file)
    ready, failed, warnings = _select_records(
        dataset.records,
        statuses,
        allow_warning,
    )
    records = [item[1] for item in ready]
    entries = [
        MappingEntry(
            reaction_id=record.reaction_id,
            catkinas_id=catkinas_id,
            dataset_record_index=index,
            source_path=record.calculation.source_path,
            validation_status=status,
        )
        for catkinas_id, (index, record, status) in enumerate(ready, start=1)
    ]

    try:
        project_path.mkdir(parents=True, exist_ok=True)
        write_species_file(records, project_path / "species.dat")
        write_reaction_file(records, project_path / "reactions.dat")
        write_parameter_file(records, project_path / "parameters.dat")
        write_mapping(entries, project_path / "mapping.json")
    except (OSError, TypeError, ValueError) as exc:
        raise CatkinasGenerationError(
            f"Unable to write CATKINAS adapter project: {project_path}"
        ) from exc

    report: dict[str, object] = {
        "dataset": str(dataset_file),
        "validation_report": str(validation_file),
        "output_path": str(project_path),
        "total_reactions": len(dataset.records),
        "generated": len(records),
        "failed": len(failed),
        "warnings": len(warnings),
        "failed_reason": failed,
        "warning_reactions": warnings,
    }
    try:
        _write_generation_report(report, project_path / "generation_report.json")
    except OSError as exc:
        raise CatkinasGenerationError(
            f"Unable to write generation report: {project_path}"
        ) from exc

    LOGGER.info("Generated CATKINAS adapter project: %s", report)
    return report
