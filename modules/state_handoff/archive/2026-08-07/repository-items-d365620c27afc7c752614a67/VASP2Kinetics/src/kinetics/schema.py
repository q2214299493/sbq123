"""Typed Phase 3 schema for kinetic reaction records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..exceptions import KineticDataError


class ReactionStatus(str, Enum):
    """Allowed lifecycle states for a reaction record."""

    RAW = "RAW"
    UNVERIFIED = "UNVERIFIED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SystemInfo:
    """Human-provided material and surface labels."""

    material: str
    surface: str
    facet: str


@dataclass(frozen=True)
class SpeciesInfo:
    """Human-provided reactant and product labels."""

    reactant: list[str]
    product: list[str]


@dataclass(frozen=True)
class Energetics:
    """Recorded energies without derived reaction or activation quantities."""

    E_initial: float | None
    E_final: float | None
    E_reaction: float | None
    Ea_forward: float | None
    Ea_reverse: float | None
    candidate_TS_energy: float | None


@dataclass(frozen=True)
class CalculationInfo:
    """Calculation method and provenance."""

    method: str
    functional: str
    source_path: str | None


@dataclass(frozen=True)
class QualityInfo:
    """Review flags that default to unverified states."""

    vasp_converged: bool
    ts_verified: bool
    scientific_review: bool


@dataclass(frozen=True)
class ReactionRecord:
    """A single typed Phase 3 reaction record."""

    reaction_id: str
    system: SystemInfo
    species: SpeciesInfo
    energetics: Energetics
    calculation: CalculationInfo
    quality: QualityInfo
    status: ReactionStatus

    def to_dict(self) -> dict[str, object]:
        """Serialize the record to its stable JSON-compatible representation."""

        return {
            "reaction_id": self.reaction_id,
            "system": {
                "material": self.system.material,
                "surface": self.system.surface,
                "facet": self.system.facet,
            },
            "species": {
                "reactant": list(self.species.reactant),
                "product": list(self.species.product),
            },
            "energetics": {
                "E_initial": self.energetics.E_initial,
                "E_final": self.energetics.E_final,
                "E_reaction": self.energetics.E_reaction,
                "Ea_forward": self.energetics.Ea_forward,
                "Ea_reverse": self.energetics.Ea_reverse,
                "candidate_TS_energy": self.energetics.candidate_TS_energy,
            },
            "calculation": {
                "method": self.calculation.method,
                "functional": self.calculation.functional,
                "source_path": self.calculation.source_path,
            },
            "quality": {
                "vasp_converged": self.quality.vasp_converged,
                "ts_verified": self.quality.ts_verified,
                "scientific_review": self.quality.scientific_review,
            },
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReactionRecord:
        """Deserialize and structurally validate a stored reaction record."""

        system = _require_mapping(data, "system")
        species = _require_mapping(data, "species")
        energetics = _require_mapping(data, "energetics")
        calculation = _require_mapping(data, "calculation")
        quality = _require_mapping(data, "quality")

        try:
            status = ReactionStatus(_require_text(data, "status"))
        except ValueError as exc:
            raise KineticDataError("Reaction record contains an invalid status.") from exc

        return cls(
            reaction_id=_require_text(data, "reaction_id"),
            system=SystemInfo(
                material=_require_text(system, "material"),
                surface=_require_text(system, "surface"),
                facet=_require_text(system, "facet"),
            ),
            species=SpeciesInfo(
                reactant=_require_text_list(species, "reactant"),
                product=_require_text_list(species, "product"),
            ),
            energetics=Energetics(
                E_initial=_optional_float(energetics, "E_initial"),
                E_final=_optional_float(energetics, "E_final"),
                E_reaction=_optional_float(energetics, "E_reaction"),
                Ea_forward=_optional_float(energetics, "Ea_forward"),
                Ea_reverse=_optional_float(energetics, "Ea_reverse"),
                candidate_TS_energy=_optional_float(
                    energetics,
                    "candidate_TS_energy",
                ),
            ),
            calculation=CalculationInfo(
                method=_require_text(calculation, "method"),
                functional=_require_text(calculation, "functional"),
                source_path=_optional_text(calculation, "source_path"),
            ),
            quality=QualityInfo(
                vasp_converged=_require_bool(quality, "vasp_converged"),
                ts_verified=_require_bool(quality, "ts_verified"),
                scientific_review=_require_bool(quality, "scientific_review"),
            ),
            status=status,
        )


@dataclass(frozen=True)
class KineticDataset:
    """Collection stored in `kinetic_dataset.json`."""

    records: list[ReactionRecord] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, object]:
        """Serialize the complete dataset."""

        return {
            "schema_version": self.schema_version,
            "records": [record.to_dict() for record in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KineticDataset:
        """Deserialize a stored dataset into typed records."""

        schema_version = _require_text(data, "schema_version")
        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            raise KineticDataError("Dataset field 'records' must be a list.")
        records: list[ReactionRecord] = []
        for index, raw_record in enumerate(raw_records):
            if not isinstance(raw_record, dict):
                raise KineticDataError(
                    f"Dataset record at index {index} must be a mapping."
                )
            records.append(ReactionRecord.from_dict(raw_record))
        return cls(records=records, schema_version=schema_version)


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return one required reaction-record mapping."""

    value = data.get(key)
    if not isinstance(value, dict):
        raise KineticDataError(f"Reaction record field '{key}' must be a mapping.")
    return value


def _require_text(data: dict[str, Any], key: str) -> str:
    """Return one required non-empty reaction-record string."""

    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KineticDataError(
            f"Reaction record field '{key}' must be a non-empty string."
        )
    return value.strip()


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    """Return one optional reaction-record string."""

    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KineticDataError(
            f"Reaction record field '{key}' must be null or a non-empty string."
        )
    return value.strip()


def _require_text_list(data: dict[str, Any], key: str) -> list[str]:
    """Return one required non-empty string list."""

    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise KineticDataError(
            f"Reaction record field '{key}' must be a non-empty list."
        )
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise KineticDataError(
            f"Reaction record field '{key}' must contain non-empty strings."
        )
    return [item.strip() for item in value]


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    """Return one optional finite numeric field."""

    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KineticDataError(
            f"Reaction record field '{key}' must be null or numeric."
        )
    return float(value)


def _require_bool(data: dict[str, Any], key: str) -> bool:
    """Return one required boolean field."""

    value = data.get(key)
    if not isinstance(value, bool):
        raise KineticDataError(f"Reaction record field '{key}' must be boolean.")
    return value
