from __future__ import annotations

from scripts.runtime_resources import resource_path

import argparse
import math
import re
from pathlib import Path

from scripts.scientific_validation import finite_number, validate_finite_tree
from typing import Any

import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.neb_agent.utils_report import write_json
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.ts_validation.dimer_frequency_gate import evaluate_dimer_frequency_gate


FREQUENCY_PATTERN = re.compile(r"^\s*(\d+)\s+f(/i)?\s*=.*?([-+0-9.]+)\s+cm-1", re.I)
DEFAULT_PROFILE = resource_path('configs/true_fe110_production.yaml')


def _frequency_policy(override: dict[str, Any] | None) -> dict[str, Any]:
    if override is not None:
        validate_finite_tree(override, "frequency policy")
        return override
    profile = yaml.safe_load(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    policy = profile["transition_state"]["vfa"]["validation"]
    validate_finite_tree(policy, "frequency policy")
    return policy


def _frequency_modes(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    modes: list[dict[str, Any]] = []
    for position, line in enumerate(lines):
        if "cm-1" in line:
            validate_finite_tree(line.split(), "frequency row")
        match = FREQUENCY_PATTERN.search(line)
        if not match:
            continue
        vectors: list[dict[str, float | int]] = []
        for candidate in lines[position + 1 :]:
            if FREQUENCY_PATTERN.search(candidate):
                break
            fields = candidate.split()
            atom_index: int | None = None
            vector_fields: list[str] = []
            if len(fields) >= 7 and fields[0].isdigit():
                atom_index = int(fields[0]) - 1
                vector_fields = fields[-3:]
            elif len(fields) == 6:
                # Real VASP OUTCAR frequency rows contain X Y Z dx dy dz and
                # no explicit atom index. Their row order is the atom order.
                atom_index = len(vectors)
                vector_fields = fields[-3:]
            if atom_index is not None:
                validate_finite_tree(vector_fields, "frequency eigenvector")
                try:
                    dx, dy, dz = (finite_number(value, "frequency eigenvector") for value in vector_fields)
                except ValueError:
                    continue
                vectors.append(
                    {
                        "atom_index_zero_based": atom_index,
                        "dx": dx,
                        "dy": dy,
                        "dz": dz,
                        "amplitude": math.sqrt(dx * dx + dy * dy + dz * dz),
                    }
                )
                continue
            if vectors:
                break
        modes.append(
            {
                "mode_index": int(match.group(1)),
                "imaginary": bool(match.group(2)),
                "frequency_cm1": finite_number(match.group(3), "frequency cm-1"),
                "dominant_atoms": sorted(vectors, key=lambda item: float(item["amplitude"]), reverse=True)[:10],
            }
        )
    return modes


def _review(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return load_json_object(path)


def _bound_vfa_handoff(
    review: dict[str, Any], review_root: Path, workdir: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    value = review.get("vfa_handoff")
    if not value:
        return {}
    path = Path(value)
    if not path.is_absolute():
        path = review_root / path
    if not path.is_file() or review.get("vfa_handoff_sha256") != sha256_file(path):
        return {}
    payload = load_json_object(path)
    frequency_poscar = workdir / "POSCAR"
    if (
        any(
            payload.get(key) != contract[key]
            for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
        )
        or len(str(payload.get("source_sha256", ""))) != 64
        or not frequency_poscar.is_file()
        or payload.get("frequency_poscar_sha256") != sha256_file(frequency_poscar)
    ):
        return {}
    saddle_analysis = _resolve_bound_path(
        payload.get("saddle_analysis_source"), path.parent
    )
    if (
        saddle_analysis is None
        or not saddle_analysis.is_file()
        or payload.get("saddle_analysis_sha256") != sha256_file(saddle_analysis)
    ):
        return {}
    saddle_payload = load_json_object(saddle_analysis)
    source_method = str(payload.get("source_method", "")).lower()
    dimer_frequency_acceptance = None
    dimer_technical_acceptance = None
    if source_method == "dimer":
        source_structure = _resolve_bound_path(
            payload.get("source_ts_candidate"), path.parent
        )
        if (
            source_structure is None
            or not source_structure.is_file()
            or payload.get("source_sha256") != sha256_file(source_structure)
        ):
            return {}
        from scripts.ts_validation.prepare_vfa_from_ts_image import same_vfa_geometry

        final_structure = _resolve_bound_path(saddle_payload.get("final_structure"), saddle_analysis.parent)
        if (
            final_structure is None or final_structure.resolve() != source_structure.resolve()
            or any(saddle_payload.get(key) != contract[key] for key in (
                "contract_sha256", "atom_map_sha256", "compatibility_sha256",
            ))
            or not same_vfa_geometry(source_structure, frequency_poscar)
        ):
            return {}
        embedded_gate = payload.get("dimer_frequency_gate") or {}
        soft_review_path = embedded_gate.get("manual_review_path")
        resolved_review = Path(str(soft_review_path)) if soft_review_path else None
        if resolved_review is not None and not resolved_review.is_absolute():
            resolved_review = path.parent / resolved_review
        gate = evaluate_dimer_frequency_gate(
            saddle_payload,
            saddle_analysis,
            source_structure,
            resolved_review,
        )
        dimer_frequency_acceptance = gate["frequency_handoff_allowed"]
        dimer_technical_acceptance = gate["ts_validation_eligible"]
        if not dimer_frequency_acceptance:
            return {}
        payload["_dimer_frequency_gate"] = gate
    payload["_dimer_technical_acceptance"] = (
        dimer_technical_acceptance if source_method == "dimer" else None
    )
    payload["_dimer_frequency_handoff_acceptance"] = (
        dimer_frequency_acceptance if source_method == "dimer" else None
    )
    from scripts.ts_validation.prepare_vfa_from_ts_image import vfa_scope_checks

    try:
        if not all(vfa_scope_checks(workdir, path).values()):
            return {}
    except (OSError, ValueError, TypeError):
        return {}
    payload["_evidence_path"] = str(path.resolve())
    payload["_evidence_sha256"] = sha256_file(path)
    return payload


def _resolve_bound_path(value: Any, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return path if path.is_file() else root / path


def _connectivity_report(
    review: dict[str, Any],
    review_root: Path,
    workdir: Path,
    outcar_path: Path,
    contract: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    value = review.get("connectivity_report")
    if not value:
        return {}
    path = Path(value)
    if not path.is_absolute():
        path = review_root / path
    if not path.is_file():
        return {}
    expected_sha = review.get("connectivity_report_sha256")
    actual_sha = sha256_file(path)
    if expected_sha != actual_sha:
        return {}
    payload = load_json_object(path)
    bound = all(
        payload.get(key) == contract[key]
        for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
    )
    frequency = payload.get("frequency_outcar") or {}
    frequency_bound = outcar_path.is_file() and frequency.get("sha256") == sha256_file(outcar_path)
    frequency_poscar = payload.get("frequency_poscar") or {}
    frequency_poscar_path = workdir / "POSCAR"
    saddle = payload.get("source_saddle") or {}
    saddle_path = Path(str(saddle.get("path", "")))
    if not saddle_path.is_absolute():
        saddle_path = path.parent / saddle_path
    structure_bound = bool(
        handoff
        and saddle_path.is_file()
        and saddle.get("sha256") == sha256_file(saddle_path)
        and saddle.get("sha256") == handoff.get("source_sha256")
        and frequency_poscar_path.is_file()
        and frequency_poscar.get("sha256") == sha256_file(frequency_poscar_path)
        and frequency_poscar.get("sha256") == handoff.get("frequency_poscar_sha256")
    )
    if not bound or not frequency_bound or not structure_bound:
        return {}
    payload["_evidence_path"] = str(path.resolve())
    payload["_evidence_sha256"] = actual_sha
    return payload


def analyze_vfa(
    workdir: Path,
    contract: dict[str, Any],
    review_path: Path | None,
    frequency_policy: dict[str, Any] | None = None,
    *, write_output: bool = True,
) -> dict[str, Any]:
    workdir = workdir.resolve()
    review_path = review_path.resolve() if review_path else None
    reaction_indices = contract["reaction_atoms"]
    outcar_path = workdir / "OUTCAR"
    text = outcar_path.read_text(encoding="utf-8", errors="replace") if outcar_path.is_file() else ""
    modes = _frequency_modes(text)
    imaginary = [mode for mode in modes if mode["imaginary"]]
    review = _review(review_path)
    source_method = str(review.get("source_method", "")).lower()
    connectivity_required = source_method != "dimer"
    normal_completion = bool(parse_outcar(outcar_path).get("normal_completion"))
    review_root = review_path.parent if review_path else workdir
    handoff = _bound_vfa_handoff(review, review_root, workdir, contract)
    connectivity = _connectivity_report(
        review, review_root, workdir, outcar_path, contract, handoff
    )
    branches = connectivity.get("branches") or []
    displacement_files = [
        (branch.get("displacement") or {}).get("path")
        for branch in branches
    ]
    displacement_files = (displacement_files + [None, None])[:2]
    resolved_displacements = [
        (Path(value) if Path(value).is_absolute() else review_root / value) if value else None
        for value in displacement_files
    ]
    displacement_files_exist = bool(
        all(value and value.is_file() for value in resolved_displacements)
    )
    principal_mode_index = review.get("principal_mode_index")
    if principal_mode_index is None and len(imaginary) == 1:
        principal_mode_index = imaginary[0]["mode_index"]
    principal_mode = next(
        (mode for mode in imaginary if mode["mode_index"] == principal_mode_index),
        None,
    )
    principal_atoms = {
        int(item["atom_index_zero_based"])
        for item in (principal_mode or {}).get("dominant_atoms", [])
    }
    reaction_overlap = sorted(principal_atoms & set(reaction_indices))
    policy = _frequency_policy(frequency_policy)
    meaningful_min = policy.get("meaningful_imaginary_frequency_min_cm1")
    soft_max = policy.get("additional_soft_mode_abs_max_cm1")
    thresholds_configured = bool(
        isinstance(meaningful_min, (int, float))
        and float(meaningful_min) > 0
        and isinstance(soft_max, (int, float))
        and float(soft_max) > 0
    )
    principal_meaningful = bool(
        thresholds_configured
        and principal_mode
        and abs(float(principal_mode["frequency_cm1"])) >= float(meaningful_min)
    )
    significant_imaginary = (
        [
            mode
            for mode in imaginary
            if abs(float(mode["frequency_cm1"])) >= float(meaningful_min)
        ]
        if thresholds_configured
        else []
    )
    small_soft_modes = (
        [
            mode
            for mode in imaginary
            if abs(float(mode["frequency_cm1"])) <= float(soft_max)
        ]
        if thresholds_configured
        else []
    )
    unresolved_imaginary = (
        [
            mode
            for mode in imaginary
            if float(soft_max)
            < abs(float(mode["frequency_cm1"]))
            < float(meaningful_min)
        ]
        if thresholds_configured
        else []
    )
    review_evidence = bool(
        normal_completion
        and source_method in {"neb", "ci_neb", "dimer"}
        and review.get("mode_assignment") == "accepted"
        and review.get("geometry_status") == "pass"
        and review.get("reviewer")
        and review.get("reviewed_at")
        and review.get("validation_calculation_id")
        and review.get("source_saddle_calculation_id")
        and review.get("source_job_record_id")
        and review.get("frequency_output_file_id")
        and review.get("contract_sha256") == contract["contract_sha256"]
        and review.get("atom_map_sha256") == contract["atom_map_sha256"]
        and review.get("compatibility_sha256") == contract["compatibility_sha256"]
        and handoff
        and reaction_overlap
        and (
            source_method != "dimer"
            or handoff.get("_dimer_technical_acceptance") is True
        )
    )
    common_evidence = bool(review_evidence and thresholds_configured and principal_meaningful)
    connectivity_evidence = bool(
        connectivity.get("status") == "PASS"
        and connectivity.get("grade_a_connectivity_eligible") is True
        and connectivity.get("connects_to_is") is True
        and connectivity.get("connects_to_fs") is True
        and review.get("positive_displacement_file_id")
        and review.get("negative_displacement_file_id")
        and review.get("connectivity_report_file_id")
        and review.get("positive_connectivity_job_record_id")
        and review.get("negative_connectivity_job_record_id")
        and displacement_files_exist
    )
    complete_evidence = bool(
        common_evidence and (not connectivity_required or connectivity_evidence)
    )
    grade_a_review = bool(complete_evidence and review.get("status") == "accepted")
    soft_modes = [
        mode for mode in small_soft_modes if mode["mode_index"] != principal_mode_index
    ]
    soft_modes_within_threshold = bool(
        thresholds_configured
        and all(abs(float(mode["frequency_cm1"])) <= float(soft_max) for mode in soft_modes)
    )
    grade_b_review = bool(
        complete_evidence
        and review.get("status") in {"needs_review", "manual_review"}
        and len(imaginary) == 2
        and len(soft_modes) == 1
        and soft_modes_within_threshold
        and review.get("soft_mode_assessment") == "one_additional_small_soft_mode_repeat_required"
        and review.get("repeat_required") is True
    )
    if not text or not modes or not normal_completion:
        grade = "Ungraded"
    elif not thresholds_configured:
        grade = "Ungraded"
    elif review and review.get("status") == "rejected":
        grade = "C"
    elif len(significant_imaginary) == 0 and not unresolved_imaginary:
        grade = "C"
    elif len(significant_imaginary) > 1:
        grade = "C"
    elif unresolved_imaginary:
        grade = "Ungraded"
    elif len(significant_imaginary) == 1 and len(imaginary) == 1 and grade_a_review:
        grade = "A"
    elif grade_b_review:
        grade = "B"
    else:
        grade = "Ungraded"
    evidence_paths = [outcar_path, workdir / "POSCAR", workdir / "vfa_scope_review.json"]
    evidence_paths.extend(Path(value) for value in (
        review_path, handoff.get("_evidence_path"),
        (handoff.get("_dimer_frequency_gate") or {}).get("manual_review_path"),
    ) if value)
    if frequency_policy is None:
        evidence_paths.append(DEFAULT_PROFILE)
    payload = {
        "scientific_review_bound": bool(review_evidence and review.get("status") == "accepted"),
        "workdir": str(workdir.resolve()),
        "review_path": str(review_path.resolve()) if review_path else None,
        "reaction_contract": contract,
        "frequency_policy": policy,
        "frequency_policy_is_default": frequency_policy is None,
        "source_files": source_file_manifest(evidence_paths),
        "status": "VALIDATED" if grade == "A" else "REJECTED" if grade == "C" else "NEEDS_REVIEW",
        "source_method": review.get("source_method", "Needs confirmation"),
        "validation_basis": (
            "DIMER_CONVERGENCE_AND_VIBRATIONAL_FREQUENCY"
            if source_method == "dimer"
            else "SADDLE_SEARCH_VIBRATION_AND_BIDIRECTIONAL_CONNECTIVITY"
        ),
        "connectivity_required": connectivity_required,
        "validation_calculation_id": review.get("validation_calculation_id"),
        "source_saddle_calculation_id": review.get("source_saddle_calculation_id"),
        "source_job_record_id": review.get("source_job_record_id"),
        "frequency_output_file_id": review.get("frequency_output_file_id"),
        "positive_displacement_file_id": review.get("positive_displacement_file_id"),
        "negative_displacement_file_id": review.get("negative_displacement_file_id"),
        "contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility_sha256": contract["compatibility_sha256"],
        "normal_completion": normal_completion,
        "modes": modes,
        "imaginary_frequency_count": len(imaginary),
        "imaginary_frequencies_cm1": [mode["frequency_cm1"] for mode in imaginary],
        "significant_imaginary_mode_indices": [
            mode["mode_index"] for mode in significant_imaginary
        ],
        "small_soft_mode_indices": [mode["mode_index"] for mode in small_soft_modes],
        "unresolved_imaginary_mode_indices": [
            mode["mode_index"] for mode in unresolved_imaginary
        ],
        "principal_mode_index": principal_mode_index,
        "principal_mode_reaction_atom_overlap": reaction_overlap,
        "frequency_threshold_status": "configured" if thresholds_configured else "needs_confirmation",
        "meaningful_imaginary_frequency_min_cm1": meaningful_min,
        "additional_soft_mode_abs_max_cm1": soft_max,
        "principal_mode_is_meaningful": principal_meaningful,
        "additional_soft_modes_within_threshold": soft_modes_within_threshold,
        "principal_mode_assignment": review.get("mode_assignment", "Needs confirmation"),
        "soft_mode_assessment": review.get("soft_mode_assessment", "Needs confirmation"),
        "repeat_required": bool(review.get("repeat_required")) if grade == "B" else False,
        "geometry_status": review.get("geometry_status", "Needs confirmation"),
        "connectivity_report": connectivity.get("_evidence_path"),
        "connectivity_report_sha256": connectivity.get("_evidence_sha256"),
        "connectivity_report_file_id": review.get("connectivity_report_file_id"),
        "vfa_handoff": handoff.get("_evidence_path"),
        "vfa_handoff_sha256": handoff.get("_evidence_sha256"),
        "source_saddle_sha256": handoff.get("source_sha256"),
        "saddle_analysis_sha256": handoff.get("saddle_analysis_sha256"),
        "dimer_technical_acceptance": handoff.get("_dimer_technical_acceptance"),
        "dimer_frequency_handoff_acceptance": handoff.get(
            "_dimer_frequency_handoff_acceptance"
        ),
        "dimer_soft_gate_review_decision": (
            handoff.get("_dimer_frequency_gate") or {}
        ).get("manual_review_decision"),
        "frequency_poscar_sha256": handoff.get("frequency_poscar_sha256"),
        "positive_connectivity_job_record_id": review.get("positive_connectivity_job_record_id"),
        "negative_connectivity_job_record_id": review.get("negative_connectivity_job_record_id"),
        "connectivity_status": connectivity.get("status", "Needs confirmation"),
        "connectivity_job_ids": [branch.get("job_id") for branch in branches],
        "connects_to_is": connectivity.get("connects_to_is"),
        "connects_to_fs": connectivity.get("connects_to_fs"),
        "positive_displacement_file": str(resolved_displacements[0]) if resolved_displacements[0] else None,
        "negative_displacement_file": str(resolved_displacements[1]) if resolved_displacements[1] else None,
        "displacement_files_exist": displacement_files_exist,
        "grade": grade,
        "kinetic_eligible": grade == "A",
        "reviewer": review.get("reviewer"),
        "reviewed_at": review.get("reviewed_at"),
        "notes": review.get("notes"),
    }
    if write_output:
        write_json(workdir / "vfa_analysis.json", payload)
    return payload


def _require_final_dimer_review(dimer: dict, dimer_path: Path, final: Path, handoff: dict, soft_review_path: Path | None) -> None:
    gate = handoff["_dimer_frequency_gate"]
    embedded = handoff.get("dimer_frequency_gate") or {}
    if embedded.get("manual_review_path"):
        if embedded.get("manual_review_sha256") != gate.get("manual_review_sha256"):
            raise ValueError("VFA soft-review reference is missing or stale")
    if soft_review_path is not None:
        gate = evaluate_dimer_frequency_gate(dimer, dimer_path, final, soft_review_path)
        if not gate["manual_review_accepted"]:
            raise ValueError("DIMER soft review is missing, stale or belongs to another object")
        if embedded.get("manual_review_sha256") != gate["manual_review_sha256"]:
            raise ValueError("Pipeline and VFA use different DIMER soft reviews")
    if not gate["ts_validation_eligible"]:
        raise ValueError("DIMER review permits frequency handoff only")


def _require_dimer_identity(dimer: dict, dimer_path: Path, vfa: dict, handoff: dict, handoff_path: Path, contract: dict) -> Path:
    from scripts.ts_strategy_engine.contract import normalize_contract

    source = _resolve_bound_path(handoff.get("source_ts_candidate"), handoff_path.parent)
    final = _resolve_bound_path(dimer.get("final_structure"), dimer_path.parent)
    if source is None or final is None or source.resolve() != final.resolve():
        raise ValueError("VFA source is not this DIMER final structure")
    if vfa.get("source_saddle_sha256") != sha256_file(final):
        raise ValueError("VFA source saddle content is stale")
    for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256"):
        if any(item.get(key) != contract[key] for item in (dimer, vfa, handoff)):
            raise ValueError(f"DIMER/VFA {key} mismatch")
    if "reaction_contract" in handoff and normalize_contract(handoff["reaction_contract"]) != contract:
        raise ValueError("VFA handoff reaction contract differs from the analyzed contract")
    return final


def validate_dimer_vfa_binding(
    dimer: dict[str, Any], dimer_path: Path, vfa: dict[str, Any],
    vfa_path: Path, workdir: Path | None, soft_review_path: Path | None,
) -> tuple[dict[str, Any], list[Path]]:
    """Verify current evidence and one scientific object before pipeline acceptance.

    Reuse the original parsers/gates in read-only mode; summaries cannot replace
    their inputs. Optional frequency classification remains independent of TS
    acceptance and no connectivity requirement is introduced here.
    """
    from scripts.ts_strategy_engine.contract import normalize_contract
    from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
    from scripts.ts_validation.prepare_vfa_from_ts_image import vfa_scope_checks

    if not source_file_manifest_valid(dimer) or not source_file_manifest_valid(vfa):
        raise ValueError("DIMER/VFA source files are missing or stale; regenerate their analyses")
    contract = normalize_contract(vfa.get("reaction_contract"))
    root = Path(vfa.get("workdir", "")).resolve()
    if workdir is not None and root != workdir.resolve():
        raise ValueError("VFA analysis belongs to a different workdir")
    if root != vfa_path.parent.resolve():
        raise ValueError("VFA summary is outside its bound workdir")
    review_path = _resolve_bound_path(vfa.get("review_path"), root)
    if review_path is None:
        raise ValueError("VFA mode/geometry review is missing")
    handoff = _bound_vfa_handoff(vfa, vfa_path.parent, root, contract)
    if not handoff or handoff.get("source_method") != "dimer":
        raise ValueError("VFA handoff is missing, stale or not DIMER-derived")
    handoff_path = Path(handoff["_evidence_path"])
    analysis_source = _resolve_bound_path(handoff.get("saddle_analysis_source"), handoff_path.parent)
    if analysis_source is None or analysis_source.resolve() != dimer_path.resolve():
        raise ValueError("VFA references a different DIMER analysis")
    if vfa.get("saddle_analysis_sha256") != sha256_file(dimer_path):
        raise ValueError("VFA DIMER analysis digest is stale")
    final = _require_dimer_identity(dimer, dimer_path, vfa, handoff, handoff_path, contract)
    current_dimer = analyze_dimer(final.parent, write_output=False)
    if current_dimer != dimer:
        raise ValueError("DIMER summary differs from its current scientific evidence")
    scope = vfa_scope_checks(root, handoff_path)
    if not all(scope.values()):
        raise ValueError("VFA scope review is missing, stale or invalid: " + ", ".join(key for key, ok in scope.items() if not ok))
    _require_final_dimer_review(dimer, dimer_path, final, handoff, soft_review_path)
    if set(handoff.get("reaction_atom_indices_zero_based", [])) != set(contract["reaction_atoms"]):
        raise ValueError("VFA active scope uses a different reaction atom set")
    current_vfa = analyze_vfa(root, contract, review_path,
        None if vfa.get("frequency_policy_is_default") else vfa.get("frequency_policy"), write_output=False)
    # Classification labels may have legacy spellings when unconfigured.
    current_vfa["frequency_threshold_status"] = vfa.get("frequency_threshold_status") if (
        current_vfa["frequency_threshold_status"] != "configured" and vfa.get("frequency_threshold_status") != "configured"
    ) else current_vfa["frequency_threshold_status"]
    if not current_vfa["scientific_review_bound"]:
        raise ValueError("VFA review identity, scientific scope or acceptance is incomplete")
    if current_vfa != vfa:
        raise ValueError("VFA summary differs from its current frequency/review evidence")
    sources = [Path(item["path"]) for payload in (dimer, vfa) for item in payload["source_files"]]
    return contract, [*sources, handoff_path, dimer_path, final]


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse TS finite-difference frequencies and apply the project A/B/C gate.")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    from scripts.ts_strategy_engine.contract import load_contract

    payload = analyze_vfa(args.workdir, load_contract(args.contract), args.review)
    print(payload["status"])


if __name__ == "__main__":
    main()
