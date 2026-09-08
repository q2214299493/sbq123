from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ase.data import atomic_numbers, covalent_radii

from .evidence import (
    EndpointGeometryEvidence,
    collect_endpoint_geometry_evidence,
    load_endpoint_structures,
)
from scripts.adsmind_lite.adsmind_common import load_yaml
from scripts.neb_agent.utils_structure import compatible


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "structure_purpose_routing.yaml"
MULTI_EVENT_REACTION = "MULTI_EVENT_REACTION"
REQUIRED_THRESHOLD_KEYS = {
    "reactive_atom_displacement_warning_A",
    "non_reactive_adsorbate_displacement_warning_A",
    "adsorbate_com_displacement_warning_A",
    "surface_atom_displacement_warning_A",
    "covalent_radius_scale",
    "minimum_bond_distance_A",
    "collision_radius_scale",
    "absolute_minimum_distance_A",
    "desorption_height_change_warning_A",
}


class EndpointValidationStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNING = "VALID_WITH_WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class EndpointThresholdPolicy:
    version: str
    reactive_atom_displacement_warning_A: float
    non_reactive_adsorbate_displacement_warning_A: float
    adsorbate_com_displacement_warning_A: float
    surface_atom_displacement_warning_A: float
    covalent_radius_scale: float
    minimum_bond_distance_A: float
    collision_radius_scale: float
    absolute_minimum_distance_A: float
    desorption_height_change_warning_A: float
    applied_overrides: tuple[str, ...] = ()


def load_endpoint_threshold_policy(
    config_path: Path = DEFAULT_CONFIG,
    *,
    surface: str | None = None,
    reaction_type: str | None = None,
    template_id: str | None = None,
) -> EndpointThresholdPolicy:
    config = load_yaml(config_path)
    endpoint = config.get("endpoint_validation")
    if not isinstance(endpoint, dict):
        raise ValueError("structure-purpose config is missing endpoint_validation")
    defaults = endpoint.get("defaults")
    if not isinstance(defaults, dict) or set(defaults) != REQUIRED_THRESHOLD_KEYS:
        raise ValueError("endpoint validation defaults do not match the required threshold keys")
    values = dict(defaults)
    applied: list[str] = []
    overrides = endpoint.get("overrides", {})
    for group, key in (
        ("surfaces", surface),
        ("reaction_types", reaction_type),
        ("templates", template_id),
    ):
        group_values = overrides.get(group, {}) if isinstance(overrides, dict) else {}
        selected = group_values.get(key) if isinstance(group_values, dict) and key else None
        if selected is None:
            continue
        if not isinstance(selected, dict) or not set(selected) <= REQUIRED_THRESHOLD_KEYS:
            raise ValueError(f"invalid endpoint threshold override: {group}.{key}")
        values.update(selected)
        applied.append(f"{group}:{key}")
    numeric = {key: float(value) for key, value in values.items()}
    if any(value <= 0 for value in numeric.values()):
        raise ValueError("endpoint validation thresholds must be positive")
    version = str(endpoint.get("threshold_version", "")).strip()
    if not version:
        raise ValueError("endpoint validation threshold_version is required")
    return EndpointThresholdPolicy(
        version=version,
        applied_overrides=tuple(applied),
        **numeric,
    )


@dataclass(frozen=True, order=True)
class BondChange:
    kind: str
    atoms: tuple[int, int]

    def __post_init__(self) -> None:
        if self.kind not in {"break", "form"}:
            raise ValueError("bond change kind must be 'break' or 'form'")
        if len(self.atoms) != 2 or self.atoms[0] == self.atoms[1]:
            raise ValueError("bond change requires two distinct atom indices")
        object.__setattr__(self, "atoms", tuple(sorted(self.atoms)))

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "atoms": list(self.atoms)}


@dataclass(frozen=True)
class EndpointValidationRequest:
    initial_structure: Path
    endpoint_structure: Path
    reactive_atoms: tuple[int, ...]
    adsorbate_atoms: tuple[int, ...]
    bond_changes: tuple[BondChange, ...]
    surface_atoms: tuple[int, ...] = ()
    expected_site_changes: tuple[str, ...] = ()
    observed_site_changes: tuple[str, ...] = ()
    atom_map: tuple[tuple[int, int], ...] = ()
    surface: str | None = None
    reaction_type: str | None = None
    template_id: str | None = None


@dataclass(frozen=True)
class EndpointValidationResult:
    status: EndpointValidationStatus
    threshold_version: str
    applied_threshold_overrides: tuple[str, ...]
    atom_mapping_method: str
    periodic_mapping_method: str
    expected_bond_changes: tuple[BondChange, ...]
    observed_bond_changes: tuple[BondChange, ...]
    site_coordination_bond_changes: tuple[BondChange, ...]
    unexpected_bond_changes: tuple[BondChange, ...]
    missing_expected_bond_changes: tuple[BondChange, ...]
    expected_site_changes: tuple[str, ...]
    observed_site_changes: tuple[str, ...]
    unexpected_site_changes: tuple[str, ...]
    atomic_displacement_A: dict[int, float]
    reactive_displacement_A: dict[int, float]
    adsorbate_com_displacement_A: float
    max_reactive_displacement_A: float
    max_non_reactive_adsorbate_displacement_A: float
    max_surface_displacement_A: float
    migration_flag: str | None
    validation_score: float
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


class TSEndpointValidator:
    """Validate endpoint chemistry and path locality without relaxing structures."""

    def __init__(self, config_path: Path = DEFAULT_CONFIG) -> None:
        self.config_path = config_path

    def validate(self, request: EndpointValidationRequest) -> EndpointValidationResult:
        policy = load_endpoint_threshold_policy(
            self.config_path,
            surface=request.surface,
            reaction_type=request.reaction_type,
            template_id=request.template_id,
        )
        structures = load_endpoint_structures(
            request.initial_structure,
            request.endpoint_structure,
        )
        initial = structures.initial
        endpoint = structures.endpoint
        errors, atom_mapping_method = self._preflight_errors(
            request,
            initial,
            endpoint,
        )
        warnings: list[str] = []
        if errors:
            return self._result(
                policy=policy,
                status=EndpointValidationStatus.REJECTED,
                atom_mapping_method=atom_mapping_method,
                expected=tuple(sorted(set(request.bond_changes))),
                observed=(),
                site_coordination=(),
                unexpected=(),
                missing=tuple(sorted(set(request.bond_changes))),
                request=request,
                displacements={},
                reactive_displacements={},
                adsorbate_com=0.0,
                max_reactive=0.0,
                max_non_reactive_adsorbate=0.0,
                max_surface=0.0,
                migration_flag=None,
                errors=errors,
                warnings=warnings,
            )

        evidence = collect_endpoint_geometry_evidence(
            structures,
            initial_path=request.initial_structure,
            endpoint_path=request.endpoint_structure,
            adsorbate_atoms=request.adsorbate_atoms,
            surface_atoms=request.surface_atoms,
            covalent_radius_scale=policy.covalent_radius_scale,
            minimum_bond_distance_A=policy.minimum_bond_distance_A,
        )
        if self._has_unphysical_contact(evidence, endpoint.labels, policy):
            errors.append("UNPHYSICAL_ATOM_CONTACT")
        displacements = evidence.atomic_displacement_A
        reactive_displacements = {
            index: displacements[index] for index in request.reactive_atoms
        }
        max_reactive = max(reactive_displacements.values(), default=0.0)
        if max_reactive > policy.reactive_atom_displacement_warning_A:
            warnings.append("REACTIVE_ATOM_DISPLACEMENT_WARNING")

        non_reactive_adsorbate = [
            displacements[index]
            for index in request.adsorbate_atoms
            if index not in request.reactive_atoms
        ]
        max_non_reactive_adsorbate = max(non_reactive_adsorbate, default=0.0)
        if max_non_reactive_adsorbate > policy.non_reactive_adsorbate_displacement_warning_A:
            warnings.append("NON_REACTIVE_ADSORBATE_DISPLACEMENT_WARNING")

        surface_atoms = request.surface_atoms or tuple(
            index for index in range(initial.atom_count) if index not in request.adsorbate_atoms
        )
        max_surface = max((displacements[index] for index in surface_atoms), default=0.0)
        if max_surface > policy.surface_atom_displacement_warning_A:
            warnings.append("SURFACE_ATOM_DISPLACEMENT_WARNING")

        adsorbate_com = evidence.adsorbate_com_displacement_A
        migration_flag = None
        if adsorbate_com > policy.adsorbate_com_displacement_warning_A:
            migration_flag = MULTI_EVENT_REACTION
            warnings.append(MULTI_EVENT_REACTION)
        if any(
            change > policy.desorption_height_change_warning_A
            for change in evidence.adsorbate_surface_height_change_A.values()
        ):
            warnings.append("ADSORBATE_DESORPTION_WARNING")

        expected = tuple(sorted(set(request.bond_changes)))
        observed = self._observed_bond_changes(request, evidence)
        expected_set = set(expected)
        observed_set = set(observed)
        unexpected_candidates = observed_set - expected_set
        site_coordination = self._site_coordination_changes(
            request,
            initial.labels,
            unexpected_candidates,
        )
        unexpected = tuple(sorted(unexpected_candidates - set(site_coordination)))
        missing = tuple(sorted(expected_set - observed_set))
        if missing:
            errors.append("EXPECTED_BOND_CHANGE_MISSING")
        if unexpected:
            warnings.append("UNEXPECTED_BOND_CHANGE")

        expected_sites = set(request.expected_site_changes)
        observed_sites = set(request.observed_site_changes)
        if expected_sites and not observed_sites:
            warnings.append("SITE_CHANGE_EVIDENCE_MISSING")
        elif expected_sites - observed_sites:
            warnings.append("EXPECTED_SITE_CHANGE_MISSING")
        unexpected_sites = tuple(sorted(observed_sites - expected_sites))
        if unexpected_sites:
            warnings.append("UNEXPECTED_SITE_CHANGE")

        status = self._validation_status(
            errors,
            warnings,
            migration_flag=migration_flag,
            unexpected=unexpected,
        )
        return self._result(
            policy=policy,
            status=status,
            atom_mapping_method=atom_mapping_method,
            expected=expected,
            observed=observed,
            site_coordination=site_coordination,
            unexpected=unexpected,
            missing=missing,
            request=request,
            displacements=displacements,
            reactive_displacements=reactive_displacements,
            adsorbate_com=adsorbate_com,
            max_reactive=max_reactive,
            max_non_reactive_adsorbate=max_non_reactive_adsorbate,
            max_surface=max_surface,
            migration_flag=migration_flag,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _has_unphysical_contact(
        evidence: EndpointGeometryEvidence,
        labels: list[str],
        policy: EndpointThresholdPolicy,
    ) -> bool:
        for (left, right), distance in evidence.endpoint_pair_distances_A.items():
            left_number = atomic_numbers.get(labels[left])
            right_number = atomic_numbers.get(labels[right])
            if left_number is None or right_number is None:
                threshold = policy.absolute_minimum_distance_A
            else:
                threshold = min(
                    policy.absolute_minimum_distance_A,
                    policy.collision_radius_scale
                    * (covalent_radii[left_number] + covalent_radii[right_number]),
                )
            if distance < threshold:
                return True
        return False

    @staticmethod
    def _validation_status(
        errors: list[str],
        warnings: list[str],
        *,
        migration_flag: str | None,
        unexpected: tuple[BondChange, ...],
    ) -> EndpointValidationStatus:
        if errors:
            return EndpointValidationStatus.REJECTED
        review_reasons = {
            "ADSORBATE_DESORPTION_WARNING",
            "SITE_CHANGE_EVIDENCE_MISSING",
            "EXPECTED_SITE_CHANGE_MISSING",
            "UNEXPECTED_SITE_CHANGE",
        }
        if migration_flag or unexpected or review_reasons & set(warnings):
            return EndpointValidationStatus.REVIEW_REQUIRED
        if warnings:
            return EndpointValidationStatus.VALID_WITH_WARNING
        return EndpointValidationStatus.VALID

    @classmethod
    def _preflight_errors(
        cls,
        request: EndpointValidationRequest,
        initial: Any,
        endpoint: Any,
    ) -> tuple[list[str], str]:
        errors = [
            f"STRUCTURE_INCOMPATIBLE:{reason}"
            for reason in compatible(initial, endpoint)
        ]
        atom_mapping_method = cls._atom_mapping_method(
            request,
            initial.atom_count,
            errors,
        )
        all_indices = {
            *request.reactive_atoms,
            *request.adsorbate_atoms,
            *request.surface_atoms,
            *(index for change in request.bond_changes for index in change.atoms),
        }
        if not request.bond_changes and not request.expected_site_changes:
            errors.append("REACTION_CHANGE_REQUIRED")
        if any(index < 0 or index >= initial.atom_count for index in all_indices):
            errors.append("ATOM_INDEX_OUT_OF_RANGE")
        return errors, atom_mapping_method

    @staticmethod
    def _atom_mapping_method(
        request: EndpointValidationRequest,
        atom_count: int,
        errors: list[str],
    ) -> str:
        if not request.atom_map:
            return "preserved_atom_order"
        mapping = dict(request.atom_map)
        if len(mapping) != len(request.atom_map) or any(
            initial < 0 or final < 0 or initial >= atom_count or final >= atom_count
            for initial, final in request.atom_map
        ):
            errors.append("INVALID_ATOM_MAP")
        elif any(initial != final for initial, final in request.atom_map):
            errors.append("ATOM_MAP_NOT_PRESERVED")
        return "reaction_contract_atom_map"

    @staticmethod
    def _observed_bond_changes(
        request: EndpointValidationRequest,
        evidence: EndpointGeometryEvidence,
    ) -> tuple[BondChange, ...]:
        initial_edges = set(evidence.initial_connectivity_edges)
        endpoint_edges = set(evidence.endpoint_connectivity_edges)
        adsorbate = set(request.adsorbate_atoms)
        relevant_initial = {
            edge for edge in initial_edges if edge[0] in adsorbate or edge[1] in adsorbate
        }
        relevant_endpoint = {
            edge for edge in endpoint_edges if edge[0] in adsorbate or edge[1] in adsorbate
        }
        changes = [
            *(BondChange("break", edge) for edge in relevant_initial - relevant_endpoint),
            *(BondChange("form", edge) for edge in relevant_endpoint - relevant_initial),
        ]
        return tuple(sorted(changes))

    @staticmethod
    def _site_coordination_changes(
        request: EndpointValidationRequest,
        labels: list[str],
        candidates: set[BondChange],
    ) -> tuple[BondChange, ...]:
        expected_sites = set(request.expected_site_changes)
        observed_sites = set(request.observed_site_changes)
        if not expected_sites or expected_sites != observed_sites:
            return ()
        adsorbate = set(request.adsorbate_atoms)
        surface = set(request.surface_atoms) or (
            set(range(len(labels))) - adsorbate
        )
        explained: list[BondChange] = []
        for change in candidates:
            left, right = change.atoms
            if left in surface and right in adsorbate:
                surface_index = left
            elif right in surface and left in adsorbate:
                surface_index = right
            else:
                continue
            if labels[surface_index] == "Fe":
                explained.append(change)
        return tuple(sorted(explained))

    @staticmethod
    def _result(
        *,
        policy: EndpointThresholdPolicy,
        status: EndpointValidationStatus,
        atom_mapping_method: str,
        expected: tuple[BondChange, ...],
        observed: tuple[BondChange, ...],
        site_coordination: tuple[BondChange, ...],
        unexpected: tuple[BondChange, ...],
        missing: tuple[BondChange, ...],
        request: EndpointValidationRequest,
        displacements: dict[int, float],
        reactive_displacements: dict[int, float],
        adsorbate_com: float,
        max_reactive: float,
        max_non_reactive_adsorbate: float,
        max_surface: float,
        migration_flag: str | None,
        errors: list[str],
        warnings: list[str],
    ) -> EndpointValidationResult:
        unique_errors = tuple(sorted(set(errors)))
        unique_warnings = tuple(sorted(set(warnings)))
        score = {
            EndpointValidationStatus.VALID: 1.0,
            EndpointValidationStatus.VALID_WITH_WARNING: 0.75,
            EndpointValidationStatus.REVIEW_REQUIRED: 0.5,
            EndpointValidationStatus.REJECTED: 0.0,
        }[status]
        return EndpointValidationResult(
            status=status,
            threshold_version=policy.version,
            applied_threshold_overrides=policy.applied_overrides,
            atom_mapping_method=atom_mapping_method,
            periodic_mapping_method="fractional_minimum_image_displacement",
            expected_bond_changes=expected,
            observed_bond_changes=observed,
            site_coordination_bond_changes=site_coordination,
            unexpected_bond_changes=unexpected,
            missing_expected_bond_changes=missing,
            expected_site_changes=tuple(sorted(set(request.expected_site_changes))),
            observed_site_changes=tuple(sorted(set(request.observed_site_changes))),
            unexpected_site_changes=tuple(
                sorted(set(request.observed_site_changes) - set(request.expected_site_changes))
            ),
            atomic_displacement_A=displacements,
            reactive_displacement_A=reactive_displacements,
            adsorbate_com_displacement_A=adsorbate_com,
            max_reactive_displacement_A=max_reactive,
            max_non_reactive_adsorbate_displacement_A=max_non_reactive_adsorbate,
            max_surface_displacement_A=max_surface,
            migration_flag=migration_flag,
            validation_score=score,
            errors=unique_errors,
            warnings=unique_warnings,
            reasons=unique_errors + unique_warnings,
        )
