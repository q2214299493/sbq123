from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import write_json
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.check_endpoints import check_endpoints, write_report as write_endpoint_report
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.generate_path import generate_path
from scripts.neb_agent.path_quality_service import (
    PathQualityRequest,
    build_path_quality_report,
)

from .contract import load_contract
from .evidence import validate_endpoint_evidence
from .fingerprint import build_fingerprint, rank_templates
from .path_evidence import load_json_object, require_file, validate_path_binding, validate_path_review
from .strategy import compose_strategy, decide_search
from .templates import load_templates
from .learning_store import get_event
from .strategy_learning import apply_variant, task_lessons

@dataclass(frozen=True)
class PlanRequest:
    initial: Path
    final: Path
    contract: Path
    workdir: Path
    database: Path
    families: Path
    thresholds: Path
    initialize_path: bool = False
    constraints: Path | None = None
    waypoint: tuple[Path, ...] = field(default_factory=tuple)
    output_dir: Path | None = None
    images: int | None = None
    rebuild: bool = False
    gate_decision: Path | None = None
    gate_state_sha256: str | None = None
    strategy_variant: str | None = None

@dataclass(frozen=True)
class AnalyzeRequest:
    workdir: Path
    contract: Path
    thresholds: Path
    path_review: Path | None = None
    quality_thresholds: Path = Path("configs/neb_path_quality_control_v2.yaml")
    preflight: Path | None = None
    validation: Path | None = None
    scheduler: Path | None = None

def plan(request: PlanRequest) -> dict[str, Any]:
    for path, label in (
        (request.initial, "IS"),
        (request.final, "FS"),
        (request.contract, "reaction contract"),
        (request.families, "family rules"),
    ):
        require_file(path, label)
    contract = load_contract(request.contract)
    if (request.workdir / "ts_strategy.json").exists():
        raise SystemExit("Strategy output already exists; use a new workdir.")
    request.workdir.mkdir(parents=True, exist_ok=True)
    _validate_endpoints(request, contract)

    fingerprint = build_fingerprint(contract)
    templates = load_templates(request.database)
    ranked = rank_templates(fingerprint, templates)
    rules = yaml.safe_load(request.families.read_text(encoding="utf-8"))
    strategy = compose_strategy(fingerprint, ranked, rules)
    strategy["learning_failure_constraints"] = task_lessons(request.database, contract["reaction_id"])
    if request.strategy_variant:
        variant = get_event(request.database, "variant", request.strategy_variant)
        if contract["reaction_id"] not in variant["cases"]:
            raise ValueError("strategy variant is outside its frozen reaction case set")
        if request.images is not None and request.images != variant["settings"]["initial_images"]:
            raise ValueError("--images conflicts with the bound strategy variant")
        strategy = apply_variant(request.database, request.strategy_variant, strategy)
        if request.initialize_path and strategy["candidate_method_preference"] == "aqcat25_ba_sella":
            raise ValueError("BA-Sella is a GPU candidate reference branch; prepare its reviewed handoff instead of a NEB path")
        if request.initialize_path and strategy["candidate_method_preference"] == "matris_ml_neb_sella":
            raise ValueError("MatRIS NEB/Sella requires a reviewed dual-model GPU request with sella_refinement settings")
    _write_plan_evidence(request, contract, fingerprint, templates, ranked)
    if not strategy["status"].startswith("STOP") and request.initialize_path:
        _initialize_path(request, contract, fingerprint, strategy)
    _finish_plan(request.workdir, strategy)
    if strategy["status"].startswith("STOP"):
        raise SystemExit(2)
    return strategy

def _validate_endpoints(request: PlanRequest, contract: dict[str, Any]) -> None:
    endpoint = check_endpoints(request.initial, request.final, contract)
    evidence = validate_endpoint_evidence(request.database, contract)
    write_endpoint_report(request.workdir, endpoint)
    write_json(request.workdir / "endpoint_evidence.json", evidence)
    if endpoint["status"] == "STOP" or evidence["status"] == "STOP":
        raise SystemExit(2)

def _write_plan_evidence(
    request: PlanRequest,
    contract: dict[str, Any],
    fingerprint: dict[str, Any],
    templates: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
) -> None:
    write_json(request.workdir / "reaction_contract.normalized.json", contract)
    write_json(request.workdir / "reaction_fingerprint.json", fingerprint)
    keys = (
        "template_id",
        "score",
        "match_level",
        "strategy_match_level",
        "compatible",
        "chemical_match",
        "reaction_event_similarity",
        "evidence_valid",
        "strategy_transferable",
        "result_transferable",
        "transferable",
    )
    write_json(
        request.workdir / "template_retrieval.json",
        {
            "database": str(request.database),
            "template_count": len(templates),
            "top_matches": [{key: item[key] for key in keys} for item in ranked[:5]],
        },
    )

def _initialize_path(
    request: PlanRequest,
    contract: dict[str, Any],
    fingerprint: dict[str, Any],
    strategy: dict[str, Any],
) -> None:
    require_file(request.thresholds, "geometry thresholds")
    waypoints = _resolve_waypoints(request.contract, contract, request.waypoint)
    for waypoint in waypoints:
        require_file(waypoint, "reviewed waypoint")
    constraints = _resolve_constraints(request, contract)
    images = request.images if request.images is not None else int(strategy["neb_settings"].get("initial_images", 3))
    output = request.output_dir or request.workdir / "path_candidate"
    generated = generate_path(
        request.initial,
        request.final,
        output,
        images,
        strategy["interpolation_strategy"],
        constraints,
        list(waypoints),
        rebuild=request.rebuild,
        gate_decision=request.gate_decision,
        gate_state_sha256=request.gate_state_sha256,
    )
    generated.update(_path_provenance(contract, fingerprint, strategy))
    if generated["status"] != "STOP":
        write_json(output / "path_generation_report.json", generated)
    strategy["path_generation"] = generated
    if generated["status"] == "STOP":
        strategy["status"] = "STOP_PATH_GENERATION"
        return
    pairs = contract["broken_bonds"] or contract["formed_bonds"]
    geometry = diagnose(
        output,
        [str(index) for index in contract["reaction_atoms"]],
        [],
        request.thresholds,
        reaction_pairs=pairs,
        expected_interior=images,
    )
    strategy["path_geometry"] = geometry
    strategy["status"] = (
        "STOP_PATH_GEOMETRY"
        if geometry["status"] == "STOP"
        else "NEEDS_PATH_REVIEW"
    )

def _resolve_waypoints(contract_path: Path, contract: dict[str, Any], explicit: tuple[Path, ...]) -> tuple[Path, ...]:
    values = [Path(value) for value in contract.get("waypoint_files", [])] + list(explicit)
    return tuple(value if value.is_absolute() else contract_path.parent / value for value in values)

def _resolve_constraints(request: PlanRequest, contract: dict[str, Any]) -> Path | None:
    constraints = request.constraints
    if constraints is None and contract.get("retrieval_constraints"):
        retrieval = contract["retrieval_constraints"]
        value = retrieval.get("constraints_file") if isinstance(retrieval, dict) else retrieval
        if value:
            path = Path(str(value))
            constraints = path if path.is_absolute() else request.contract.parent / path
    if constraints is not None:
        require_file(constraints, "reviewed retrieval constraints")
    return constraints

def _path_provenance(
    contract: dict[str, Any], fingerprint: dict[str, Any], strategy: dict[str, Any]
) -> dict[str, Any]:
    return {
        "contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility_sha256": contract["compatibility_sha256"],
        "fingerprint_id": fingerprint["fingerprint_id"],
        "strategy_source": strategy["strategy_source"],
        "template_id": (strategy["template_match"] or {}).get("template_id"),
        "waypoint_strategy": strategy["waypoint_strategy"],
        "interpolation_strategy": strategy["interpolation_strategy"],
    }


def _finish_plan(workdir: Path, strategy: dict[str, Any]) -> None:
    write_json(workdir / "ts_strategy.json", strategy)
    print(strategy["status"])


def analyze_search(request: AnalyzeRequest) -> dict[str, Any]:
    if not request.workdir.is_dir():
        raise SystemExit(f"workdir not found: {request.workdir}")
    contract = load_contract(request.contract)
    require_file(request.thresholds, "analysis thresholds")
    pairs = contract["broken_bonds"] or contract["formed_bonds"]
    geometry = diagnose(
        request.workdir,
        [str(index) for index in contract["reaction_atoms"]],
        [],
        request.thresholds,
        reaction_pairs=pairs,
    )
    analysis = analyze(request.workdir, request.thresholds, contract["reaction_atoms"])
    binding = validate_path_binding(request.workdir, contract)
    reviewed, review = validate_path_review(
        request.path_review or request.workdir / "path_review.json",
        request.workdir / "path_generation_report.json",
    )
    analysis.update(
        contract_sha256=contract["contract_sha256"],
        atom_map_sha256=contract["atom_map_sha256"],
        compatibility_sha256=contract["compatibility_sha256"],
        path_binding=binding,
        path_binding_valid=binding["valid"],
        geometry_validated=geometry["status"] == "PASS",
        path_reviewed=reviewed,
        path_stage_valid=bool(
            analysis["technically_converged"]
            and binding["valid"]
            and geometry["status"] in {"PASS", "REVIEW"}
            and reviewed
        ),
        scientifically_valid=False,
        transition_state_validated=False,
        scientific_validity_scope="path_stage_only_requires_later_source_method_ts_validation",
        path_review=review,
    )
    write_json(request.workdir / "neb_analysis.json", analysis)
    thresholds = yaml.safe_load(request.thresholds.read_text(encoding="utf-8"))
    quality = _path_quality(request, contract, analysis)
    preflight = load_json_object(request.preflight, "submission preflight") if request.preflight else {}
    validation = load_json_object(request.validation, "TS validation") if request.validation else {}
    scheduler = load_json_object(request.scheduler, "scheduler evidence") if request.scheduler else {}
    decision = decide_search(
        geometry,
        analysis,
        thresholds,
        _incar_has_climb(request.workdir),
        reviewed,
        quality,
        preflight,
        validation,
        scheduler,
    )
    _write_search_decision(request.workdir, decision)
    print(decision["DECISION"])
    return decision
def _path_quality(
    request: AnalyzeRequest,
    contract: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    if analysis["status"] == "NO_OUTPUT":
        return {}
    coordinates = contract.get("reaction_coordinates", [])
    primary = next((item for item in coordinates if item["role"] == "primary"), None)
    if primary is None:
        return {
            "PATH_QUALITY_STATUS": "INVALID_ENDPOINTS",
            "REASON_CODES": ["PRIMARY_REACTION_COORDINATE_MISSING"],
            "CRITICAL_IMAGES": [],
        }
    quality_path = request.quality_thresholds
    if not quality_path.is_absolute():
        quality_path = Path(__file__).resolve().parents[2] / quality_path
    report = build_path_quality_report(
        PathQualityRequest(
            workdir=request.workdir,
            reaction_pair=tuple(primary["atoms"]),
            important_interval=tuple(primary["important_interval_A"]),
            quality_thresholds=quality_path,
            geometry_thresholds=request.thresholds,
            monitor={},
            configured_nelm=analysis.get("configured_nelm") or 60,
        )
    )
    write_json(request.workdir / "neb_path_quality.json", report)
    return report
def _incar_has_climb(workdir: Path) -> bool:
    path = workdir / "INCAR"
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].replace(" ", "").upper()
        if clean.startswith("LCLIMB="):
            return clean.split("=", 1)[1] in {".TRUE.", "TRUE", "T"}
    return False


def _write_search_decision(workdir: Path, decision: dict[str, Any]) -> None:
    write_json(workdir / "ts_search_decision.json", decision)
