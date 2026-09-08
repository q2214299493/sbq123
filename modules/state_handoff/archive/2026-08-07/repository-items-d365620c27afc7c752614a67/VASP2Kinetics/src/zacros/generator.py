"""Generate the bounded Phase 6 Zacros adapter package."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..exceptions import RegistryError, ZacrosGenerationError
from ..kinetics.registry import load
from ..kinetics.schema import ReactionRecord
from .energetics_writer import write_energetics_file
from .lattice_writer import SurfaceConfig, load_surface_config, write_lattice_file
from .mapping import MappingEntry, write_mapping
from .mechanism_writer import MechanismEntry, write_mechanism_file
from .species_writer import write_species_file

LOGGER = logging.getLogger("vasp2kinetics.zacros.generator")
_VALIDATION_STATES = {"PASS", "WARNING", "FAILED"}


def _load_validation_statuses(path: Path) -> dict[str, str]:
    """Load one strict reaction-to-validation-status mapping."""

    if not path.is_file():
        raise ZacrosGenerationError(f"Validation report does not exist: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ZacrosGenerationError(
            f"Invalid JSON in validation report: {path}"
        ) from exc
    except OSError as exc:
        raise ZacrosGenerationError(
            f"Unable to read validation report: {path}"
        ) from exc

    checks = raw.get("checks") if isinstance(raw, dict) else None
    if not isinstance(checks, list):
        raise ZacrosGenerationError("Validation report must contain a 'checks' list.")

    statuses: dict[str, str] = {}
    for item in checks:
        reaction_id = item.get("reaction_id") if isinstance(item, dict) else None
        status = item.get("overall_status") if isinstance(item, dict) else None
        if (
            not isinstance(reaction_id, str)
            or not reaction_id
            or status not in _VALIDATION_STATES
        ):
            raise ZacrosGenerationError(
                "Validation report contains an invalid reaction result."
            )
        if reaction_id in statuses:
            raise ZacrosGenerationError(
                f"Duplicate reaction ID in validation report: {reaction_id}"
            )
        statuses[reaction_id] = status
    return statuses


def _issue(reaction_id: str, status: str, reason: str) -> dict[str, str]:
    """Build one Zacros generation issue record."""

    return {"reaction_id": reaction_id, "status": status, "reason": reason}


def _select_records(
    records: list[ReactionRecord],
    validation_statuses: dict[str, str],
    surface: SurfaceConfig,
    allow_warning: bool,
) -> tuple[
    list[tuple[int, ReactionRecord, str, str | None]],
    list[dict[str, str]],
    list[dict[str, object]],
]:
    """Select records eligible under validation, energy, and site data."""

    ready: list[tuple[int, ReactionRecord, str, str | None]] = []
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for index, record in enumerate(records):
        reaction_id = record.reaction_id
        if reaction_id in seen_ids:
            errors.append(_issue(reaction_id, "FAILED", "duplicate reaction_id"))
            continue
        seen_ids.add(reaction_id)

        validation = validation_statuses.get(reaction_id)
        if validation is None:
            errors.append(_issue(reaction_id, "FAILED", "validation result not found"))
            continue
        if validation == "FAILED":
            errors.append(_issue(reaction_id, "FAILED", "validation status FAILED"))
            continue
        if validation == "WARNING" and not allow_warning:
            errors.append(_issue(reaction_id, "FAILED", "WARNING is not allowed"))
            continue
        if record.energetics.Ea_forward is None:
            errors.append(_issue(reaction_id, "FAILED", "missing activation energy"))
            continue

        site = surface.reaction_sites.get(reaction_id)
        warning_reasons: list[str] = []
        if site is None:
            if not allow_warning:
                errors.append(_issue(reaction_id, "FAILED", "missing site information"))
                continue
            warning_reasons.append("missing site information")
        elif site not in surface.sites:
            errors.append(
                _issue(
                    reaction_id,
                    "FAILED",
                    f"site not declared in surface configuration: {site}",
                )
            )
            continue

        if validation == "WARNING":
            warning_reasons.append("validation status WARNING")
        if warning_reasons:
            warnings.append(
                {
                    "reaction_id": reaction_id,
                    "status": "WARNING",
                    "reasons": warning_reasons,
                }
            )
        ready.append((index, record, validation, site))
    return ready, errors, warnings


def _write_generation_report(report: dict[str, Any], path: Path) -> None:
    """Write the Zacros generation report as UTF-8 JSON."""

    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_zacros_project(
    dataset_path: str | Path,
    validation_report_path: str | Path,
    surface_config_path: str | Path,
    output_path: str | Path,
    allow_warning: bool,
) -> dict[str, object]:
    """Generate static Zacros adapter files from eligible existing records."""

    dataset_file = Path(dataset_path).expanduser().resolve()
    validation_file = Path(validation_report_path).expanduser().resolve()
    surface_file = Path(surface_config_path).expanduser().resolve()
    project_path = Path(output_path).expanduser().resolve()
    if not dataset_file.is_file():
        raise ZacrosGenerationError(f"Kinetic dataset does not exist: {dataset_file}")

    try:
        dataset = load(dataset_file)
    except RegistryError as exc:
        raise ZacrosGenerationError(str(exc)) from exc
    statuses = _load_validation_statuses(validation_file)
    surface = load_surface_config(surface_file)
    ready, errors, warnings = _select_records(
        dataset.records,
        statuses,
        surface,
        allow_warning,
    )

    records = [item[1] for item in ready]
    mechanisms = [MechanismEntry(record=item[1], site=item[3]) for item in ready]
    mappings = [
        MappingEntry(
            reaction_id=record.reaction_id,
            zacros_id=zacros_id,
            dataset_record_index=index,
            source_path=record.calculation.source_path,
            activation_energy=record.energetics.Ea_forward,
            reaction_energy=record.energetics.E_reaction,
            validation_status=status,
            site=site,
        )
        for zacros_id, (index, record, status, site) in enumerate(ready, start=1)
        if record.energetics.Ea_forward is not None
    ]

    try:
        project_path.mkdir(parents=True, exist_ok=True)
        write_lattice_file(surface, project_path / "lattice_input.dat")
        write_mechanism_file(mechanisms, project_path / "mechanism_input.dat")
        write_energetics_file(records, project_path / "energetics_input.dat")
        write_species_file(records, project_path / "species_input.dat")
        write_mapping(mappings, project_path / "mapping.json")
    except (OSError, TypeError, ValueError) as exc:
        raise ZacrosGenerationError(
            f"Unable to write Zacros adapter project: {project_path}"
        ) from exc

    report: dict[str, object] = {
        "dataset": str(dataset_file),
        "validation_report": str(validation_file),
        "surface_config": str(surface_file),
        "output_path": str(project_path),
        "total_reactions": len(dataset.records),
        "generated": len(records),
        "failed": len(errors),
        "warnings": len(warnings),
        "errors": errors,
        "warning_reactions": warnings,
    }
    try:
        _write_generation_report(report, project_path / "generation_report.json")
    except OSError as exc:
        raise ZacrosGenerationError(
            f"Unable to write generation report: {project_path}"
        ) from exc

    LOGGER.info("Generated Zacros adapter project: %s", report)
    return report
