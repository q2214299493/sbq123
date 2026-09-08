from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Protocol

from .database import TSEndpointDatabase, TSEndpointRecord
from .generator import (
    EndpointCandidate,
    GeneratedTSEndpoint,
    TSEndpointGenerationRequest,
    TSEndpointGenerator,
)
from scripts.adsmind_lite.adsmind_common import load_yaml
from scripts.artifact_io import sha256_file


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "structure_purpose_routing.yaml"
PURPOSE_CONFIRMATION_PROMPT = (
    "Please confirm structure purpose: "
    "[1] stable adsorption structure; "
    "[2] TS reaction endpoint structure; "
    "[3] other."
)
_LEGACY_BYPASS_OPERATIONS = {
    "submitted",
    "resume",
    "restart",
    "parse",
    "import",
    "historical_audit",
    "singlepoint",
}


class StructurePurpose(str, Enum):
    ADSORPTION_STABLE = "ADSORPTION_STABLE"
    TS_ENDPOINT = "TS_ENDPOINT"
    UNRESOLVED = "UNRESOLVED"


_PURPOSE_ALIASES = {
    "ADSORPTION_STABLE": StructurePurpose.ADSORPTION_STABLE,
    "STABLE_ADSORPTION_STRUCTURE": StructurePurpose.ADSORPTION_STABLE,
    "ADSORPTION_DATABASE": StructurePurpose.ADSORPTION_STABLE,
    "TS_ENDPOINT": StructurePurpose.TS_ENDPOINT,
    "TS_REACTION_ENDPOINT_STRUCTURE": StructurePurpose.TS_ENDPOINT,
    "TS_CALCULATION": StructurePurpose.TS_ENDPOINT,
}


@dataclass(frozen=True)
class StructurePurposeContext:
    purpose: str | StructurePurpose | None = None
    parent_purpose: str | StructurePurpose | None = None
    task_id: str | None = None
    operation: str = "new_structure"
    is_new_structure_task: bool = False
    interactive: bool = False
    confirmation_requested: bool = False
    batch: bool = False


@dataclass(frozen=True)
class PurposeResolution:
    purpose: StructurePurpose | None
    workflow_status: str
    use_legacy_workflow: bool
    prompt: str | None = None


def _parse_explicit_purpose(value: str | StructurePurpose | None) -> StructurePurpose | None:
    if value is None:
        return None
    if isinstance(value, StructurePurpose):
        return value
    return _PURPOSE_ALIASES.get(str(value).strip().upper(), StructurePurpose.UNRESOLVED)


def resolve_structure_purpose(
    context: StructurePurposeContext,
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> PurposeResolution:
    """Single routing entry; callers must not infer purpose elsewhere."""

    config = load_yaml(config_path)
    if not isinstance(config.get("enabled"), bool):
        raise ValueError("structure_purpose_routing.enabled must be a boolean")
    if not config["enabled"]:
        return PurposeResolution(None, "LEGACY_UNCHANGED", True)

    explicit = _parse_explicit_purpose(context.purpose)
    if explicit is None:
        explicit = _parse_explicit_purpose(context.parent_purpose)
    if explicit in {StructurePurpose.ADSORPTION_STABLE, StructurePurpose.TS_ENDPOINT}:
        return PurposeResolution(explicit, "PURPOSE_RESOLVED", False)
    if explicit is StructurePurpose.UNRESOLVED:
        return PurposeResolution(
            StructurePurpose.UNRESOLVED,
            "AWAITING_PURPOSE_CONFIRMATION",
            False,
            PURPOSE_CONFIRMATION_PROMPT
            if context.interactive and not context.confirmation_requested
            else None,
        )

    operation = context.operation.strip().lower()
    if (
        not context.is_new_structure_task
        or operation in _LEGACY_BYPASS_OPERATIONS
        or context.batch
    ):
        return PurposeResolution(None, "LEGACY_UNCHANGED", True)
    return PurposeResolution(
        StructurePurpose.UNRESOLVED,
        "AWAITING_PURPOSE_CONFIRMATION",
        False,
        PURPOSE_CONFIRMATION_PROMPT
        if context.interactive and not context.confirmation_requested
        else None,
    )


class LegacyStructureWorkflow(Protocol):
    def select_structure(self, request: Any) -> Any:
        """Run the unchanged pre-purpose workflow."""


class StableAdsorptionSelector(Protocol):
    def select_stable_structure(self, request: Any) -> Any:
        """Run the existing stable-adsorption selection workflow."""


@dataclass(frozen=True)
class StructurePurposeResult:
    purpose: StructurePurpose | None
    workflow_status: str
    structure: Any = None
    ts_endpoint: GeneratedTSEndpoint | None = None
    database_record_id: str | None = None
    confirmation_prompt: str | None = None


class StructurePurposeManager:
    """Additive purpose-aware interface around unchanged legacy services."""

    def __init__(
        self,
        *,
        stable_adsorption_selector: StableAdsorptionSelector,
        ts_endpoint_generator: TSEndpointGenerator,
        ts_endpoint_database: TSEndpointDatabase,
        legacy_workflow: LegacyStructureWorkflow | None = None,
        config_path: Path = DEFAULT_CONFIG,
    ) -> None:
        self.stable_adsorption_selector = stable_adsorption_selector
        self.ts_endpoint_generator = ts_endpoint_generator
        self.ts_endpoint_database = ts_endpoint_database
        self.legacy_workflow = legacy_workflow
        self.config_path = config_path

    def select_structure(
        self,
        purpose: str | StructurePurpose | None = None,
        *,
        context: StructurePurposeContext | None = None,
        legacy_request: Any = None,
        adsorption_request: Any = None,
        ts_request: TSEndpointGenerationRequest | None = None,
        endpoint_candidates: Iterable[EndpointCandidate] = (),
    ) -> StructurePurposeResult:
        if context is None:
            context = StructurePurposeContext(
                purpose=purpose,
                is_new_structure_task=purpose is not None,
            )
        elif purpose is not None:
            context = replace(context, purpose=purpose)
        resolution = resolve_structure_purpose(context, config_path=self.config_path)
        if resolution.use_legacy_workflow:
            if self.legacy_workflow is None:
                raise ValueError("legacy_workflow is required for a legacy-routed call")
            return StructurePurposeResult(
                purpose=None,
                workflow_status=resolution.workflow_status,
                structure=self.legacy_workflow.select_structure(legacy_request),
            )
        if resolution.purpose is StructurePurpose.UNRESOLVED:
            return StructurePurposeResult(
                purpose=resolution.purpose,
                workflow_status=resolution.workflow_status,
                confirmation_prompt=resolution.prompt,
            )
        if resolution.purpose is StructurePurpose.ADSORPTION_STABLE:
            selected = self.stable_adsorption_selector.select_stable_structure(
                adsorption_request
            )
            return StructurePurposeResult(
                purpose=resolution.purpose,
                workflow_status=resolution.workflow_status,
                structure=selected,
            )
        if ts_request is None:
            raise ValueError("ts_request is required for TS_ENDPOINT")

        generated = self.ts_endpoint_generator.generate(ts_request, endpoint_candidates)
        record_id = self.ts_endpoint_database.save(self._record(generated))
        return StructurePurposeResult(
            purpose=resolution.purpose,
            workflow_status=resolution.workflow_status,
            structure=generated.candidate,
            ts_endpoint=generated,
            database_record_id=record_id,
        )

    @staticmethod
    def _record(generated: GeneratedTSEndpoint) -> TSEndpointRecord:
        request = generated.request
        candidate = generated.candidate
        selected_assessment = next(
            assessment
            for assessment in generated.assessments
            if assessment.candidate.endpoint_id == candidate.endpoint_id
        )
        candidate_hash = sha256_file(candidate.structure_path)
        stable_hash = (
            sha256_file(request.stable_structure_path)
            if request.stable_structure_path is not None
            else None
        )
        is_same_as_stable = stable_hash == candidate_hash if stable_hash else False
        validation = generated.validation.as_dict()
        validation["stable_product_reuse"] = {
            "is_global_minimum": candidate.is_global_minimum,
            "local_stability_validated": candidate.local_stability_validated,
            "path_connectivity_validated": candidate.path_connectivity_validated,
            "reuse_eligible": selected_assessment.reuse_eligible,
            "eligibility_reasons": list(selected_assessment.eligibility_reasons),
        }
        return TSEndpointRecord(
            endpoint_record_id=candidate.endpoint_id,
            reaction_id=request.reaction_id,
            endpoint_role=request.endpoint_role,
            structure_hash=candidate_hash,
            endpoint_version=request.endpoint_version,
            source_calculation_id=request.source_calculation_id,
            stable_structure_file_id=request.stable_structure_file_id,
            ts_structure_file_id=(
                None if is_same_as_stable else candidate.structure_file_id
            ),
            endpoint_structure_path=(
                None if is_same_as_stable else str(candidate.structure_path.resolve())
            ),
            is_same_as_stable=is_same_as_stable,
            validation_status=generated.validation.status.value,
            validation=validation,
            threshold_version=generated.validation.threshold_version,
        )
