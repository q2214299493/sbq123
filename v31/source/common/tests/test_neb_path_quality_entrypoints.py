from __future__ import annotations

import copy
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts.neb_agent import path_quality_cli, path_quality_service, pilot_validation
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.path_quality_control import (
    collect_evidence,
    evaluate_quality,
    quality_source_paths,
)
from scripts.neb_agent.path_quality_service import PathQualityRequest
from scripts.neb_agent.utils_structure import Poscar, write_poscar
from scripts.ts_strategy_engine import workflow
from scripts.ts_strategy_engine.workflow import AnalyzeRequest


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_FIELDS = (
    "schema_version",
    "PATH_QUALITY_STATUS",
    "REASON_CODES",
    "CRITICAL_IMAGES",
    "EVIDENCE",
    "CHEMICAL_INTERPRETATION",
    "FILES_SAVED",
    "NEXT_REQUIRED_EVIDENCE_CHECK",
    "execution_authority",
    "COMPUTE_COST_ASSESSMENT",
)


def _evidence(case: str) -> dict:
    smooth = {
        "image_names": ["00", "01", "02", "03", "04"],
        "important_interval_A": [1.5, 2.1],
        "coordinate_history_A": [
            [1.2, 1.5, 1.8, 2.1, 2.4] for _ in range(5)
        ],
        "adjacent_pair_metrics": [
            {
                "max_displacement_A": 0.4,
                "rms_displacement_A": 0.1,
                "largest_moves": [],
            }
            for _ in range(4)
        ],
        "energies_eV": [0.0, 0.1, 0.2, 0.1, 0.0],
        "scf_iterations": {"02": [20, 18, 19, 17, 16]},
        "projected_force_history_eV_per_A": {},
        "highest_image_history": ["02"] * 5,
        "image_ordering_valid": True,
        "mixed_elementary_steps": False,
        "invalid_endpoints": False,
    }
    if case == "single_warning":
        smooth["invalid_endpoints"] = True
    elif case == "electronic_failure":
        smooth["scf_iterations"] = {"02": [200, 200, 200, 200, 200]}
    elif case == "large_displacement":
        smooth["coordinate_history_A"] = [
            [1.2, 1.4, 1.6, 1.9, 2.1] for _ in range(5)
        ]
        smooth["adjacent_pair_metrics"][2]["max_displacement_A"] = 1.2
        smooth["energies_eV"] = [None] * 5
    elif case == "multiple_problems":
        smooth["coordinate_history_A"] = [
            [1.176, 1.181, 1.218, 1.299, value, 2.768, 3.237]
            for value in [2.270, 2.281, 2.294, 2.305, 2.317]
        ]
        smooth["image_names"] = ["00", "01", "02", "03", "04", "05", "06"]
        smooth["adjacent_pair_metrics"] = [
            {
                "max_displacement_A": value,
                "rms_displacement_A": 0.1,
                "largest_moves": [],
            }
            for value in (0.84, 0.92, 0.88, 0.93, 0.87, 1.02)
        ]
        smooth["energies_eV"] = [None] * 7
        smooth["scf_iterations"] = {"02": [200, 200, 200, 200, 200]}
        smooth["projected_force_history_eV_per_A"] = {
            "04": [0.270, 0.263, 0.257, 0.247, 0.241]
        }
        smooth["highest_image_history"] = ["04"] * 5
    elif case == "collision_context":
        smooth["geometry_diagnosis"] = {
            "status": "STOP",
            "errors": ["image_01:unphysical_contact_pair_0_1"],
        }
    return smooth


def _write_inputs(workdir: Path) -> tuple[Path, Path]:
    workdir.mkdir()
    (workdir / "INCAR").write_text("NELM = 200\n", encoding="ascii")
    quality = workdir / "quality.yaml"
    shared = workdir / "shared.yaml"
    quality.write_text(
        (ROOT / "configs" / "neb_path_quality_control_v2.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    shared.write_text(
        (ROOT / "configs" / "neb_agent" / "default_thresholds.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return quality, shared


def _request(
    workdir: Path,
    quality: Path,
    shared: Path,
    *,
    configured_nelm: int | None = 200,
) -> PathQualityRequest:
    return PathQualityRequest(
        workdir=workdir,
        reaction_pair=(0, 1),
        important_interval=(1.5, 2.1),
        quality_thresholds=quality,
        geometry_thresholds=shared,
        configured_nelm=configured_nelm,
    )


def _write_real_path(workdir: Path) -> tuple[Path, Path]:
    quality, shared = _write_inputs(workdir)
    cell = np.diag([10.0, 10.0, 10.0])
    for index, distance in enumerate((1.2, 1.5, 1.8, 2.1, 2.4)):
        structure = Poscar(
            comment=f"image {index}",
            cell=cell,
            symbols=["C", "O"],
            counts=[1, 1],
            frac=np.array([[0.10, 0.10, 0.10], [0.10 + distance / 10.0, 0.10, 0.10]]),
            selective=False,
            flags=[(), ()],
        )
        write_poscar(workdir / f"{index:02d}" / "POSCAR", structure)
    return quality, shared


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reasons"),
    [
        (
            "ordinary",
            "ORDINARY_NEB_PROGRESS_EVIDENCE",
            ["C_gap_persistent_or_increasing"],
        ),
        (
            "single_warning",
            "ORDINARY_NEB_PROGRESS_EVIDENCE",
            [
                "C_gap_persistent_or_increasing",
                "UNVERIFIED_INVALID_ENDPOINT_FLAG",
            ],
        ),
        (
            "electronic_failure",
            "ELECTRONIC_FAILURE",
            [
                "C_gap_persistent_or_increasing",
                "ELECTRONIC_CONVERGENCE_FAILURE",
            ],
        ),
        (
            "large_displacement",
            "UNDERRESOLVED_REACTION_COORDINATE",
            [
                "A_abnormal_adjacent_displacement",
                "C_gap_persistent_or_increasing",
            ],
        ),
        (
            "multiple_problems",
            "UNDERRESOLVED_REACTION_COORDINATE",
            [
                "B_large_reaction_coordinate_gap",
                "C_gap_persistent_or_increasing",
                "E_important_interval_unsampled",
                "G_neighbouring_images_in_separate_basins",
                "H_force_drop_from_product_basin_motion",
                "ELECTRONIC_CONVERGENCE_FAILURE",
            ],
        ),
        (
            "collision_context",
            "ORDINARY_NEB_PROGRESS_EVIDENCE",
            ["C_gap_persistent_or_increasing"],
        ),
    ],
)
def test_all_path_quality_entrypoints_are_semantically_identical(
    case: str,
    expected_status: str,
    expected_reasons: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_inputs(workdir)
    evidence = _evidence(case)
    monkeypatch.setattr(
        path_quality_service,
        "collect_evidence",
        lambda *args, **kwargs: copy.deepcopy(evidence),
    )
    thresholds = path_quality_service.load_path_quality_thresholds(quality, shared)
    direct_evidence = copy.deepcopy(evidence)
    direct_evidence["configured_nelm"] = 200
    direct = evaluate_quality(direct_evidence, thresholds)

    application = path_quality_service.build_path_quality_report(
        _request(workdir, quality, shared)
    )
    pilot = pilot_validation.build_pilot_path_quality_result(
        _request(workdir, quality, shared)
    )

    cli_output = workdir / "cli_quality.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "path_quality_cli",
            "--workdir",
            str(workdir),
            "--reaction-pair",
            "0:1",
            "--important-interval",
            "1.5:2.1",
            "--thresholds",
            str(quality),
            "--geometry-thresholds",
            str(shared),
            "--output",
            str(cli_output),
        ],
    )
    assert path_quality_cli.main() == 0
    cli = json.loads(cli_output.read_text(encoding="utf-8"))

    workflow_report = workflow._path_quality(
        AnalyzeRequest(
            workdir=workdir,
            contract=workdir / "contract.json",
            thresholds=shared,
            quality_thresholds=quality,
        ),
        {
            "reaction_coordinates": [
                {
                    "role": "primary",
                    "atoms": [0, 1],
                    "important_interval_A": [1.5, 2.1],
                }
            ]
        },
        {"status": "HAS_OUTPUT", "configured_nelm": 200},
    )

    assert direct["PATH_QUALITY_STATUS"] == expected_status
    assert direct["REASON_CODES"] == expected_reasons
    for result in (application, cli, workflow_report, pilot):
        assert {field: result[field] for field in EVALUATOR_FIELDS} == direct
        assert tuple(result) == (
            *EVALUATOR_FIELDS,
            "document_kind",
            "producer",
            "source_files",
        )
        assert result["document_kind"] == "neb_path_quality_evidence"
        assert result["producer"] == "scripts.neb_agent.path_quality_control"
        assert result["source_files"] == application["source_files"]
    assert application == cli == workflow_report == pilot


def test_real_file_collection_matches_all_entrypoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_real_path(workdir)
    request = _request(workdir, quality, shared, configured_nelm=None)
    application = path_quality_service.build_path_quality_report(request)
    pilot = pilot_validation.build_pilot_path_quality_result(request)

    cli_output = workdir / "cli_quality.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "path_quality_cli",
            "--workdir",
            str(workdir),
            "--reaction-pair",
            "0:1",
            "--important-interval",
            "1.5:2.1",
            "--thresholds",
            str(quality),
            "--geometry-thresholds",
            str(shared),
            "--output",
            str(cli_output),
        ],
    )
    assert path_quality_cli.main() == 0
    cli = json.loads(cli_output.read_text(encoding="utf-8"))
    workflow_report = workflow._path_quality(
        AnalyzeRequest(
            workdir=workdir,
            contract=workdir / "contract.json",
            thresholds=shared,
            quality_thresholds=quality,
        ),
        {
            "reaction_coordinates": [
                {
                    "role": "primary",
                    "atoms": [0, 1],
                    "important_interval_A": [1.5, 2.1],
                }
            ]
        },
        {"status": "HAS_OUTPUT", "configured_nelm": 200},
    )

    assert application["PATH_QUALITY_STATUS"] == "ORDINARY_NEB_PROGRESS_EVIDENCE"
    assert application["REASON_CODES"] == ["C_gap_persistent_or_increasing"]
    assert application == cli == workflow_report == pilot


def test_unphysical_contact_remains_owned_by_geometry_diagnosis(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_inputs(workdir)
    cell = np.diag([10.0, 10.0, 10.0])
    for index in range(3):
        structure = Poscar(
            comment=f"collision image {index}",
            cell=cell,
            symbols=["C", "O"],
            counts=[1, 1],
            frac=np.array([[0.10, 0.10, 0.10], [0.14, 0.10, 0.10]]),
            selective=False,
            flags=[(), ()],
        )
        write_poscar(workdir / f"{index:02d}" / "POSCAR", structure)

    geometry = diagnose(
        workdir,
        ["0", "1"],
        [],
        shared,
        reaction_pairs=[[0, 1]],
        expected_interior=1,
    )
    assert geometry["status"] == "STOP"
    assert any("unphysical_contact_pair_0_1" in item for item in geometry["errors"])

    thresholds = path_quality_service.load_path_quality_thresholds(quality, shared)
    evidence = _evidence("collision_context")
    evidence["configured_nelm"] = 200
    result = evaluate_quality(evidence, thresholds)
    assert result["PATH_QUALITY_STATUS"] == "ORDINARY_NEB_PROGRESS_EVIDENCE"
    assert all("contact" not in reason.lower() for reason in result["REASON_CODES"])


def test_legacy_path_quality_module_paths_and_signatures_remain_available() -> None:
    assert list(inspect.signature(quality_source_paths).parameters) == [
        "workdir",
        "extras",
    ]
    assert list(inspect.signature(collect_evidence).parameters) == [
        "workdir",
        "pair",
        "important_interval",
        "cycles",
        "monitor",
    ]
    assert list(inspect.signature(evaluate_quality).parameters) == [
        "evidence",
        "thresholds",
    ]
    assert list(inspect.signature(path_quality_cli.main).parameters) == []
    assert list(inspect.signature(pilot_validation.build_pilot_result).parameters) == [
        "pilot_dir",
        "production_dir",
        "job_id",
    ]


def test_evaluator_and_service_do_not_mutate_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_inputs(workdir)
    evidence = _evidence("ordinary")
    evidence_before = copy.deepcopy(evidence)
    thresholds = path_quality_service.load_path_quality_thresholds(quality, shared)
    thresholds_before = copy.deepcopy(thresholds)
    evaluator_evidence = copy.deepcopy(evidence)
    evaluator_evidence["configured_nelm"] = 200
    evaluator_before = copy.deepcopy(evaluator_evidence)

    evaluate_quality(evaluator_evidence, thresholds)
    assert evaluator_evidence == evaluator_before
    assert thresholds == thresholds_before

    monkeypatch.setattr(
        path_quality_service,
        "collect_evidence",
        lambda *args, **kwargs: evidence,
    )
    path_quality_service.build_path_quality_report(
        _request(workdir, quality, shared)
    )
    assert evidence == evidence_before


def test_invalid_configuration_is_rejected_before_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_inputs(workdir)
    quality.write_text("version: 2\n", encoding="utf-8")
    collected = False

    def unexpected_collection(*args, **kwargs):
        nonlocal collected
        collected = True

    monkeypatch.setattr(
        path_quality_service,
        "collect_evidence",
        unexpected_collection,
    )
    with pytest.raises(
        ValueError,
        match="missing required section: persistence",
    ):
        path_quality_service.build_path_quality_report(
            _request(workdir, quality, shared)
        )
    assert collected is False


def test_missing_configuration_file_has_clear_cli_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workdir = tmp_path / "neb"
    workdir.mkdir()
    output = workdir / "quality.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "path_quality_cli",
            "--workdir",
            str(workdir),
            "--reaction-pair",
            "0:1",
            "--important-interval",
            "1.5:2.1",
            "--thresholds",
            str(workdir / "missing.yaml"),
            "--output",
            str(output),
        ],
    )

    assert path_quality_cli.main() == 1
    assert "path-quality error:" in capsys.readouterr().err
    assert not output.exists()


def test_missing_input_and_evaluator_errors_do_not_write_success_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_inputs(workdir)
    output = workdir / "quality.json"
    argv = [
        "path_quality_cli",
        "--workdir",
        str(workdir),
        "--reaction-pair",
        "0:1",
        "--important-interval",
        "1.5:2.1",
        "--thresholds",
        str(quality),
        "--geometry-thresholds",
        str(shared),
        "--output",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert path_quality_cli.main() == 1
    assert "at least three NEB image directories are required" in capsys.readouterr().err
    assert not output.exists()

    monkeypatch.setattr(
        path_quality_service,
        "collect_evidence",
        lambda *args, **kwargs: _evidence("ordinary"),
    )
    monkeypatch.setattr(
        path_quality_service,
        "evaluate_quality",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("expected evaluator error")
        ),
    )
    assert path_quality_cli.main() == 1
    assert "expected evaluator error" in capsys.readouterr().err
    assert not output.exists()


def test_output_write_failure_is_reported_without_success_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workdir = tmp_path / "neb"
    quality, shared = _write_inputs(workdir)
    monkeypatch.setattr(
        path_quality_service,
        "collect_evidence",
        lambda *args, **kwargs: _evidence("ordinary"),
    )
    monkeypatch.setattr(
        path_quality_cli,
        "write_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("simulated write failure")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "path_quality_cli",
            "--workdir",
            str(workdir),
            "--reaction-pair",
            "0:1",
            "--important-interval",
            "1.5:2.1",
            "--thresholds",
            str(quality),
            "--geometry-thresholds",
            str(shared),
        ],
    )

    assert path_quality_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "simulated write failure" in captured.err
    assert not (workdir / "neb_path_quality.json").exists()


def test_workflow_missing_quality_inputs_preserves_legacy_returns() -> None:
    request = AnalyzeRequest(
        Path("."),
        Path("contract.json"),
        Path("thresholds.yaml"),
    )
    assert workflow._path_quality(request, {}, {"status": "NO_OUTPUT"}) == {}
    assert workflow._path_quality(
        request,
        {"reaction_coordinates": []},
        {"status": "HAS_OUTPUT"},
    ) == {
        "PATH_QUALITY_STATUS": "INVALID_ENDPOINTS",
        "REASON_CODES": ["PRIMARY_REACTION_COORDINATE_MISSING"],
        "CRITICAL_IMAGES": [],
    }
