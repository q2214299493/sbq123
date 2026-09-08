from __future__ import annotations

import ast
import importlib
import inspect
import sqlite3
from dataclasses import fields
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from modules import (
    ts_endpoint_database,
    ts_endpoint_evidence,
)
from modules.structure_purpose_manager import (
    PurposeResolution,
    StructurePurpose,
    StructurePurposeContext,
    StructurePurposeManager,
    StructurePurposeResult,
    resolve_structure_purpose,
)
from modules.ts_endpoint_database import TSEndpointDatabase, TSEndpointRecord
from modules.ts_endpoint_generator import (
    CandidateAssessment,
    EndpointCandidate,
    GeneratedTSEndpoint,
    TSEndpointGenerationRequest,
    TSEndpointGenerator,
)
from modules.ts_endpoint_validator import (
    BondChange,
    EndpointThresholdPolicy,
    EndpointValidationRequest,
    EndpointValidationResult,
    EndpointValidationStatus,
    TSEndpointValidator,
    load_endpoint_threshold_policy,
)
from scripts.adsmind_lite.adsmind_common import load_yaml
from scripts.neb_agent.utils_structure import Poscar, read_poscar, write_poscar
from scripts.ts_endpoint import database as endpoint_database_implementation
from scripts.ts_endpoint import evidence as endpoint_evidence_implementation


ROOT = Path(__file__).resolve().parents[1]
PURPOSE_CONFIG = ROOT / "configs" / "structure_purpose_routing.yaml"
CONNECTIVITY_CONFIG = ROOT / "configs" / "ts_connectivity_gate.yaml"


def _structure(
    c_x: float,
    o_x: float,
    *,
    labels: tuple[str, str, str] = ("Fe", "C", "O"),
) -> Poscar:
    return Poscar(
        comment="TS endpoint contract fixture",
        cell=np.eye(3) * 10.0,
        symbols=list(labels),
        counts=[1, 1, 1],
        frac=np.array(
            [
                [0.0, 0.0, 0.0],
                [c_x, 0.2, 0.2],
                [o_x, 0.2, 0.2],
            ]
        ),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )


def _write_endpoint_pair(tmp_path: Path) -> tuple[Path, Path]:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, _structure(0.20, 0.32))
    write_poscar(endpoint, _structure(0.22, 0.41))
    return initial, endpoint


def _generation_request(
    initial: Path,
    **changes: Any,
) -> TSEndpointGenerationRequest:
    values: dict[str, Any] = {
        "reaction_id": "fe110_co_dissociation",
        "surface": "Fe(110)",
        "reaction_type": "CO_dissociation",
        "reactant_id": "co_top",
        "initial_structure": initial,
        "reactive_atoms": (1, 2),
        "adsorbate_atoms": (1, 2),
        "surface_atoms": (0,),
        "bond_changes": (BondChange("break", (1, 2)),),
        "atom_map": ((0, 0), (1, 1), (2, 2)),
    }
    values.update(changes)
    return TSEndpointGenerationRequest(**values)


def _candidate(endpoint: Path, identifier: str = "endpoint-a") -> EndpointCandidate:
    return EndpointCandidate(
        endpoint_id=identifier,
        product_id="c_o_near",
        structure_path=endpoint,
        site="C_near+O_near",
        energy_eV=-1.0,
        structure_file_id="file-endpoint",
    )


def _create_test_endpoint_schema(database: Path) -> None:
    """Create a test-only adapter fixture without reading blocked migrations."""

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


def _create_test_registry_base(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', '8');
            CREATE TABLE calculations (calculation_id TEXT PRIMARY KEY);
            CREATE TABLE files (file_id TEXT PRIMARY KEY);
            """
        )


def _record(
    *,
    identifier: str = "endpoint-a",
    structure_hash: str = "hash-a",
    validation_status: str = "VALID",
) -> TSEndpointRecord:
    return TSEndpointRecord(
        endpoint_record_id=identifier,
        reaction_id="reaction-a",
        endpoint_role="final",
        structure_hash=structure_hash,
        endpoint_version="1",
        validation_status=validation_status,
        validation={"status": validation_status, "reasons": []},
        threshold_version="ts_endpoint_thresholds_v1",
        is_same_as_stable=False,
        endpoint_structure_path="FS.POSCAR",
        created_at="2026-07-27T00:00:00+00:00",
    )


def test_public_endpoint_api_signatures_and_result_fields_are_frozen() -> None:
    signatures = {
        TSEndpointGenerator.__init__: ("self", "validator"),
        TSEndpointGenerator.generate: ("self", "request", "candidates"),
        TSEndpointValidator.__init__: ("self", "config_path"),
        TSEndpointValidator.validate: ("self", "request"),
        load_endpoint_threshold_policy: (
            "config_path",
            "surface",
            "reaction_type",
            "template_id",
        ),
        resolve_structure_purpose: ("context", "config_path"),
        StructurePurposeManager.select_structure: (
            "self",
            "purpose",
            "context",
            "legacy_request",
            "adsorption_request",
            "ts_request",
            "endpoint_candidates",
        ),
        TSEndpointDatabase.save: ("self", "record"),
        TSEndpointDatabase.get: ("self", "endpoint_record_id"),
        TSEndpointDatabase.find_by_reaction: ("self", "reaction_id"),
        ts_endpoint_database.apply_ts_endpoint_migration: (
            "database",
            "rollback",
        ),
        ts_endpoint_database.rollback_empty_ts_endpoint_migration: (
            "database",
            "confirmation",
        ),
    }
    for function, expected in signatures.items():
        assert tuple(inspect.signature(function).parameters) == expected

    assert tuple(field.name for field in fields(GeneratedTSEndpoint)) == (
        "request",
        "candidate",
        "validation",
        "assessments",
    )
    assert tuple(field.name for field in fields(CandidateAssessment)) == (
        "candidate",
        "validation",
        "reuse_eligible",
        "eligibility_reasons",
    )
    assert tuple(field.name for field in fields(EndpointValidationResult)) == (
        "status",
        "threshold_version",
        "applied_threshold_overrides",
        "atom_mapping_method",
        "periodic_mapping_method",
        "expected_bond_changes",
        "observed_bond_changes",
        "site_coordination_bond_changes",
        "unexpected_bond_changes",
        "missing_expected_bond_changes",
        "expected_site_changes",
        "observed_site_changes",
        "unexpected_site_changes",
        "atomic_displacement_A",
        "reactive_displacement_A",
        "adsorbate_com_displacement_A",
        "max_reactive_displacement_A",
        "max_non_reactive_adsorbate_displacement_A",
        "max_surface_displacement_A",
        "migration_flag",
        "validation_score",
        "errors",
        "warnings",
        "reasons",
    )
    assert tuple(status.value for status in EndpointValidationStatus) == (
        "VALID",
        "VALID_WITH_WARNING",
        "REVIEW_REQUIRED",
        "REJECTED",
    )


def test_endpoint_configuration_fields_and_defaults_are_frozen() -> None:
    purpose = load_yaml(PURPOSE_CONFIG)
    connectivity = load_yaml(CONNECTIVITY_CONFIG)
    assert tuple(purpose) == ("schema_version", "enabled", "endpoint_validation")
    assert tuple(purpose["endpoint_validation"]) == (
        "threshold_version",
        "defaults",
        "overrides",
    )
    assert tuple(purpose["endpoint_validation"]["defaults"]) == (
        "reactive_atom_displacement_warning_A",
        "non_reactive_adsorbate_displacement_warning_A",
        "adsorbate_com_displacement_warning_A",
        "surface_atom_displacement_warning_A",
        "covalent_radius_scale",
        "minimum_bond_distance_A",
        "collision_radius_scale",
        "absolute_minimum_distance_A",
        "desorption_height_change_warning_A",
    )
    assert purpose["endpoint_validation"]["threshold_version"] == (
        "ts_endpoint_thresholds_v2"
    )
    assert tuple(connectivity) == (
        "changed_bond_endpoint_tolerance_A",
        "minimum_endpoint_pair_separation_A",
        "minimum_normalized_score_margin",
        "reaction_atom_rmsd_A_max",
        "reaction_atom_max_displacement_A",
        "reaction_atom_endpoint_margin_A_min",
        "fixed_atom_max_displacement_A",
        "unresolved_policy",
    )
    policy = load_endpoint_threshold_policy()
    assert isinstance(policy, EndpointThresholdPolicy)
    assert policy.version == "ts_endpoint_thresholds_v2"
    assert policy.applied_overrides == ()
    assert policy.collision_radius_scale == 0.55
    assert policy.absolute_minimum_distance_A == 1.0
    assert policy.desorption_height_change_warning_A == 2.0


def test_generator_is_deterministic_and_preserves_candidate_structure(
    tmp_path: Path,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    request = _generation_request(initial)
    candidates = (
        _candidate(endpoint, "endpoint-b"),
        _candidate(endpoint, "endpoint-a"),
    )
    before = {path.name: path.read_bytes() for path in (initial, endpoint)}

    first = TSEndpointGenerator().generate(request, candidates)
    second = TSEndpointGenerator().generate(request, candidates)

    assert first.candidate.endpoint_id == second.candidate.endpoint_id == "endpoint-a"
    assert first.validation.as_dict() == second.validation.as_dict()
    assert [item.candidate.endpoint_id for item in first.assessments] == [
        "endpoint-b",
        "endpoint-a",
    ]
    assert first.validation.status is EndpointValidationStatus.VALID
    assert first.validation.observed_bond_changes == (
        BondChange("break", (1, 2)),
    )
    assert first.validation.atom_mapping_method == "reaction_contract_atom_map"
    assert first.candidate.site == "C_near+O_near"
    assert read_poscar(first.candidate.structure_path).labels == ["Fe", "C", "O"]
    assert {path.name: path.read_bytes() for path in (initial, endpoint)} == before


def test_generator_preserves_target_bond_formation(tmp_path: Path) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, _structure(0.20, 0.41))
    write_poscar(endpoint, _structure(0.20, 0.32))
    request = _generation_request(
        initial,
        bond_changes=(BondChange("form", (1, 2)),),
    )
    result = TSEndpointGenerator().generate(request, (_candidate(endpoint),))
    assert result.validation.status is EndpointValidationStatus.VALID
    assert result.validation.observed_bond_changes == (
        BondChange("form", (1, 2)),
    )


def test_generator_input_failures_are_not_converted_to_success(
    tmp_path: Path,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    generator = TSEndpointGenerator()
    with pytest.raises(ValueError, match="endpoint_role"):
        generator.generate(
            _generation_request(initial, endpoint_role="middle"),
            (_candidate(endpoint),),
        )
    with pytest.raises(ValueError, match="no path-compatible"):
        generator.generate(_generation_request(initial), ())


def test_empty_reaction_id_is_rejected_at_request_boundary(
    tmp_path: Path,
) -> None:
    initial, _ = _write_endpoint_pair(tmp_path)
    with pytest.raises(ValueError, match="reaction_id is required"):
        _generation_request(initial, reaction_id="   ")


def test_validator_freezes_pass_mapping_and_reason_order(tmp_path: Path) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    result = TSEndpointValidator().validate(
        EndpointValidationRequest(
            initial_structure=initial,
            endpoint_structure=endpoint,
            reactive_atoms=(1, 2),
            adsorbate_atoms=(1, 2),
            surface_atoms=(0,),
            bond_changes=(BondChange("break", (1, 2)),),
            atom_map=((0, 0), (1, 1), (2, 2)),
        )
    )
    assert result.status is EndpointValidationStatus.VALID
    assert result.errors == ()
    assert result.warnings == ()
    assert result.reasons == ()
    assert result.validation_score == 1.0
    assert tuple(result.as_dict()) == tuple(
        field.name for field in fields(EndpointValidationResult)
    )


def test_endpoint_evidence_is_raw_and_loads_each_ase_structure_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    calls: list[Path] = []
    original_loader = ts_endpoint_evidence.require_ase_structure

    def counted_loader(path: Path) -> Any:
        calls.append(path)
        return original_loader(path)

    monkeypatch.setattr(
        ts_endpoint_evidence,
        "require_ase_structure",
        counted_loader,
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

    assert result.status is EndpointValidationStatus.VALID
    assert calls == [initial, endpoint]
    assert tuple(
        field.name for field in fields(
            ts_endpoint_evidence.EndpointGeometryEvidence
        )
    ) == (
        "atomic_displacement_A",
        "adsorbate_com_displacement_A",
        "initial_connectivity_edges",
        "endpoint_connectivity_edges",
        "endpoint_pair_distances_A",
        "adsorbate_surface_height_change_A",
    )
    evidence_source = inspect.getsource(ts_endpoint_evidence)
    assert "EndpointValidationStatus" not in evidence_source
    assert "REASON" not in evidence_source


def test_validator_reloads_isolated_structures_without_mutating_ase_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    ase_calls: list[Path] = []
    poscar_calls: list[Path] = []
    loaded_ase: list[tuple[Any, tuple[Any, ...]]] = []
    loaded_poscars: list[Poscar] = []
    original_ase_loader = ts_endpoint_evidence.require_ase_structure
    original_poscar_loader = ts_endpoint_evidence.read_poscar

    def ase_snapshot(atoms: Any) -> tuple[Any, ...]:
        return (
            tuple(atoms.get_chemical_symbols()),
            tuple(tuple(float(value) for value in row) for row in atoms.cell),
            tuple(bool(value) for value in atoms.pbc),
            tuple(int(value) for value in atoms.get_tags()),
            tuple(float(value) for value in atoms.get_initial_magnetic_moments()),
            tuple(repr(constraint) for constraint in atoms.constraints),
        )

    def tracked_ase_loader(path: Path) -> Any:
        atoms = original_ase_loader(path)
        ase_calls.append(path)
        loaded_ase.append((atoms, ase_snapshot(atoms)))
        return atoms

    def tracked_poscar_loader(path: Path) -> Poscar:
        structure = original_poscar_loader(path)
        poscar_calls.append(path)
        loaded_poscars.append(structure)
        return structure

    monkeypatch.setattr(
        ts_endpoint_evidence,
        "require_ase_structure",
        tracked_ase_loader,
    )
    monkeypatch.setattr(
        ts_endpoint_evidence,
        "read_poscar",
        tracked_poscar_loader,
    )
    request = EndpointValidationRequest(
        initial_structure=initial,
        endpoint_structure=endpoint,
        reactive_atoms=(1, 2),
        adsorbate_atoms=(1, 2),
        surface_atoms=(0,),
        bond_changes=(BondChange("break", (1, 2)),),
    )

    first = TSEndpointValidator().validate(request)
    write_poscar(endpoint, _structure(0.20, 0.32))
    second = TSEndpointValidator().validate(request)

    assert first.status is EndpointValidationStatus.VALID
    assert second.status is EndpointValidationStatus.REJECTED
    assert second.reasons == ("EXPECTED_BOND_CHANGE_MISSING",)
    assert ase_calls == [initial, endpoint, initial, endpoint]
    assert poscar_calls == [initial, endpoint, initial, endpoint]
    assert len({id(atoms) for atoms, _ in loaded_ase}) == 4
    assert len({id(structure) for structure in loaded_poscars}) == 4
    assert all(ase_snapshot(atoms) == snapshot for atoms, snapshot in loaded_ase)


def test_collector_metric_failure_propagates_without_manager_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    failure = RuntimeError("raw endpoint evidence failed")

    def fail_connectivity(*args: Any, **kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(
        ts_endpoint_evidence,
        "connectivity_edges",
        fail_connectivity,
    )
    events: list[str] = []
    database = _RecordingDatabase(events)
    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=TSEndpointGenerator(),
        ts_endpoint_database=database,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="raw endpoint evidence failed") as caught:
        manager.select_structure(
            StructurePurpose.TS_ENDPOINT,
            ts_request=_generation_request(initial),
            endpoint_candidates=(_candidate(endpoint),),
        )

    assert caught.value is failure
    assert events == []
    assert database.records == []


def test_validator_rejects_mapping_count_and_missing_event_problems(
    tmp_path: Path,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    same = tmp_path / "same.POSCAR"
    wrong_order = tmp_path / "wrong-order.POSCAR"
    short = tmp_path / "short.POSCAR"
    write_poscar(same, _structure(0.20, 0.32))
    write_poscar(wrong_order, _structure(0.22, 0.41, labels=("Fe", "O", "C")))
    short_structure = Poscar(
        comment="short endpoint",
        cell=np.eye(3) * 10.0,
        symbols=["C", "O"],
        counts=[1, 1],
        frac=np.array([[0.2, 0.2, 0.2], [0.41, 0.2, 0.2]]),
        selective=False,
        flags=[(), ()],
    )
    write_poscar(short, short_structure)

    base = {
        "initial_structure": initial,
        "reactive_atoms": (1, 2),
        "adsorbate_atoms": (1, 2),
        "surface_atoms": (0,),
        "bond_changes": (BondChange("break", (1, 2)),),
    }
    identical = TSEndpointValidator().validate(
        EndpointValidationRequest(endpoint_structure=same, **base)
    )
    reordered = TSEndpointValidator().validate(
        EndpointValidationRequest(endpoint_structure=wrong_order, **base)
    )
    count_mismatch = TSEndpointValidator().validate(
        EndpointValidationRequest(endpoint_structure=short, **base)
    )
    bad_map = TSEndpointValidator().validate(
        EndpointValidationRequest(
            endpoint_structure=endpoint,
            atom_map=((0, 0), (1, 2), (2, 1)),
            **base,
        )
    )

    assert identical.status is EndpointValidationStatus.REJECTED
    assert identical.reasons == ("EXPECTED_BOND_CHANGE_MISSING",)
    assert reordered.status is EndpointValidationStatus.REJECTED
    assert any(reason.startswith("STRUCTURE_INCOMPATIBLE:") for reason in reordered.reasons)
    assert count_mismatch.status is EndpointValidationStatus.REJECTED
    assert any(
        reason.startswith("STRUCTURE_INCOMPATIBLE:")
        for reason in count_mismatch.reasons
    )
    assert bad_map.status is EndpointValidationStatus.REJECTED
    assert bad_map.reasons == ("ATOM_MAP_NOT_PRESERVED",)


def test_validator_reports_site_and_unexpected_bond_issues_in_sorted_order(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "FS.POSCAR"
    write_poscar(initial, _structure(0.20, 0.32))
    moved = _structure(0.30, 0.10)
    moved.frac[2, 1:] = (0.0, 0.0)
    write_poscar(endpoint, moved)
    result = TSEndpointValidator().validate(
        EndpointValidationRequest(
            initial_structure=initial,
            endpoint_structure=endpoint,
            reactive_atoms=(1, 2),
            adsorbate_atoms=(1, 2),
            surface_atoms=(0,),
            bond_changes=(BondChange("break", (1, 2)),),
            expected_site_changes=("o:molecular->top",),
            observed_site_changes=("o:molecular->bridge",),
        )
    )
    assert result.status is EndpointValidationStatus.REVIEW_REQUIRED
    assert result.reasons == tuple(sorted(result.reasons))
    assert "EXPECTED_SITE_CHANGE_MISSING" in result.reasons
    assert "UNEXPECTED_BOND_CHANGE" in result.reasons
    assert "UNEXPECTED_SITE_CHANGE" in result.reasons


def test_validator_rejects_close_contact_without_misclassifying_inplane_motion(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    too_close = tmp_path / "too-close.POSCAR"
    detached = tmp_path / "detached.POSCAR"
    write_poscar(initial, _structure(0.20, 0.32))
    write_poscar(too_close, _structure(0.22, 0.24))
    write_poscar(detached, _structure(0.70, 0.90))
    request = {
        "initial_structure": initial,
        "reactive_atoms": (1, 2),
        "adsorbate_atoms": (1, 2),
        "surface_atoms": (0,),
        "bond_changes": (BondChange("break", (1, 2)),),
    }

    close_result = TSEndpointValidator().validate(
        EndpointValidationRequest(endpoint_structure=too_close, **request)
    )
    detached_result = TSEndpointValidator().validate(
        EndpointValidationRequest(endpoint_structure=detached, **request)
    )

    assert close_result.status is EndpointValidationStatus.REJECTED
    assert close_result.reasons == ("UNPHYSICAL_ATOM_CONTACT",)
    assert detached_result.status is EndpointValidationStatus.VALID_WITH_WARNING
    assert detached_result.reasons == ("REACTIVE_ATOM_DISPLACEMENT_WARNING",)


def test_validator_requires_review_for_real_partial_desorption(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "IS.POSCAR"
    endpoint = tmp_path / "desorbed.POSCAR"
    write_poscar(initial, _structure(0.20, 0.32))
    desorbed = _structure(0.22, 0.41)
    desorbed.frac[2, 2] = 0.41
    write_poscar(endpoint, desorbed)

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
    assert result.reasons == (
        "ADSORBATE_DESORPTION_WARNING",
        "REACTIVE_ATOM_DISPLACEMENT_WARNING",
    )


def test_validator_missing_fields_and_invalid_files_raise(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError):
        EndpointValidationRequest()  # type: ignore[call-arg]
    with pytest.raises(FileNotFoundError):
        TSEndpointValidator().validate(
            EndpointValidationRequest(
                initial_structure=tmp_path / "missing-is",
                endpoint_structure=tmp_path / "missing-fs",
                reactive_atoms=(0, 1),
                adsorbate_atoms=(0, 1),
                bond_changes=(BondChange("break", (0, 1)),),
            )
        )
    invalid = tmp_path / "invalid.POSCAR"
    invalid.write_text("not a POSCAR\n", encoding="utf-8")
    with pytest.raises(ValueError):
        TSEndpointValidator().validate(
            EndpointValidationRequest(
                initial_structure=invalid,
                endpoint_structure=invalid,
                reactive_atoms=(0, 1),
                adsorbate_atoms=(0, 1),
                bond_changes=(BondChange("break", (0, 1)),),
            )
        )


class _StableSelector:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def select_stable_structure(self, request: Any) -> Any:
        self.events.append("stable")
        return request


class _LegacySelector:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def select_structure(self, request: Any) -> Any:
        self.events.append("legacy")
        return request


class _SpyValidator:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.delegate = TSEndpointValidator()

    def validate(self, request: EndpointValidationRequest) -> EndpointValidationResult:
        self.events.append("validator")
        return self.delegate.validate(request)


class _RecordingDatabase:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.records: list[TSEndpointRecord] = []

    def save(self, record: TSEndpointRecord) -> str:
        self.events.append("database")
        self.records.append(record)
        return record.endpoint_record_id


class _CountingGenerator(TSEndpointGenerator):
    def __init__(self, validator: _SpyValidator) -> None:
        super().__init__(validator)
        self.calls = 0

    def generate(
        self,
        request: TSEndpointGenerationRequest,
        candidates: Any,
    ) -> GeneratedTSEndpoint:
        self.calls += 1
        return super().generate(request, candidates)


def test_manager_preserves_routing_priority_and_call_order(tmp_path: Path) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    events: list[str] = []
    database = _RecordingDatabase(events)
    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=TSEndpointGenerator(_SpyValidator(events)),
        ts_endpoint_database=database,  # type: ignore[arg-type]
        legacy_workflow=_LegacySelector(events),
    )
    resolution = resolve_structure_purpose(
        StructurePurposeContext(
            purpose=StructurePurpose.ADSORPTION_STABLE,
            parent_purpose=StructurePurpose.TS_ENDPOINT,
            is_new_structure_task=True,
        )
    )
    assert resolution == PurposeResolution(
        StructurePurpose.ADSORPTION_STABLE,
        "PURPOSE_RESOLVED",
        False,
    )

    result = manager.select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=_generation_request(initial),
        endpoint_candidates=(_candidate(endpoint),),
    )
    assert events == ["validator", "database"]
    assert result == StructurePurposeResult(
        purpose=StructurePurpose.TS_ENDPOINT,
        workflow_status="PURPOSE_RESOLVED",
        structure=result.structure,
        ts_endpoint=result.ts_endpoint,
        database_record_id="endpoint-a",
    )
    assert len(database.records) == 1


def test_manager_and_direct_generator_results_are_equivalent_and_single_call(
    tmp_path: Path,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    request = _generation_request(initial)
    candidates = (_candidate(endpoint),)
    direct = TSEndpointGenerator().generate(request, candidates)

    events: list[str] = []
    validator = _SpyValidator(events)
    generator = _CountingGenerator(validator)
    database = _RecordingDatabase(events)
    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=generator,
        ts_endpoint_database=database,  # type: ignore[arg-type]
    )
    managed = manager.select_structure(
        StructurePurpose.TS_ENDPOINT,
        ts_request=request,
        endpoint_candidates=candidates,
    )

    assert generator.calls == 1
    assert events == ["validator", "database"]
    assert managed.ts_endpoint is not None
    assert managed.ts_endpoint.candidate == direct.candidate
    assert managed.ts_endpoint.validation.as_dict() == direct.validation.as_dict()
    assert managed.ts_endpoint.assessments == direct.assessments


def test_manager_does_not_persist_after_validator_failure(tmp_path: Path) -> None:
    initial = tmp_path / "IS.POSCAR"
    identical = tmp_path / "identical.POSCAR"
    write_poscar(initial, _structure(0.20, 0.32))
    write_poscar(identical, _structure(0.20, 0.32))
    events: list[str] = []
    database = _RecordingDatabase(events)
    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=TSEndpointGenerator(_SpyValidator(events)),
        ts_endpoint_database=database,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="no path-compatible"):
        manager.select_structure(
            StructurePurpose.TS_ENDPOINT,
            ts_request=_generation_request(initial),
            endpoint_candidates=(_candidate(identical),),
        )
    assert events == ["validator"]
    assert database.records == []


def test_manager_propagates_validator_exception_without_persistence(
    tmp_path: Path,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    events: list[str] = []

    class RaisingValidator:
        def validate(self, request: EndpointValidationRequest) -> EndpointValidationResult:
            events.append("validator")
            raise RuntimeError("validator failed")

    database = _RecordingDatabase(events)
    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=TSEndpointGenerator(
            RaisingValidator()  # type: ignore[arg-type]
        ),
        ts_endpoint_database=database,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="validator failed"):
        manager.select_structure(
            StructurePurpose.TS_ENDPOINT,
            ts_request=_generation_request(initial),
            endpoint_candidates=(_candidate(endpoint),),
        )
    assert events == ["validator"]
    assert database.records == []


def test_manager_propagates_database_failure_without_success_result(
    tmp_path: Path,
) -> None:
    initial, endpoint = _write_endpoint_pair(tmp_path)
    events: list[str] = []
    failure = sqlite3.OperationalError("database write failed")

    class RaisingDatabase:
        def save(self, record: TSEndpointRecord) -> str:
            events.append("database")
            raise failure

    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=TSEndpointGenerator(_SpyValidator(events)),
        ts_endpoint_database=RaisingDatabase(),  # type: ignore[arg-type]
    )

    with pytest.raises(sqlite3.OperationalError, match="database write failed") as caught:
        manager.select_structure(
            StructurePurpose.TS_ENDPOINT,
            ts_request=_generation_request(initial),
            endpoint_candidates=(_candidate(endpoint),),
        )

    assert caught.value is failure
    assert events == ["validator", "database"]


def test_manager_unknown_and_non_ts_routes_do_not_touch_endpoint_database() -> None:
    events: list[str] = []
    database = _RecordingDatabase(events)
    manager = StructurePurposeManager(
        stable_adsorption_selector=_StableSelector(events),
        ts_endpoint_generator=TSEndpointGenerator(),
        ts_endpoint_database=database,  # type: ignore[arg-type]
        legacy_workflow=_LegacySelector(events),
    )
    unknown = manager.select_structure(
        context=StructurePurposeContext(
            purpose="unknown-purpose",
            is_new_structure_task=True,
        )
    )
    stable = manager.select_structure(
        StructurePurpose.ADSORPTION_STABLE,
        adsorption_request={"stable": True},
    )
    legacy = manager.select_structure(legacy_request={"legacy": True})
    assert unknown.workflow_status == "AWAITING_PURPOSE_CONFIRMATION"
    assert stable.structure == {"stable": True}
    assert legacy.structure == {"legacy": True}
    assert events == ["stable", "legacy"]
    assert database.records == []


def test_database_adapter_crud_duplicate_and_order_without_migration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "endpoint-contract.sqlite3"
    _create_test_endpoint_schema(database_path)
    database = TSEndpointDatabase(database_path)
    first = _record()
    second = _record(identifier="endpoint-b", structure_hash="hash-b")
    rejected = _record(
        identifier="endpoint-rejected",
        structure_hash="hash-rejected",
        validation_status="REJECTED",
    )

    assert database.save(first) == "endpoint-a"
    assert database.save(first) == "endpoint-a"
    with pytest.raises(ValueError, match="different content"):
        database.save(_record(identifier="endpoint-a", structure_hash="other-hash"))
    assert database.save(second) == "endpoint-b"
    assert database.save(rejected) == "endpoint-rejected"
    assert database.get("endpoint-a")["validation"] == {
        "reasons": [],
        "status": "VALID",
    }
    with pytest.raises(KeyError):
        database.get("missing")
    assert [row["endpoint_record_id"] for row in database.find_by_reaction("reaction-a")] == [
        "endpoint-a",
        "endpoint-b",
        "endpoint-rejected",
    ]
    assert not hasattr(database, "update")

    missing_table_path = tmp_path / "missing-table.sqlite3"
    with sqlite3.connect(missing_table_path) as connection:
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
    with pytest.raises(ValueError, match="TS endpoint table is missing"):
        TSEndpointDatabase(missing_table_path).find_by_reaction("reaction-a")


def test_database_adapter_rejects_invalid_records_and_rolls_back_failures(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unsupported characters"):
        _record(identifier="invalid id")
    with pytest.raises(ValueError, match="reaction_id is required"):
        TSEndpointRecord(
            **{
                **_record().as_dict(),
                "reaction_id": " ",
            }
        )
    with pytest.raises(ValueError, match="reviewed structure path"):
        TSEndpointRecord(
            **{
                **_record().as_dict(),
                "endpoint_structure_path": None,
            }
        )

    database_path = tmp_path / "endpoint-rollback.sqlite3"
    _create_test_endpoint_schema(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_endpoint_insert
            BEFORE INSERT ON ts_endpoint_records
            BEGIN
                SELECT RAISE(ABORT, 'forced adapter failure');
            END
            """
        )
    database = TSEndpointDatabase(database_path)
    with pytest.raises(sqlite3.IntegrityError, match="forced adapter failure"):
        database.save(_record())
    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM ts_endpoint_records"
        ).fetchone()[0]
    assert count == 0


def test_database_serialization_failure_rolls_back_without_partial_record(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "endpoint-serialization.sqlite3"
    _create_test_endpoint_schema(database_path)
    values = _record(
        identifier="serialization-failure",
        structure_hash="hash-serialization",
    ).as_dict()
    values["validation"] = {"not_json_serializable": object()}
    record = TSEndpointRecord(**values)

    with pytest.raises(TypeError):
        TSEndpointDatabase(database_path).save(record)

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM ts_endpoint_records"
        ).fetchone()[0]
    assert count == 0


def test_endpoint_migration_is_validated_repeatable_and_transactional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "endpoint-migration.sqlite3"
    _create_test_registry_base(database_path)

    ts_endpoint_database.apply_ts_endpoint_migration(database_path)
    ts_endpoint_database.apply_ts_endpoint_migration(database_path)
    assert TSEndpointDatabase(database_path).save(_record()) == "endpoint-a"

    failed_path = tmp_path / "endpoint-migration-failure.sqlite3"
    _create_test_registry_base(failed_path)

    def fail_validation(connection: Any) -> None:
        raise ValueError("forced post-migration validation failure")

    monkeypatch.setattr(
        ts_endpoint_database,
        "_validate_endpoint_schema",
        fail_validation,
    )
    with pytest.raises(ValueError, match="forced post-migration"):
        ts_endpoint_database.apply_ts_endpoint_migration(failed_path)
    with sqlite3.connect(failed_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='ts_endpoint_records'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT value FROM schema_metadata "
            "WHERE key='ts_endpoint_schema_version'"
        ).fetchone() is None


def test_endpoint_migration_rejects_incompatible_schema_before_execution(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "incompatible-migration.sqlite3"
    _create_test_registry_base(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE ts_endpoint_records (sentinel_only TEXT)")

    with pytest.raises(ValueError, match="incompatible TS endpoint schema columns"):
        ts_endpoint_database.apply_ts_endpoint_migration(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(ts_endpoint_records)"
            )
        )
    assert columns == ("sentinel_only",)


def test_endpoint_rollback_requires_confirmation_and_refuses_nonempty_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "endpoint-rollback-guard.sqlite3"
    _create_test_registry_base(database_path)
    ts_endpoint_database.apply_ts_endpoint_migration(database_path)

    with pytest.raises(ValueError, match="prohibited by default"):
        ts_endpoint_database.apply_ts_endpoint_migration(
            database_path,
            rollback=True,
        )
    with pytest.raises(ValueError, match="explicit empty"):
        ts_endpoint_database.rollback_empty_ts_endpoint_migration(
            database_path,
            confirmation="wrong",
        )

    TSEndpointDatabase(database_path).save(_record())
    with pytest.raises(ValueError, match="non-empty"):
        ts_endpoint_database.rollback_empty_ts_endpoint_migration(
            database_path,
            confirmation="DROP EMPTY TS ENDPOINT TABLE",
        )
    assert TSEndpointDatabase(database_path).get("endpoint-a")["reaction_id"] == (
        "reaction-a"
    )

    empty_path = tmp_path / "empty-endpoint-rollback.sqlite3"
    _create_test_registry_base(empty_path)
    ts_endpoint_database.apply_ts_endpoint_migration(empty_path)
    ts_endpoint_database.rollback_empty_ts_endpoint_migration(
        empty_path,
        confirmation="DROP EMPTY TS ENDPOINT TABLE",
    )
    with sqlite3.connect(empty_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='ts_endpoint_records'"
        ).fetchone() is None


def test_adapter_does_not_run_migration_or_replace_incompatible_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "incompatible-endpoint.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', '8');
            CREATE TABLE ts_endpoint_records (sentinel_only TEXT);
            """
        )

    def forbidden_migration(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("blocked endpoint migration was called")

    monkeypatch.setattr(
        ts_endpoint_database,
        "_execute_sql_file",
        forbidden_migration,
    )
    monkeypatch.setattr(
        ts_endpoint_database,
        "apply_ts_endpoint_migration",
        forbidden_migration,
    )

    with pytest.raises(sqlite3.OperationalError):
        TSEndpointDatabase(database_path).find_by_reaction("reaction-a")

    with sqlite3.connect(database_path) as connection:
        columns = [
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(ts_endpoint_records)"
            ).fetchall()
        ]
        endpoint_version = connection.execute(
            "SELECT value FROM schema_metadata "
            "WHERE key='ts_endpoint_schema_version'"
        ).fetchone()
    assert columns == ["sentinel_only"]
    assert endpoint_version is None


def test_database_adapter_has_no_endpoint_science_dependency() -> None:
    source = ROOT / "scripts" / "ts_endpoint" / "database.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "scripts.ts_endpoint.validator" not in imported_modules
    assert "scripts.ts_endpoint.generator" not in imported_modules
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "validate" not in calls


def test_legacy_endpoint_modules_alias_canonical_implementations() -> None:
    aliases = {
        "modules.ts_endpoint_database": "scripts.ts_endpoint.database",
        "modules.ts_endpoint_evidence": "scripts.ts_endpoint.evidence",
        "modules.ts_endpoint_validator": "scripts.ts_endpoint.validator",
        "modules.ts_endpoint_generator": "scripts.ts_endpoint.generator",
        "modules.structure_purpose_manager": "scripts.ts_endpoint.purpose",
    }
    for legacy_name, canonical_name in aliases.items():
        assert importlib.import_module(legacy_name) is importlib.import_module(canonical_name)
    assert ts_endpoint_database is endpoint_database_implementation
    assert ts_endpoint_evidence is endpoint_evidence_implementation


def test_endpoint_implementation_does_not_depend_on_modules_package() -> None:
    implementation_root = ROOT / "scripts" / "ts_endpoint"
    for source in implementation_root.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not {name for name in imports if name == "modules" or name.startswith("modules.")}
