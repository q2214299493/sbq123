from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from modules.structure_purpose_manager import (
    PURPOSE_CONFIRMATION_PROMPT,
    StructurePurpose,
    StructurePurposeContext,
    StructurePurposeManager,
    resolve_structure_purpose,
)
from modules.ts_endpoint_database import (
    TSEndpointDatabase,
)
from modules.ts_endpoint_generator import (
    EndpointCandidate,
    TSEndpointGenerationRequest,
    TSEndpointGenerator,
)
from modules.ts_endpoint_validator import (
    MULTI_EVENT_REACTION,
    BondChange,
    EndpointValidationRequest,
    EndpointValidationStatus,
    TSEndpointValidator,
)
from scripts.neb_agent.utils_structure import Poscar, write_poscar


class ExistingStableAdsorptionSelector:
    def __init__(self) -> None:
        self.calls = 0

    def select_stable_structure(
        self, request: list[dict[str, object]]
    ) -> dict[str, object]:
        self.calls += 1
        return min(request, key=lambda candidate: float(candidate["energy_eV"]))


class ExistingLegacyWorkflow:
    def __init__(self) -> None:
        self.calls = 0

    def select_structure(self, request: object) -> object:
        self.calls += 1
        return request


def structure(
    c_x: float,
    o_x: float,
    *,
    fe: tuple[float, float, float] = (0.0, 0.0, 0.0),
    c_yz: tuple[float, float] = (0.2, 0.2),
    o_yz: tuple[float, float] = (0.2, 0.2),
) -> Poscar:
    return Poscar(
        comment="Fe CO purpose test",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C", "O"],
        counts=[1, 1, 1],
        frac=np.array(
            [
                fe,
                [c_x, *c_yz],
                [o_x, *o_yz],
            ]
        ),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )


def endpoint_database(tmp_path: Path) -> TSEndpointDatabase:
    database = tmp_path / "registry.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', '8');

            CREATE TABLE ts_endpoint_records (
                endpoint_record_id TEXT PRIMARY KEY,
                reaction_id TEXT NOT NULL,
                endpoint_role TEXT NOT NULL,
                structure_hash TEXT NOT NULL,
                endpoint_version TEXT NOT NULL,
                source_calculation_id TEXT,
                stable_structure_file_id TEXT,
                ts_structure_file_id TEXT,
                endpoint_structure_path TEXT,
                is_same_as_stable INTEGER NOT NULL,
                validation_status TEXT NOT NULL,
                validation_json TEXT NOT NULL,
                threshold_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (
                    reaction_id,
                    endpoint_role,
                    structure_hash,
                    endpoint_version
                )
            );
            """
        )
    return TSEndpointDatabase(database)


def manager(
    tmp_path: Path,
    selector: ExistingStableAdsorptionSelector,
    legacy: ExistingLegacyWorkflow | None = None,
) -> StructurePurposeManager:
    return StructurePurposeManager(
        stable_adsorption_selector=selector,
        ts_endpoint_generator=TSEndpointGenerator(),
        ts_endpoint_database=endpoint_database(tmp_path),
        legacy_workflow=legacy,
    )


def dissociation_request(
    initial: Path,
    *,
    stable_structure_path: Path | None = None,
) -> TSEndpointGenerationRequest:
    return TSEndpointGenerationRequest(
        reaction_id="fe110_co_dissociation",
        surface="Fe(110)",
        reaction_type="CO_dissociation",
        reactant_id="co_top",
        initial_structure=initial,
        reactive_atoms=(1, 2),
        adsorbate_atoms=(1, 2),
        surface_atoms=(0,),
        bond_changes=(BondChange("break", (1, 2)),),
        atom_map=((0, 0), (1, 1), (2, 2)),
        stable_structure_path=stable_structure_path,
    )


def test_old_call_without_purpose_uses_legacy_workflow_unchanged(
    tmp_path: Path,
) -> None:
    selector = ExistingStableAdsorptionSelector()
    legacy = ExistingLegacyWorkflow()
    request = {"old": "request"}

    result = manager(tmp_path, selector, legacy).select_structure(
        legacy_request=request
    )

    assert result.workflow_status == "LEGACY_UNCHANGED"
    assert result.structure is request
    assert legacy.calls == 1
    assert selector.calls == 0


def test_co_adsorption_delegates_to_existing_stable_minimum_selector(
    tmp_path: Path,
) -> None:
    selector = ExistingStableAdsorptionSelector()
    candidates = [
        {"structure_id": "co_bridge", "energy_eV": -1.1},
        {"structure_id": "co_top", "energy_eV": -1.8},
    ]

    result = manager(tmp_path, selector).select_structure(
        StructurePurpose.ADSORPTION_STABLE,
        adsorption_request=candidates,
    )

    assert selector.calls == 1
    assert result.structure["structure_id"] == "co_top"
    assert result.ts_endpoint is None
    assert result.database_record_id is None


def test_co_dissociation_selects_continuous_endpoint_not_global_minimum(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    nearby = tmp_path / "FS_near.POSCAR"
    global_minimum = tmp_path / "FS_global.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(nearby, structure(0.22, 0.41))
    write_poscar(global_minimum, structure(0.45, 0.77))
    selector = ExistingStableAdsorptionSelector()
    purpose_manager = manager(tmp_path, selector)

    result = purpose_manager.select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=dissociation_request(initial),
        endpoint_candidates=(
            EndpointCandidate(
                endpoint_id="co_dissociation_near",
                product_id="c_near_o_near",
                structure_path=nearby,
                site="C_near+O_near",
                energy_eV=-1.0,
            ),
            EndpointCandidate(
                endpoint_id="co_dissociation_global",
                product_id="c_long_bridge_o_hollow",
                structure_path=global_minimum,
                site="C_long_bridge+O_hollow",
                energy_eV=-2.0,
                is_global_minimum=True,
                local_stability_validated=True,
                path_connectivity_validated=True,
            ),
        ),
    )

    assert selector.calls == 0
    assert result.structure.endpoint_id == "co_dissociation_near"
    assert result.ts_endpoint is not None
    assert result.ts_endpoint.validation.status is EndpointValidationStatus.VALID
    stored = purpose_manager.ts_endpoint_database.get("co_dissociation_near")
    assert stored["reaction_id"] == "fe110_co_dissociation"
    assert stored["endpoint_structure_path"] == str(nearby.resolve())


def test_path_compatible_global_minimum_can_be_the_ts_endpoint(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    stable = tmp_path / "FS_stable.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(stable, structure(0.22, 0.41))
    purpose_manager = manager(tmp_path, ExistingStableAdsorptionSelector())

    result = purpose_manager.select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=dissociation_request(initial, stable_structure_path=stable),
        endpoint_candidates=(
            EndpointCandidate(
                endpoint_id="co_dissociation_stable_compatible",
                product_id="c_o_stable",
                structure_path=stable,
                site="compatible_stable_site",
                energy_eV=-2.0,
                is_global_minimum=True,
                local_stability_validated=True,
                path_connectivity_validated=True,
            ),
        ),
    )

    assert result.structure.is_global_minimum is True
    stored = purpose_manager.ts_endpoint_database.get(
        "co_dissociation_stable_compatible"
    )
    assert stored["is_same_as_stable"] is True
    assert stored["endpoint_structure_path"] is None
    assert stored["validation"]["stable_product_reuse"] == {
        "eligibility_reasons": [],
        "is_global_minimum": True,
        "local_stability_validated": True,
        "path_connectivity_validated": True,
        "reuse_eligible": True,
    }


def test_unvalidated_global_minimum_is_not_reused_as_ts_endpoint(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    nearby = tmp_path / "FS_near.POSCAR"
    global_minimum = tmp_path / "FS_global.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(nearby, structure(0.22, 0.41))
    write_poscar(global_minimum, structure(0.23, 0.42))

    result = manager(
        tmp_path,
        ExistingStableAdsorptionSelector(),
    ).select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=dissociation_request(initial),
        endpoint_candidates=(
            EndpointCandidate(
                endpoint_id="co_dissociation_near_validated",
                product_id="c_near_o_near",
                structure_path=nearby,
                site="C_near+O_near",
                energy_eV=-1.0,
            ),
            EndpointCandidate(
                endpoint_id="co_dissociation_global_unvalidated",
                product_id="c_o_global",
                structure_path=global_minimum,
                site="C_global+O_global",
                energy_eV=-2.0,
                is_global_minimum=True,
            ),
        ),
    )

    assert result.structure.endpoint_id == "co_dissociation_near_validated"
    global_assessment = next(
        assessment
        for assessment in result.ts_endpoint.assessments
        if assessment.candidate.is_global_minimum
    )
    assert global_assessment.reuse_eligible is False
    assert global_assessment.eligibility_reasons == (
        "GLOBAL_MINIMUM_LOCAL_STABILITY_NOT_VALIDATED",
        "GLOBAL_MINIMUM_PATH_CONNECTIVITY_NOT_VALIDATED",
    )


def test_global_minimum_with_extra_reaction_event_is_not_reused(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    nearby = tmp_path / "FS_near.POSCAR"
    global_minimum = tmp_path / "FS_global.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(nearby, structure(0.22, 0.41))
    write_poscar(global_minimum, structure(0.23, 0.42))

    result = manager(
        tmp_path,
        ExistingStableAdsorptionSelector(),
    ).select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=dissociation_request(initial),
        endpoint_candidates=(
            EndpointCandidate(
                endpoint_id="co_dissociation_near_no_extra_event",
                product_id="c_near_o_near",
                structure_path=nearby,
                site="C_near+O_near",
                energy_eV=-1.0,
            ),
            EndpointCandidate(
                endpoint_id="co_dissociation_global_extra_event",
                product_id="c_o_global",
                structure_path=global_minimum,
                site="C_global+O_global",
                energy_eV=-2.0,
                is_global_minimum=True,
                local_stability_validated=True,
                path_connectivity_validated=True,
                metadata={"observed_site_changes": ("o:bridge->remote_hollow",)},
            ),
        ),
    )

    assert result.structure.endpoint_id == "co_dissociation_near_no_extra_event"
    global_assessment = next(
        assessment
        for assessment in result.ts_endpoint.assessments
        if assessment.candidate.is_global_minimum
    )
    assert global_assessment.reuse_eligible is False
    assert global_assessment.eligibility_reasons == (
        "GLOBAL_MINIMUM_HAS_EXTRA_OR_INCORRECT_REACTION_EVENT",
    )


def test_large_adsorbate_migration_is_flagged_as_multi_event(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(endpoint, structure(0.32, 0.50))

    result = TSEndpointValidator().validate(
        EndpointValidationRequest(
            initial_structure=initial,
            endpoint_structure=endpoint,
            reactive_atoms=(1, 2),
            adsorbate_atoms=(1, 2),
            surface_atoms=(0,),
            bond_changes=(BondChange("break", (1, 2)),),
        )
    )

    assert result.status is EndpointValidationStatus.REVIEW_REQUIRED
    assert result.adsorbate_com_displacement_A > 1.5
    assert result.migration_flag == MULTI_EVENT_REACTION
    assert MULTI_EVENT_REACTION in result.warnings


def test_single_displacement_threshold_cannot_reject_endpoint(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(endpoint, structure(0.05, 0.55))

    result = TSEndpointValidator().validate(
        EndpointValidationRequest(
            initial_structure=initial,
            endpoint_structure=endpoint,
            reactive_atoms=(2,),
            adsorbate_atoms=(1, 2),
            surface_atoms=(0,),
            bond_changes=(BondChange("break", (1, 2)),),
        )
    )

    assert result.max_reactive_displacement_A > 2.0
    assert result.status is EndpointValidationStatus.VALID_WITH_WARNING
    assert "REACTIVE_ATOM_DISPLACEMENT_WARNING" in result.warnings


def test_validator_reports_complete_and_unexpected_bond_changes(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(
        endpoint,
        structure(
            0.30,
            0.10,
            c_yz=(0.2, 0.2),
            o_yz=(0.0, 0.0),
        ),
    )

    result = TSEndpointValidator().validate(
        EndpointValidationRequest(
            initial_structure=initial,
            endpoint_structure=endpoint,
            reactive_atoms=(1, 2),
            adsorbate_atoms=(1, 2),
            surface_atoms=(0,),
            bond_changes=(BondChange("break", (1, 2)),),
        )
    )

    assert BondChange("break", (1, 2)) in result.observed_bond_changes
    assert BondChange("form", (0, 2)) in result.unexpected_bond_changes
    assert result.status is EndpointValidationStatus.REVIEW_REQUIRED
    assert result.periodic_mapping_method == "fractional_minimum_image_displacement"


def test_verified_site_coordination_is_not_unexpected_and_migration_warning_remains(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(
        endpoint,
        structure(
            0.30,
            0.10,
            c_yz=(0.2, 0.2),
            o_yz=(0.0, 0.0),
        ),
    )

    result = TSEndpointValidator().validate(
        EndpointValidationRequest(
            initial_structure=initial,
            endpoint_structure=endpoint,
            reactive_atoms=(1, 2),
            adsorbate_atoms=(1, 2),
            surface_atoms=(0,),
            bond_changes=(BondChange("break", (1, 2)),),
            expected_site_changes=("o:molecular->top",),
            observed_site_changes=("o:molecular->top",),
        )
    )

    coordination_change = BondChange("form", (0, 2))
    assert coordination_change in result.observed_bond_changes
    assert coordination_change in result.site_coordination_bond_changes
    assert coordination_change not in result.unexpected_bond_changes
    assert "UNEXPECTED_BOND_CHANGE" not in result.warnings
    assert result.migration_flag == MULTI_EVENT_REACTION
    assert MULTI_EVENT_REACTION in result.warnings
    assert result.status is EndpointValidationStatus.REVIEW_REQUIRED


def test_interactive_confirmation_is_requested_once_then_continues_same_task(
    tmp_path: Path,
) -> None:
    selector = ExistingStableAdsorptionSelector()
    purpose_manager = manager(tmp_path, selector)
    candidates = [{"structure_id": "co_top", "energy_eV": -1.8}]
    context = StructurePurposeContext(
        task_id="task-1",
        is_new_structure_task=True,
        interactive=True,
    )

    first = purpose_manager.select_structure(
        context=context,
        adsorption_request=candidates,
    )
    second = purpose_manager.select_structure(
        context=StructurePurposeContext(
            task_id="task-1",
            is_new_structure_task=True,
            interactive=True,
            confirmation_requested=True,
        ),
        adsorption_request=candidates,
    )
    confirmed = purpose_manager.select_structure(
        context=StructurePurposeContext(
            purpose=StructurePurpose.ADSORPTION_STABLE,
            task_id="task-1",
            is_new_structure_task=True,
            interactive=True,
            confirmation_requested=True,
        ),
        adsorption_request=candidates,
    )

    assert first.workflow_status == "AWAITING_PURPOSE_CONFIRMATION"
    assert first.confirmation_prompt == PURPOSE_CONFIRMATION_PROMPT
    assert second.workflow_status == "AWAITING_PURPOSE_CONFIRMATION"
    assert second.confirmation_prompt is None
    assert confirmed.structure["structure_id"] == "co_top"
    assert selector.calls == 1


def test_noninteractive_missing_purpose_waits_without_blocking_legacy_operations(
    tmp_path: Path,
) -> None:
    selector = ExistingStableAdsorptionSelector()
    legacy = ExistingLegacyWorkflow()
    purpose_manager = manager(tmp_path, selector, legacy)

    waiting = purpose_manager.select_structure(
        context=StructurePurposeContext(
            task_id="new-one",
            is_new_structure_task=True,
            interactive=False,
        )
    )
    batch = purpose_manager.select_structure(
        context=StructurePurposeContext(
            task_id="batch-one",
            is_new_structure_task=True,
            batch=True,
        ),
        legacy_request="batch-preserved",
    )
    legacy_results = [
        purpose_manager.select_structure(
            context=StructurePurposeContext(
                task_id=f"{operation}-one",
                is_new_structure_task=True,
                operation=operation,
            ),
            legacy_request=f"{operation}-preserved",
        )
        for operation in (
            "submitted",
            "resume",
            "restart",
            "parse",
            "import",
            "historical_audit",
            "singlepoint",
        )
    ]

    assert waiting.workflow_status == "AWAITING_PURPOSE_CONFIRMATION"
    assert waiting.confirmation_prompt is None
    assert batch.structure == "batch-preserved"
    assert [result.structure for result in legacy_results] == [
        "submitted-preserved",
        "resume-preserved",
        "restart-preserved",
        "parse-preserved",
        "import-preserved",
        "historical_audit-preserved",
        "singlepoint-preserved",
    ]
    assert legacy.calls == 8
    assert purpose_manager.ts_endpoint_database.find_by_reaction(
        "fe110_co_dissociation"
    ) == []


def test_confirmed_child_task_inherits_parent_purpose() -> None:
    resolution = resolve_structure_purpose(
        StructurePurposeContext(
            parent_purpose=StructurePurpose.TS_ENDPOINT,
            task_id="child-task",
            is_new_structure_task=True,
        )
    )

    assert resolution.purpose is StructurePurpose.TS_ENDPOINT
    assert resolution.workflow_status == "PURPOSE_RESOLVED"


def test_feature_switch_disabled_restores_legacy_routing(
    tmp_path: Path,
) -> None:
    config = tmp_path / "purpose.yaml"
    config.write_text("schema_version: 1\nenabled: false\n", encoding="utf-8")
    resolution = resolve_structure_purpose(
        StructurePurposeContext(
            purpose=StructurePurpose.TS_ENDPOINT,
            is_new_structure_task=True,
        ),
        config_path=config,
    )

    assert resolution.use_legacy_workflow is True
    assert resolution.workflow_status == "LEGACY_UNCHANGED"


def test_ts_endpoint_save_is_idempotent_and_does_not_copy_poscar(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, structure(0.20, 0.32))
    write_poscar(endpoint, structure(0.22, 0.41))
    purpose_manager = manager(tmp_path, ExistingStableAdsorptionSelector())
    candidate = EndpointCandidate(
        endpoint_id="co_dissociation_idempotent",
        product_id="c_o_near",
        structure_path=endpoint,
        site="near",
    )

    first = purpose_manager.select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=dissociation_request(initial),
        endpoint_candidates=(candidate,),
    )
    second = purpose_manager.select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=dissociation_request(initial),
        endpoint_candidates=(candidate,),
    )

    assert first.database_record_id == second.database_record_id
    assert len(
        purpose_manager.ts_endpoint_database.find_by_reaction(
            "fe110_co_dissociation"
        )
    ) == 1
    assert list(tmp_path.rglob("FS.POSCAR")) == [endpoint]


def test_endpoint_database_does_not_implicitly_execute_blocked_migration(
    tmp_path: Path,
) -> None:
    database = tmp_path / "registry.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', '8');
            """
        )

    endpoint_store = TSEndpointDatabase(database)
    with pytest.raises(ValueError, match="TS endpoint table is missing"):
        endpoint_store.find_by_reaction("fe110_co_dissociation")

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ts_endpoint_records'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key='ts_endpoint_schema_version'"
        ).fetchone() is None
