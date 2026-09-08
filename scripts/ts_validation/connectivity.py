from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from scripts.adsmind_lite.adsmind_common import load_yaml, require_ase_structure
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.artifact_io import sha256_file, write_json
from scripts.neb_agent.utils_structure import (
    Poscar,
    compatible,
    displacement_cart,
    pbc_distance,
    read_poscar,
)
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.path_evidence import load_json_object
from scripts.vasp_result_gate import validate_lsf_done_evidence, validate_vasp_relaxation


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_THRESHOLDS = ROOT / "configs" / "ts_connectivity_gate.yaml"
STRUCTURE_PURPOSE_CONFIG = ROOT / "configs" / "structure_purpose_routing.yaml"


def _load_thresholds(path: Path | None = None) -> dict[str, Any]:
    values = yaml.safe_load((path or DEFAULT_THRESHOLDS).read_text(encoding="utf-8"))
    if not isinstance(values, dict) or values.get("unresolved_policy") != "manual_review":
        raise ValueError("invalid TS connectivity thresholds")
    return values


def _connectivity_edge_policy() -> tuple[float, float]:
    config = load_yaml(STRUCTURE_PURPOSE_CONFIG)
    defaults = config.get("endpoint_validation", {}).get("defaults", {})
    try:
        scale = float(defaults["covalent_radius_scale"])
        minimum = float(defaults["minimum_bond_distance_A"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("endpoint connectivity thresholds are unavailable") from exc
    if scale <= 0 or minimum <= 0:
        raise ValueError("endpoint connectivity thresholds must be positive")
    return scale, minimum


def _changed_pairs(contract: dict[str, Any]) -> list[tuple[int, int, str]]:
    pairs = [(left, right, "break") for left, right in contract.get("broken_bonds", [])]
    pairs.extend((left, right, "form") for left, right in contract.get("formed_bonds", []))
    return pairs


def _reaction_domain(contract: dict[str, Any]) -> list[int]:
    indices = set(contract.get("reaction_atoms", []))
    indices.update(index for pair in _changed_pairs(contract) for index in pair[:2])
    for coordinate in contract.get("reaction_coordinates", []):
        indices.update(coordinate.get("atoms", []))
    return sorted(indices)


def _fragment_composition(
    labels: list[str], domain: list[int], edges: set[tuple[int, int]]
) -> list[list[list[Any]]]:
    neighbors = {index: set() for index in domain}
    for left, right in edges:
        if left in neighbors and right in neighbors:
            neighbors[left].add(right)
            neighbors[right].add(left)
    remaining = set(domain)
    fragments: list[list[list[Any]]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            found = neighbors[stack.pop()] & remaining
            remaining.difference_update(found)
            component.update(found)
            stack.extend(found)
        counts = Counter(labels[index] for index in component)
        fragments.append([[symbol, count] for symbol, count in sorted(counts.items())])
    return sorted(fragments)


def _numeric_descriptors(
    structure: Poscar, contract: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    descriptors: dict[str, dict[str, Any]] = {}
    changed_pairs: set[tuple[int, int]] = set()
    for left, right, change in _changed_pairs(contract):
        pair = (min(left, right), max(left, right))
        changed_pairs.add(pair)
        key = f"bond:{pair[0]}-{pair[1]}:{change}"
        descriptors[key] = {
            "kind": "distance",
            "source": "changed_bond",
            "atoms_zero_based": [left, right],
            "change": change,
            "value_A": pbc_distance(structure, left, right),
        }
    for coordinate in contract.get("reaction_coordinates", []):
        if coordinate.get("kind") != "distance" or len(coordinate.get("atoms", [])) != 2:
            continue
        left, right = coordinate["atoms"]
        if (min(left, right), max(left, right)) in changed_pairs:
            continue
        key = f"coordinate:{coordinate.get('name', '')}:{min(left, right)}-{max(left, right)}"
        descriptors.setdefault(
            key,
            {
                "kind": "distance",
                "source": "reaction_coordinate",
                "atoms_zero_based": [left, right],
                "value_A": pbc_distance(structure, left, right),
            },
        )
    return descriptors


def classify_state(structure_path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    """Build a generic, contract-scoped state signature from existing analyzers."""

    try:
        structure = read_poscar(structure_path)
        domain = _reaction_domain(contract)
        if not domain or any(index < 0 or index >= structure.atom_count for index in domain):
            raise ValueError("reaction domain is missing or outside the structure")
        atoms = require_ase_structure(structure_path)
        scale, minimum = _connectivity_edge_policy()
        all_edges = {
            tuple(sorted(edge))
            for edge in connectivity_edges(
                atoms,
                list(range(structure.atom_count)),
                scale,
                minimum,
            )
        }
        domain_set = set(domain)
        domain_edges = {
            edge for edge in all_edges if edge[0] in domain_set and edge[1] in domain_set
        }
        local_coordination = []
        for index in domain:
            outside_neighbors = []
            for left, right in all_edges:
                if left == index and right not in domain_set:
                    outside_neighbors.append(structure.labels[right])
                elif right == index and left not in domain_set:
                    outside_neighbors.append(structure.labels[left])
            counts = Counter(outside_neighbors)
            local_coordination.append(
                {
                    "atom_index_zero_based": index,
                    "element": structure.labels[index],
                    "neighbor_elements": [[symbol, count] for symbol, count in sorted(counts.items())],
                }
            )
        descriptor_gaps: list[str] = []
        if contract.get("site_changes") and not local_coordination:
            descriptor_gaps.append("site_change_classifier_unavailable")
        return {
            "status": "AVAILABLE",
            "structure": str(structure_path.resolve()),
            "composition": [[symbol, count] for symbol, count in sorted(Counter(structure.labels).items())],
            "reaction_domain_atoms_zero_based": domain,
            "reaction_domain_topology": [list(edge) for edge in sorted(domain_edges)],
            "fragment_composition": _fragment_composition(structure.labels, domain, domain_edges),
            "local_coordination": local_coordination,
            "numeric_descriptors": _numeric_descriptors(structure, contract),
            "descriptor_gaps": descriptor_gaps,
            "connectivity_method": "existing_covalent_radii_connectivity_edges",
        }
    except (OSError, ValueError, IndexError) as exc:
        return {
            "status": "UNAVAILABLE",
            "structure": str(structure_path.resolve()),
            "reason": str(exc),
        }


def _numeric_state_evidence(
    candidate: dict[str, Any],
    reference_is: dict[str, Any],
    reference_fs: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    is_score = 0.0
    fs_score = 0.0
    for key in sorted(
        set(candidate.get("numeric_descriptors", {}))
        & set(reference_is.get("numeric_descriptors", {}))
        & set(reference_fs.get("numeric_descriptors", {}))
    ):
        value = candidate["numeric_descriptors"][key]
        initial = reference_is["numeric_descriptors"][key]
        final = reference_fs["numeric_descriptors"][key]
        separation = abs(float(final["value_A"]) - float(initial["value_A"]))
        if separation < float(thresholds["minimum_endpoint_pair_separation_A"]):
            continue
        normalized_is = abs(float(value["value_A"]) - float(initial["value_A"])) / separation
        normalized_fs = abs(float(value["value_A"]) - float(final["value_A"])) / separation
        is_score += normalized_is
        fs_score += normalized_fs
        rows.append(
            {
                "descriptor": key,
                "source": value["source"],
                "atoms_1based": [index + 1 for index in value["atoms_zero_based"]],
                "change": value.get("change"),
                "is_distance_A": float(initial["value_A"]),
                "fs_distance_A": float(final["value_A"]),
                "branch_distance_A": float(value["value_A"]),
                "normalized_is_error": normalized_is,
                "normalized_fs_error": normalized_fs,
            }
        )
    if not rows:
        return {"status": "NOT_APPLICABLE", "rows": [], "assigned_state": None}
    is_score /= len(rows)
    fs_score /= len(rows)
    margin = abs(is_score - fs_score)
    assigned = None
    if margin >= float(thresholds["minimum_normalized_score_margin"]):
        assigned = "IS" if is_score < fs_score else "FS"
    return {
        "status": "MATCHED" if assigned else "AMBIGUOUS",
        "rows": rows,
        "is_score": is_score,
        "fs_score": fs_score,
        "score_margin": margin,
        "assigned_state": assigned,
    }


def _categorical_state_label(
    candidate_value: Any, is_value: Any, fs_value: Any
) -> str | None:
    if is_value == fs_value:
        return None
    if candidate_value == is_value:
        return "IS"
    if candidate_value == fs_value:
        return "FS"
    return "NO_MATCH"


def _match_state_signature(
    candidate: dict[str, Any],
    reference_is: dict[str, Any],
    reference_fs: dict[str, Any],
    contract: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    if any(
        signature.get("status") != "AVAILABLE"
        for signature in (candidate, reference_is, reference_fs)
    ):
        return {
            "status": "UNRESOLVED",
            "state_class": "UNRESOLVED",
            "reason_codes": ["STATE_SIGNATURE_UNAVAILABLE"],
        }
    if candidate["composition"] != reference_is["composition"] or candidate["composition"] != reference_fs["composition"]:
        return {
            "status": "NO_MATCH",
            "state_class": "OTHER",
            "reason_codes": ["ELEMENT_COMPOSITION_MISMATCH"],
        }

    numeric = _numeric_state_evidence(candidate, reference_is, reference_fs, thresholds)
    labels: list[str] = []
    ambiguous = False
    if numeric["status"] == "MATCHED":
        labels.append(str(numeric["assigned_state"]))
    elif numeric["status"] == "AMBIGUOUS":
        ambiguous = True

    reaction_graph = {
        "topology": candidate["reaction_domain_topology"],
        "fragments": candidate["fragment_composition"],
    }
    is_graph = {
        "topology": reference_is["reaction_domain_topology"],
        "fragments": reference_is["fragment_composition"],
    }
    fs_graph = {
        "topology": reference_fs["reaction_domain_topology"],
        "fragments": reference_fs["fragment_composition"],
    }
    graph_label = _categorical_state_label(reaction_graph, is_graph, fs_graph)
    if graph_label:
        labels.append(graph_label)

    # Site/local coordination is state-defining only when the contract declares a
    # site change and no bond or numeric reaction-coordinate descriptor can do so.
    if not _changed_pairs(contract) and numeric["status"] == "NOT_APPLICABLE" and contract.get("site_changes"):
        coordination_label = _categorical_state_label(
            candidate["local_coordination"],
            reference_is["local_coordination"],
            reference_fs["local_coordination"],
        )
        if coordination_label:
            labels.append(coordination_label)

    if "NO_MATCH" in labels:
        return {
            "status": "NO_MATCH",
            "state_class": "OTHER",
            "reason_codes": ["STATE_SIGNATURE_MATCHES_NEITHER_REFERENCE"],
            "numeric_evidence": numeric,
        }
    matched = {label for label in labels if label in {"IS", "FS"}}
    if len(matched) == 1:
        return {
            "status": "MATCHED",
            "state_class": matched.pop(),
            "reason_codes": [],
            "numeric_evidence": numeric,
        }
    reason = "CONFLICTING_STATE_DESCRIPTORS" if len(matched) > 1 else "REFERENCE_STATE_DESCRIPTORS_INSUFFICIENT"
    if ambiguous and not matched:
        reason = "STATE_DESCRIPTOR_MARGIN_AMBIGUOUS"
    return {
        "status": "UNRESOLVED",
        "state_class": "UNRESOLVED",
        "reason_codes": [reason],
        "numeric_evidence": numeric,
    }


def state_matches(classification: dict[str, Any], reference_state: str) -> bool:
    return bool(
        classification.get("status") == "MATCHED"
        and classification.get("state_class") == reference_state
    )


def _endpoint_match(
    structure: Poscar,
    target: Poscar,
    other: Poscar,
    target_state: str,
    signature: dict[str, Any],
    target_signature: dict[str, Any],
    contract: dict[str, Any],
    numeric_rows: list[dict[str, Any]],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    reaction_indices = list(contract["reaction_atoms"])
    target_displacements = [
        float(np.linalg.norm(displacement_cart(target, target.frac[index], structure.frac[index])))
        for index in reaction_indices
    ]
    other_displacements = [
        float(np.linalg.norm(displacement_cart(other, other.frac[index], structure.frac[index])))
        for index in reaction_indices
    ]
    target_rmsd = float(np.sqrt(np.mean(np.square(target_displacements))))
    other_rmsd = float(np.sqrt(np.mean(np.square(other_displacements))))
    fixed_indices = [
        index
        for index, flags in enumerate(target.flags)
        if target.selective and tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]
    fixed_max = max(
        (
            float(np.linalg.norm(displacement_cart(target, target.frac[index], structure.frac[index])))
            for index in fixed_indices
        ),
        default=0.0,
    )
    target_label = target_state.lower()
    changed_rows = [row for row in numeric_rows if row["source"] == "changed_bond"]
    maximum_deviation = max(
        (
            abs(
                row["branch_distance_A"]
                - (row["is_distance_A"] if target_label == "is" else row["fs_distance_A"])
            )
            for row in changed_rows
        ),
        default=0.0,
    )
    geometry_checks = {
        "reaction_atom_rmsd": target_rmsd <= float(thresholds["reaction_atom_rmsd_A_max"]),
        "reaction_atom_max_displacement": max(target_displacements)
        <= float(thresholds["reaction_atom_max_displacement_A"]),
        "reaction_atom_endpoint_margin": other_rmsd - target_rmsd
        >= float(thresholds["reaction_atom_endpoint_margin_A_min"]),
        "changed_bond_local_geometry": maximum_deviation
        <= float(thresholds["changed_bond_endpoint_tolerance_A"]),
        "fixed_atom_drift": fixed_max <= float(thresholds["fixed_atom_max_displacement_A"]),
    }
    same_environment = bool(
        signature.get("reaction_domain_topology") == target_signature.get("reaction_domain_topology")
        and signature.get("fragment_composition") == target_signature.get("fragment_composition")
        and signature.get("local_coordination") == target_signature.get("local_coordination")
    )
    if all(geometry_checks.values()) and same_environment:
        status = "EXACT"
    elif not same_environment:
        status = "DIFFERENT_LOCAL_MINIMUM"
    else:
        status = "UNRESOLVED"
    return {
        "status": status,
        "review_required": status == "UNRESOLVED",
        "symmetry_evaluation": "NOT_IMPLEMENTED",
        "target_reaction_atom_rmsd_A": target_rmsd,
        "other_endpoint_reaction_atom_rmsd_A": other_rmsd,
        "maximum_target_reaction_atom_displacement_A": max(target_displacements),
        "maximum_fixed_atom_displacement_A": fixed_max,
        "maximum_changed_bond_deviation_A": maximum_deviation,
        "local_environment_matches_reference": same_environment,
        "geometry_checks": geometry_checks,
    }


def _classify_structure(
    structure_path: Path,
    initial_path: Path,
    final_path: Path,
    contract: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
    *,
    reference_is_state: dict[str, Any] | None = None,
    reference_fs_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or _load_thresholds()
    structure = read_poscar(structure_path)
    initial = read_poscar(initial_path)
    final = read_poscar(final_path)
    errors = compatible(initial, final) + compatible(initial, structure)
    if errors:
        raise ValueError("connectivity structure incompatibility: " + ", ".join(errors))
    signature = classify_state(structure_path, contract)
    is_signature = reference_is_state or classify_state(initial_path, contract)
    fs_signature = reference_fs_state or classify_state(final_path, contract)
    state_classification = _match_state_signature(
        signature, is_signature, fs_signature, contract, thresholds
    )
    numeric = state_classification.get("numeric_evidence") or _numeric_state_evidence(
        signature, is_signature, fs_signature, thresholds
    )
    assigned = state_classification.get("state_class")
    endpoint = {
        "status": "NOT_EVALUATED",
        "review_required": False,
        "symmetry_evaluation": "NOT_IMPLEMENTED",
    }
    if assigned in {"IS", "FS"}:
        target = initial if assigned == "IS" else final
        other = final if assigned == "IS" else initial
        target_signature = is_signature if assigned == "IS" else fs_signature
        endpoint = _endpoint_match(
            structure,
            target,
            other,
            assigned,
            signature,
            target_signature,
            contract,
            numeric.get("rows", []),
            thresholds,
        )
    changed_rows = [row for row in numeric.get("rows", []) if row["source"] == "changed_bond"]
    return {
        "assigned_endpoint": assigned if assigned in {"IS", "FS"} else "UNRESOLVED",
        "state_signature": signature,
        "state_classification": state_classification,
        "is_score": numeric.get("is_score"),
        "fs_score": numeric.get("fs_score"),
        "score_margin": numeric.get("score_margin"),
        "changed_bonds": changed_rows,
        "reaction_atom_indices_zero_based": list(contract["reaction_atoms"]),
        "target_reaction_atom_rmsd_A": endpoint.get("target_reaction_atom_rmsd_A"),
        "other_endpoint_reaction_atom_rmsd_A": endpoint.get("other_endpoint_reaction_atom_rmsd_A"),
        "maximum_target_reaction_atom_displacement_A": endpoint.get("maximum_target_reaction_atom_displacement_A"),
        "maximum_fixed_atom_displacement_A": endpoint.get("maximum_fixed_atom_displacement_A"),
        "maximum_changed_bond_deviation_A": endpoint.get("maximum_changed_bond_deviation_A"),
        "geometry_checks": endpoint.get("geometry_checks", {}),
        "endpoint_match": endpoint["status"],
        "endpoint_match_review_required": endpoint["review_required"],
        "endpoint_match_details": endpoint,
        "classification_passed": state_classification.get("status") == "MATCHED",
    }


def _branch(
    label: str,
    run_directory: Path,
    displacement_path: Path,
    scheduler_path: Path,
    initial_path: Path,
    final_path: Path,
    contract: dict[str, Any],
    thresholds: dict[str, Any],
    reference_is_state: dict[str, Any],
    reference_fs_state: dict[str, Any],
) -> dict[str, Any]:
    scheduler = load_json_object(scheduler_path, f"{label} scheduler evidence")
    validate_lsf_done_evidence(scheduler)
    if sha256_file(run_directory / "POSCAR") != sha256_file(displacement_path):
        raise ValueError(f"{label} VASP POSCAR is not the reviewed mode displacement")
    result_gate = validate_vasp_relaxation(run_directory)
    classification = _classify_structure(
        run_directory / "CONTCAR",
        initial_path,
        final_path,
        contract,
        thresholds,
        reference_is_state=reference_is_state,
        reference_fs_state=reference_fs_state,
    )
    return {
        "direction": label,
        "run_directory": str(run_directory.resolve()),
        "job_id": str(scheduler["job_id"]),
        "scheduler_evidence": {"path": str(scheduler_path.resolve()), "sha256": sha256_file(scheduler_path)},
        "displacement": {"path": str(displacement_path.resolve()), "sha256": sha256_file(displacement_path)},
        "final_structure": {
            "path": str((run_directory / "CONTCAR").resolve()),
            "sha256": sha256_file(run_directory / "CONTCAR"),
        },
        "outcar_sha256": sha256_file(run_directory / "OUTCAR"),
        "oszicar_sha256": sha256_file(run_directory / "OSZICAR"),
        "result_gate": result_gate,
        "classification": classification,
    }


def _evaluate_reaction_connectivity(branches: list[dict[str, Any]]) -> dict[str, Any]:
    by_direction = {branch["direction"]: branch for branch in branches}
    if set(by_direction) != {"positive", "negative"}:
        return {
            "reaction_connectivity": "UNRESOLVED",
            "direct_match": False,
            "reverse_match": False,
            "direction_assignment": {},
            "reason_codes": ["BIDIRECTIONAL_BRANCH_SET_INCOMPLETE"],
        }
    if any(
        branch.get("result_gate", {}).get("electronically_converged") is not True
        or branch.get("result_gate", {}).get("ionic_converged") is not True
        for branch in branches
    ):
        return {
            "reaction_connectivity": "UNRESOLVED",
            "direct_match": False,
            "reverse_match": False,
            "direction_assignment": {},
            "reason_codes": ["BRANCH_NOT_CONVERGED"],
        }
    positive = by_direction["positive"]["classification"]["state_classification"]
    negative = by_direction["negative"]["classification"]["state_classification"]
    if any(value.get("status") == "UNRESOLVED" for value in (positive, negative)):
        return {
            "reaction_connectivity": "UNRESOLVED",
            "direct_match": False,
            "reverse_match": False,
            "direction_assignment": {},
            "reason_codes": ["STATE_CLASSIFICATION_AMBIGUOUS_OR_UNAVAILABLE"],
        }
    direct = state_matches(positive, "IS") and state_matches(negative, "FS")
    reverse = state_matches(positive, "FS") and state_matches(negative, "IS")
    if direct or reverse:
        return {
            "reaction_connectivity": "PASS",
            "direct_match": direct,
            "reverse_match": reverse,
            "direction_assignment": (
                {"positive": "IS", "negative": "FS"}
                if direct
                else {"positive": "FS", "negative": "IS"}
            ),
            "reason_codes": [],
        }
    same_state = bool(
        positive.get("status") == "MATCHED"
        and negative.get("status") == "MATCHED"
        and positive.get("state_class") == negative.get("state_class")
    )
    return {
        "reaction_connectivity": "FAIL",
        "direct_match": False,
        "reverse_match": False,
        "direction_assignment": {},
        "reason_codes": [
            "BOTH_BRANCHES_REACHED_SAME_STATE"
            if same_state
            else "BRANCH_STATES_DO_NOT_MATCH_EXPECTED_IS_FS"
        ],
    }


def _aggregate_endpoint_match(
    branches: list[dict[str, Any]], reaction_connectivity: str
) -> tuple[str, dict[str, str]]:
    if reaction_connectivity != "PASS":
        return "NOT_EVALUATED", {
            branch["direction"]: "NOT_EVALUATED" for branch in branches
        }
    details = {
        branch["direction"]: branch["classification"]["endpoint_match"]
        for branch in branches
    }
    values = set(details.values())
    if "UNRESOLVED" in values or "NOT_EVALUATED" in values:
        return "UNRESOLVED", details
    if "DIFFERENT_LOCAL_MINIMUM" in values:
        return "DIFFERENT_LOCAL_MINIMUM", details
    if values <= {"EXACT", "SYMMETRY_EQUIVALENT"}:
        return (
            "SYMMETRY_EQUIVALENT" if "SYMMETRY_EQUIVALENT" in values else "EXACT",
            details,
        )
    return "UNRESOLVED", details


def _overall_status(reaction_connectivity: str, endpoint_match: str) -> str:
    if reaction_connectivity == "FAIL":
        return "REJECTED"
    if reaction_connectivity == "UNRESOLVED":
        return "UNRESOLVED"
    if endpoint_match in {"EXACT", "SYMMETRY_EQUIVALENT"}:
        return "VALIDATED"
    if endpoint_match == "DIFFERENT_LOCAL_MINIMUM":
        return "VALIDATED_DIFFERENT_ENDPOINT"
    return "NEEDS_REVIEW"


def _report_summary(reaction_connectivity: str, endpoint_match: str) -> str:
    if reaction_connectivity == "PASS" and endpoint_match == "UNRESOLVED":
        return (
            "TS 两侧分别连接预期的 IS 和 FS 状态类别，因此反应连通性通过。"
            "实际端点与参考端点是否属于同一个局部极小值尚未确认，"
            "需要进一步检查周期等价性、局部配位或结构对称性。"
        )
    if reaction_connectivity == "PASS":
        return "TS 两侧分别连接预期的 IS 和 FS 状态类别，反应连通性通过。"
    if reaction_connectivity == "FAIL":
        return "TS 两侧未连接到一对预期的 IS 和 FS 状态类别，反应连通性失败。"
    return "现有收敛或状态描述符证据不足，反应连通性未能解析。"


def analyze_bidirectional_connectivity(
    *,
    contract_path: Path,
    initial_path: Path,
    final_path: Path,
    saddle_path: Path,
    frequency_outcar: Path,
    positive_run: Path,
    positive_displacement: Path,
    positive_scheduler: Path,
    negative_run: Path,
    negative_displacement: Path,
    negative_scheduler: Path,
    output: Path,
    thresholds_path: Path | None = None,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    thresholds = _load_thresholds(thresholds_path)
    frequency_poscar = frequency_outcar.parent / "POSCAR"
    if not frequency_poscar.is_file():
        raise ValueError("frequency calculation POSCAR is missing")
    reference_is_state = classify_state(initial_path, contract)
    reference_fs_state = classify_state(final_path, contract)
    branches = [
        _branch(
            "positive",
            positive_run,
            positive_displacement,
            positive_scheduler,
            initial_path,
            final_path,
            contract,
            thresholds,
            reference_is_state,
            reference_fs_state,
        ),
        _branch(
            "negative",
            negative_run,
            negative_displacement,
            negative_scheduler,
            initial_path,
            final_path,
            contract,
            thresholds,
            reference_is_state,
            reference_fs_state,
        ),
    ]
    reaction = _evaluate_reaction_connectivity(branches)
    reaction_connectivity = reaction["reaction_connectivity"]
    endpoint_match, endpoint_details = _aggregate_endpoint_match(
        branches, reaction_connectivity
    )
    overall_status = _overall_status(reaction_connectivity, endpoint_match)
    legacy_status = (
        "PASS"
        if reaction_connectivity == "PASS"
        else "FAIL"
        if reaction_connectivity == "FAIL"
        else "NEEDS_REVIEW"
    )
    grade_a_eligible = bool(overall_status == "VALIDATED")
    payload = {
        "schema_version": 2,
        "document_kind": "vasp_bidirectional_ts_connectivity",
        "status": legacy_status,
        "reaction_connectivity": reaction_connectivity,
        "endpoint_match": endpoint_match,
        "endpoint_match_details": endpoint_details,
        "overall_status": overall_status,
        "summary": _report_summary(reaction_connectivity, endpoint_match),
        "direct_match": reaction["direct_match"],
        "reverse_match": reaction["reverse_match"],
        "direction_assignment": reaction["direction_assignment"],
        "reason_codes": reaction["reason_codes"],
        "reaction_id": contract["reaction_id"],
        "contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility_sha256": contract["compatibility_sha256"],
        "source_saddle": {"path": str(saddle_path.resolve()), "sha256": sha256_file(saddle_path)},
        "frequency_poscar": {
            "path": str(frequency_poscar.resolve()),
            "sha256": sha256_file(frequency_poscar),
        },
        "frequency_outcar": {"path": str(frequency_outcar.resolve()), "sha256": sha256_file(frequency_outcar)},
        "initial_endpoint": {"path": str(initial_path.resolve()), "sha256": sha256_file(initial_path)},
        "final_endpoint": {"path": str(final_path.resolve()), "sha256": sha256_file(final_path)},
        "reference_state_signatures": {
            "IS": reference_is_state,
            "FS": reference_fs_state,
        },
        "branches": branches,
        "connects_to_is": reaction_connectivity == "PASS",
        "connects_to_fs": reaction_connectivity == "PASS",
        "grade_a_connectivity_eligible": grade_a_eligible,
        "thresholds": thresholds,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, payload)
    return payload
