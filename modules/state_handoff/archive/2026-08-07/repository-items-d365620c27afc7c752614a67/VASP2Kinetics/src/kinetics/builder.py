"""Build typed kinetic records from Phase 2 output and human reaction YAML."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import KineticDataError, ReactionDefinitionError
from .schema import (
    CalculationInfo,
    Energetics,
    QualityInfo,
    ReactionRecord,
    ReactionStatus,
    SpeciesInfo,
    SystemInfo,
)

LOGGER = logging.getLogger("vasp2kinetics.kinetics.builder")

_REACTION_KEYS = {
    "reaction_id",
    "reactant",
    "product",
    "material",
    "surface",
    "facet",
    "functional",
}


@dataclass(frozen=True)
class ReactionDefinition:
    """Human-provided reaction labels with no automatic mechanism inference."""

    reaction_id: str
    reactant: list[str]
    product: list[str]
    material: str = "unknown"
    surface: str = "unknown"
    facet: str = "unknown"
    functional: str = "unknown"


def load_vasp_result(path: str | Path) -> dict[str, Any]:
    """Load a Phase 2 `vasp_result.json` mapping."""

    input_path = Path(path).expanduser().resolve()
    if not input_path.is_file():
        raise KineticDataError(f"VASP result file does not exist: {input_path}")
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KineticDataError(f"Invalid JSON in VASP result: {input_path}") from exc
    except OSError as exc:
        raise KineticDataError(f"Unable to read VASP result: {input_path}") from exc
    if not isinstance(data, dict):
        raise KineticDataError("VASP result root must be a mapping.")
    return data


def load_reaction_definition(path: str | Path) -> ReactionDefinition:
    """Load and structurally validate a human-authored reaction YAML file."""

    reaction_path = Path(path).expanduser().resolve()
    if not reaction_path.is_file():
        raise ReactionDefinitionError(
            f"Reaction definition does not exist: {reaction_path}"
        )
    try:
        data = yaml.safe_load(reaction_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ReactionDefinitionError(
            f"Invalid YAML in reaction definition: {reaction_path}"
        ) from exc
    except OSError as exc:
        raise ReactionDefinitionError(
            f"Unable to read reaction definition: {reaction_path}"
        ) from exc
    if not isinstance(data, dict):
        raise ReactionDefinitionError("Reaction definition root must be a mapping.")

    unknown_keys = sorted(set(data) - _REACTION_KEYS)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ReactionDefinitionError(
            f"Reaction definition contains unsupported fields: {joined}."
        )

    return ReactionDefinition(
        reaction_id=_required_text(data, "reaction_id"),
        reactant=_required_species(data, "reactant"),
        product=_required_species(data, "product"),
        material=_optional_label(data, "material"),
        surface=_optional_label(data, "surface"),
        facet=_optional_label(data, "facet"),
        functional=_optional_label(data, "functional"),
    )


def build_kinetic_record(
    vasp_result: dict[str, Any],
    reaction: ReactionDefinition,
) -> ReactionRecord:
    """Map only explicitly available Phase 2 fields into a typed record."""

    final_energy = _nested_optional_number(vasp_result, "energy", "final")
    candidate_ts_energy = _nested_optional_number(
        vasp_result,
        "neb",
        "highest_energy",
    )
    source_path = _nested_optional_text(vasp_result, "source", "path")
    convergence_status = _nested_optional_text(
        vasp_result,
        "convergence",
        "status",
    )

    record = ReactionRecord(
        reaction_id=reaction.reaction_id,
        system=SystemInfo(
            material=reaction.material,
            surface=reaction.surface,
            facet=reaction.facet,
        ),
        species=SpeciesInfo(
            reactant=list(reaction.reactant),
            product=list(reaction.product),
        ),
        energetics=Energetics(
            E_initial=None,
            E_final=final_energy,
            E_reaction=None,
            Ea_forward=None,
            Ea_reverse=None,
            candidate_TS_energy=candidate_ts_energy,
        ),
        calculation=CalculationInfo(
            method="VASP",
            functional=reaction.functional,
            source_path=source_path,
        ),
        quality=QualityInfo(
            vasp_converged=convergence_status == "converged",
            ts_verified=False,
            scientific_review=False,
        ),
        status=ReactionStatus.UNVERIFIED,
    )
    LOGGER.info("Built UNVERIFIED kinetic record: reaction_id=%s", reaction.reaction_id)
    return record


def _required_text(data: dict[str, Any], key: str) -> str:
    """Return one required non-empty reaction-definition string."""

    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReactionDefinitionError(
            f"Reaction definition field '{key}' must be a non-empty string."
        )
    return value.strip()


def _required_species(data: dict[str, Any], key: str) -> list[str]:
    """Return one required non-empty species list."""

    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ReactionDefinitionError(
            f"Reaction definition field '{key}' must be a non-empty list."
        )
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReactionDefinitionError(
            f"Reaction definition field '{key}' must contain non-empty strings."
        )
    return [item.strip() for item in value]


def _optional_label(data: dict[str, Any], key: str) -> str:
    """Return one optional human label or the explicit unknown marker."""

    value = data.get(key, "unknown")
    if not isinstance(value, str) or not value.strip():
        raise ReactionDefinitionError(
            f"Reaction definition field '{key}' must be a non-empty string."
        )
    return value.strip()


def _nested_optional_number(
    data: dict[str, Any],
    section: str,
    key: str,
) -> float | None:
    """Read one optional nested numeric VASP result value."""

    section_data = data.get(section)
    if section_data is None:
        return None
    if not isinstance(section_data, dict):
        raise KineticDataError(f"VASP result section '{section}' must be a mapping.")
    value = section_data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KineticDataError(
            f"VASP result field '{section}.{key}' must be null or numeric."
        )
    return float(value)


def _nested_optional_text(
    data: dict[str, Any],
    section: str,
    key: str,
) -> str | None:
    """Read one optional nested text VASP result value."""

    section_data = data.get(section)
    if section_data is None:
        return None
    if not isinstance(section_data, dict):
        raise KineticDataError(f"VASP result section '{section}' must be a mapping.")
    value = section_data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KineticDataError(
            f"VASP result field '{section}.{key}' must be null or a string."
        )
    return value.strip()
