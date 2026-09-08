from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import load_json_object, source_file_manifest
from scripts.neb_agent.path_quality_control import (
    collect_evidence,
    evaluate_quality,
    quality_source_paths,
)


@dataclass(frozen=True)
class PathQualityRequest:
    workdir: Path
    reaction_pair: tuple[int, int]
    important_interval: tuple[float, float]
    quality_thresholds: Path
    geometry_thresholds: Path
    monitor_evidence: Path | None = None
    monitor: dict[str, Any] | None = None
    configured_nelm: int | None = None


def load_path_quality_thresholds(
    quality_path: Path,
    geometry_path: Path,
) -> dict[str, Any]:
    quality = _load_yaml_mapping(quality_path, "path-quality thresholds")
    shared = _load_yaml_mapping(geometry_path, "geometry thresholds")
    _require_mapping_keys(
        quality,
        {
            "persistence": (
                "monitoring_cycles_min",
                "underresolved_independent_family_count_min",
            ),
            "geometry": (
                "abnormal_gap_ratio_to_median_min",
                "gap_non_decrease_fraction",
                "reactant_basin_span_max_A",
            ),
            "energy": ("sharp_corner_threshold_eV",),
            "readiness": (
                "pre_ci_projected_force_eV_per_A_max",
                "recent_coordinate_drift_A_max",
            ),
        },
        "path-quality thresholds",
    )
    for key in ("image_jump_warning_A", "scf_consecutive_exhaustion_hard_min"):
        if key not in shared:
            raise ValueError(f"geometry thresholds missing required field: {key}")
    thresholds = copy.deepcopy(quality)
    thresholds["geometry"]["image_jump_warning_A"] = shared["image_jump_warning_A"]
    thresholds["electronic"] = {
        "consecutive_nelm_exhaustion_hard_min": shared[
            "scf_consecutive_exhaustion_hard_min"
        ]
    }
    return thresholds


def build_path_quality_report(request: PathQualityRequest) -> dict[str, Any]:
    thresholds = load_path_quality_thresholds(
        request.quality_thresholds,
        request.geometry_thresholds,
    )
    if request.monitor is not None and request.monitor_evidence is not None:
        raise ValueError("provide monitor data or monitor-evidence path, not both")
    monitor = (
        copy.deepcopy(request.monitor)
        if request.monitor is not None
        else (
            load_json_object(request.monitor_evidence)
            if request.monitor_evidence is not None
            else {}
        )
    )
    evidence = collect_evidence(
        request.workdir,
        request.reaction_pair,
        request.important_interval,
        int(thresholds["persistence"]["monitoring_cycles_min"]),
        monitor,
    )
    evidence = copy.deepcopy(evidence)
    evidence["configured_nelm"] = (
        request.configured_nelm
        if request.configured_nelm is not None
        else read_configured_nelm(request.workdir / "INCAR")
    )
    report = evaluate_quality(evidence, thresholds)
    report.update(
        {
            "document_kind": "neb_path_quality_evidence",
            "producer": "scripts.neb_agent.path_quality_control",
            "source_files": source_file_manifest(
                quality_source_paths(
                    request.workdir,
                    [
                        request.quality_thresholds,
                        request.geometry_thresholds,
                        *(
                            [request.monitor_evidence]
                            if request.monitor_evidence is not None
                            else []
                        ),
                    ],
                )
            ),
        }
    )
    return report


def read_configured_nelm(path: Path) -> int:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.split("=", 1)[0].strip().upper() == "NELM":
            return int(float(line.split("=", 1)[1].split()[0]))
    return 60


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a YAML mapping: {path}")
    return payload


def _require_mapping_keys(
    payload: dict[str, Any],
    required: dict[str, tuple[str, ...]],
    label: str,
) -> None:
    for section, keys in required.items():
        values = payload.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"{label} missing required section: {section}")
        for key in keys:
            if key not in values:
                raise ValueError(f"{label} missing required field: {section}.{key}")
