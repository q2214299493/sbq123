from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .validator import (
    BondChange,
    EndpointValidationRequest,
    EndpointValidationResult,
    EndpointValidationStatus,
    TSEndpointValidator,
)


@dataclass(frozen=True)
class EndpointCandidate:
    endpoint_id: str
    product_id: str
    structure_path: Path
    site: str
    energy_eV: float | None = None
    is_global_minimum: bool = False
    local_stability_validated: bool = False
    path_connectivity_validated: bool = False
    structure_file_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TSEndpointGenerationRequest:
    reaction_id: str
    surface: str
    reaction_type: str
    reactant_id: str
    initial_structure: Path
    reactive_atoms: tuple[int, ...]
    adsorbate_atoms: tuple[int, ...]
    bond_changes: tuple[BondChange, ...]
    surface_atoms: tuple[int, ...] = ()
    expected_site_changes: tuple[str, ...] = ()
    atom_map: tuple[tuple[int, int], ...] = ()
    template_id: str | None = None
    endpoint_role: str = "final"
    endpoint_version: str = "1"
    source_calculation_id: str | None = None
    stable_structure_path: Path | None = None
    stable_structure_file_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reaction_id, str) or not self.reaction_id.strip():
            raise ValueError("reaction_id is required")


@dataclass(frozen=True)
class CandidateAssessment:
    candidate: EndpointCandidate
    validation: EndpointValidationResult
    reuse_eligible: bool
    eligibility_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedTSEndpoint:
    request: TSEndpointGenerationRequest
    candidate: EndpointCandidate
    validation: EndpointValidationResult
    assessments: tuple[CandidateAssessment, ...]


class TSEndpointGenerator:
    """Choose a path-compatible endpoint from candidates built by existing workflows."""

    def __init__(self, validator: TSEndpointValidator | None = None) -> None:
        self.validator = validator or TSEndpointValidator()

    def generate(
        self,
        request: TSEndpointGenerationRequest,
        candidates: Iterable[EndpointCandidate],
    ) -> GeneratedTSEndpoint:
        if request.endpoint_role not in {"initial", "final"}:
            raise ValueError("endpoint_role must be 'initial' or 'final'")
        assessments = tuple(
            self._assess_candidate(request, candidate)
            for candidate in candidates
        )
        eligible = [
            assessment
            for assessment in assessments
            if assessment.validation.status is not EndpointValidationStatus.REJECTED
            and assessment.reuse_eligible
        ]
        if not eligible:
            raise ValueError("no path-compatible TS endpoint candidate passed validation")
        selected = min(eligible, key=self._selection_key)
        return GeneratedTSEndpoint(
            request=request,
            candidate=selected.candidate,
            validation=selected.validation,
            assessments=assessments,
        )

    def _assess_candidate(
        self,
        request: TSEndpointGenerationRequest,
        candidate: EndpointCandidate,
    ) -> CandidateAssessment:
        validation = self.validator.validate(
            EndpointValidationRequest(
                initial_structure=request.initial_structure,
                endpoint_structure=candidate.structure_path,
                reactive_atoms=request.reactive_atoms,
                adsorbate_atoms=request.adsorbate_atoms,
                bond_changes=request.bond_changes,
                surface_atoms=request.surface_atoms,
                expected_site_changes=request.expected_site_changes,
                observed_site_changes=tuple(
                    str(value)
                    for value in candidate.metadata.get("observed_site_changes", ())
                ),
                atom_map=request.atom_map,
                surface=request.surface,
                reaction_type=request.reaction_type,
                template_id=request.template_id,
            )
        )
        reasons = self._reuse_ineligibility_reasons(candidate, validation)
        return CandidateAssessment(
            candidate=candidate,
            validation=validation,
            reuse_eligible=not reasons,
            eligibility_reasons=reasons,
        )

    @staticmethod
    def _reuse_ineligibility_reasons(
        candidate: EndpointCandidate,
        validation: EndpointValidationResult,
    ) -> tuple[str, ...]:
        if not candidate.is_global_minimum:
            return ()
        reasons: list[str] = []
        if not candidate.local_stability_validated:
            reasons.append("GLOBAL_MINIMUM_LOCAL_STABILITY_NOT_VALIDATED")
        if not candidate.path_connectivity_validated:
            reasons.append("GLOBAL_MINIMUM_PATH_CONNECTIVITY_NOT_VALIDATED")
        if (
            validation.missing_expected_bond_changes
            or validation.unexpected_bond_changes
            or validation.unexpected_site_changes
        ):
            reasons.append("GLOBAL_MINIMUM_HAS_EXTRA_OR_INCORRECT_REACTION_EVENT")
        return tuple(reasons)

    @staticmethod
    def _selection_key(assessment: CandidateAssessment) -> tuple[object, ...]:
        validation = assessment.validation
        candidate = assessment.candidate
        status_rank = {
            EndpointValidationStatus.VALID: 0,
            EndpointValidationStatus.VALID_WITH_WARNING: 1,
            EndpointValidationStatus.REVIEW_REQUIRED: 2,
            EndpointValidationStatus.REJECTED: 3,
        }
        return (
            status_rank[validation.status],
            0 if validation.migration_flag is None else 1,
            validation.max_reactive_displacement_A,
            validation.adsorbate_com_displacement_A,
            validation.max_surface_displacement_A,
            float("inf") if candidate.energy_eV is None else candidate.energy_eV,
            candidate.endpoint_id,
        )
