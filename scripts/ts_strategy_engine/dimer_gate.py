from __future__ import annotations

from pathlib import Path

from typing import Any

import numpy as np


from scripts.artifact_io import load_json_object, sha256_file

from scripts.neb_agent.utils_structure import (
    compatible,
    displacement_cart,
    read_poscar,
)

from .dimer_path_gate import _evaluate_gpu_ml_neb_parent, coarse_neb_peak_stall_evidence

from .dimer_gate_common import _finite, _force_reduced

from .dimer_gate_common import load_policy as load_policy

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_POLICY = ROOT / "configs" / "dimer_gate.yaml"

def evaluate_candidate_triad(
    previous_path: Path,
    candidate_path: Path,
    next_path: Path,
    analysis: dict[str, Any],
    reaction_indices: list[int],
    *,
    policy_path: Path = DEFAULT_POLICY,
    analysis_root: Path | None = None,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    hard = policy["hard_gate"]
    previous = read_poscar(previous_path)
    candidate = read_poscar(candidate_path)
    following = read_poscar(next_path)
    image_names = (
        previous_path.parent.name,
        candidate_path.parent.name,
        next_path.parent.name,
    )
    rows = {
        str(row.get("image")): row
        for row in analysis.get("images", [])
        if isinstance(row, dict) and row.get("image") is not None
    }
    triad_rows = [rows.get(name) for name in image_names]
    parent_method = str(analysis.get("parent_neb_method", "needs_confirmation"))
    parent_method_allowed = parent_method in set(policy["eligibility"]["parent_methods"])
    compatibility_errors = [
        *(f"previous:{value}" for value in compatible(candidate, previous, float(hard["cell_tolerance_A"]))),
        *(f"next:{value}" for value in compatible(candidate, following, float(hard["cell_tolerance_A"]))),
    ]
    numbered = all(name.isdigit() for name in image_names)
    adjacent = bool(
        numbered
        and int(image_names[0]) + 1 == int(image_names[1])
        and int(image_names[1]) + 1 == int(image_names[2])
    )
    internal = bool(adjacent and int(image_names[0]) >= 0 and int(image_names[1]) > 0)
    indices_valid = bool(
        reaction_indices
        and len(set(reaction_indices)) == len(reaction_indices)
        and all(0 <= index < candidate.atom_count for index in reaction_indices)
    )
    output_complete = bool(
        all(
            row
            and row.get("has_output")
            and row.get("normal_completion")
            for row in triad_rows
        )
    )
    electronic_convergence = bool(
        all(
            row
            and (
                row.get("electronically_converged") is True
                or row.get("electronic_convergence_reached") is True
            )
            for row in triad_rows
        )
    )
    readable_energy_force = bool(
        all(
            row
            and _finite(row.get("final_energy_eV"))
            and _finite(row.get("final_atomic_force_eVA"))
            for row in triad_rows
        )
    )
    reaction_steps: dict[str, float | None] = {"previous_to_candidate_A": None, "candidate_to_next_A": None}
    branch_shifts: dict[str, float | None] = {"previous_to_candidate": None, "candidate_to_next": None}
    if indices_valid and not compatibility_errors:
        left_steps = [
            float(np.linalg.norm(displacement_cart(candidate, previous.frac[index], candidate.frac[index])))
            for index in reaction_indices
        ]
        right_steps = [
            float(np.linalg.norm(displacement_cart(candidate, candidate.frac[index], following.frac[index])))
            for index in reaction_indices
        ]
        reaction_steps = {
            "previous_to_candidate_A": max(left_steps),
            "candidate_to_next_A": max(right_steps),
        }
        left_raw = candidate.frac[reaction_indices] - previous.frac[reaction_indices]
        right_raw = following.frac[reaction_indices] - candidate.frac[reaction_indices]
        branch_shifts = {
            "previous_to_candidate": float(np.max(np.abs(np.rint(left_raw)))),
            "candidate_to_next": float(np.max(np.abs(np.rint(right_raw)))),
        }
    reaction_continuity = bool(
        indices_valid
        and all(
            value is not None and value <= float(hard["reaction_atom_neighbor_step_max_A"])
            for value in reaction_steps.values()
        )
    )
    periodic_mapping = bool(
        indices_valid
        and all(
            value is not None and value <= float(hard["periodic_branch_tolerance"])
            for value in branch_shifts.values()
        )
    )
    checks = {
        "eligible_parent_method": parent_method_allowed,
        "numbered_internal_adjacent_images": internal,
        "cell_elements_order_selective_dynamics_match": not compatibility_errors,
        "reaction_indices_valid": indices_valid,
        "triad_outputs_complete": output_complete,
        "triad_electronically_converged": electronic_convergence,
        "triad_energy_and_atomic_force_readable": readable_energy_force,
        "reaction_center_numeric_continuity": reaction_continuity,
        "continuous_periodic_branch": periodic_mapping,
    }
    gpu_parent_evidence: dict[str, Any] | None = None
    if parent_method == "gpu_ml_neb_vasp_validated_triad":
        gpu_parent_evidence = _evaluate_gpu_ml_neb_parent(
            analysis,
            image_names,
            (previous_path, candidate_path, next_path),
            triad_rows,
            policy,
            analysis_root,
        )
        checks.update(gpu_parent_evidence["checks"])
    energies = [
        row.get("final_energy_eV") if row else None
        for row in triad_rows
    ]
    local_peak = bool(
        all(_finite(value) for value in energies)
        and float(energies[0]) < float(energies[1]) > float(energies[2])
    )
    reduced_forces = bool(
        triad_rows
        and all(_force_reduced(row, float(policy["recommended_gate"]["force_reduction_fraction_max"])) for row in triad_rows)
    )
    recommendations = {
        "parent_neb_technically_converged": bool(analysis.get("technically_converged")),
        "strict_local_energy_maximum": local_peak,
        "triad_forces_clearly_reduced": reduced_forces,
        "coarse_neb_other_images_stable_peak_stalled": coarse_neb_peak_stall_evidence(
            analysis, policy=policy
        )["passed"],
        "single_target_process_without_stable_intermediate": not bool(analysis.get("internal_minimum_warning")),
        "candidate_between_is_and_fs": None,
        "mode_provenance_hash_bound": None,
    }
    return {
        "schema_version": 2,
        "policy_file": str(policy_path),
        "policy_sha256": sha256_file(policy_path),
        "image_names": list(image_names),
        "parent_method": parent_method,
        "hard_checks": checks,
        "hard_gate_passed": all(checks.values()),
        "hard_gate_errors": [name for name, passed in checks.items() if not passed],
        "compatibility_errors": compatibility_errors,
        "reaction_atom_neighbor_steps": reaction_steps,
        "periodic_branch_shifts": branch_shifts,
        "recommended_checks": recommendations,
        "recommended_gate_passed": all(value is True for value in recommendations.values()),
        "gpu_ml_neb_parent_evidence": gpu_parent_evidence,
    }

def validate_modecar_bundle(
    workdir: Path,
    *,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    hard = policy["hard_gate"]
    poscar_path = workdir / "POSCAR"
    previous_path = workdir / "PREVIOUS_POSCAR"
    next_path = workdir / "NEXT_POSCAR"
    modecar_path = workdir / "MODECAR"
    manifest_path = workdir / "dimer_handoff.json"
    review_path = workdir / "mode_review.json"
    try:
        candidate = read_poscar(poscar_path)
        previous = read_poscar(previous_path)
        following = read_poscar(next_path)
        manifest = load_json_object(manifest_path)
        review = load_json_object(review_path)
        mode = _read_modecar(modecar_path, candidate.atom_count)
    except (OSError, ValueError, KeyError) as exc:
        return {
            "hard_gate_passed": False,
            "hard_gate_errors": [f"unreadable_dimer_gate_bundle:{exc}"],
            "hard_checks": {},
        }

    compatibility_errors = [
        *(f"previous:{value}" for value in compatible(candidate, previous, float(hard["cell_tolerance_A"]))),
        *(f"next:{value}" for value in compatible(candidate, following, float(hard["cell_tolerance_A"]))),
    ]
    fixed_components_zero = True
    for index, flags in enumerate(candidate.flags):
        for axis, flag in enumerate(flags):
            if flag == "F" and abs(float(mode[index, axis])) > float(hard["fixed_mode_component_tolerance"]):
                fixed_components_zero = False
    norm = float(np.linalg.norm(mode))
    reaction_indices = review.get("reaction_atom_indices_zero_based", [])
    indices_valid = bool(
        reaction_indices
        and all(isinstance(index, int) and 0 <= index < candidate.atom_count for index in reaction_indices)
    )
    reaction_fraction = (
        float(np.linalg.norm(mode[reaction_indices])) / norm
        if indices_valid and norm > float(hard["mode_norm_min"])
        else 0.0
    )
    hashes_match = bool(
        manifest.get("source_sha256") == sha256_file(poscar_path)
        and manifest.get("previous_sha256") == sha256_file(previous_path)
        and manifest.get("next_sha256") == sha256_file(next_path)
        and manifest.get("modecar_sha256") == sha256_file(modecar_path)
        and manifest.get("dimer_gate_policy_sha256") == sha256_file(policy_path)
        and review.get("modecar_sha256") == sha256_file(modecar_path)
    )
    semantic_review = bool(
        review.get("status") == "accepted"
        and review.get("reviewer")
        and review.get("reviewed_at")
        and review.get("reaction_center_continuity") == "accepted"
        and review.get("periodic_mapping") == "accepted"
        and review.get("adsorption_site_continuity") == "accepted"
        and review.get("reaction_mechanism_continuity") == "accepted"
        and review.get("mode_assignment") == "accepted"
        and str(review.get("target_reaction_event", "")).strip()
    )
    candidate_gate = manifest.get("candidate_hard_gate", {})
    candidate_gate_bound = bool(
        candidate_gate.get("hard_gate_passed") is True
        and not candidate_gate.get("hard_gate_errors")
    )
    checks = {
        "candidate_triad_hard_gate_bound": candidate_gate_bound,
        "modecar_atom_count_and_order_bound": hashes_match and mode.shape == (candidate.atom_count, 3),
        "triad_structure_contract_preserved": not compatibility_errors,
        "fixed_mode_components_zero": fixed_components_zero,
        "modecar_finite": bool(np.isfinite(mode).all()),
        "modecar_nonzero": norm > float(hard["mode_norm_min"]),
        "modecar_normalized": abs(norm - 1.0) <= float(hard["mode_normalization_tolerance"]),
        "mode_main_components_match_reaction_center": reaction_fraction
        >= float(hard["reaction_atom_mode_fraction_min"]),
        "chemical_continuity_and_mode_review_accepted": semantic_review,
    }
    return {
        "hard_gate_passed": all(checks.values()),
        "hard_gate_errors": [name for name, passed in checks.items() if not passed],
        "hard_checks": checks,
        "mode_norm": norm,
        "reaction_atom_mode_fraction": reaction_fraction,
        "compatibility_errors": compatibility_errors,
        "recommended_checks": manifest.get("recommended_gate", {}),
    }

def _read_modecar(path: Path, atom_count: int) -> np.ndarray:
    rows: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError("MODECAR must contain exactly three components per atom")
        rows.append([float(value) for value in fields])
    mode = np.asarray(rows, dtype=float)
    if mode.shape != (atom_count, 3):
        raise ValueError(f"MODECAR shape {mode.shape} does not match {(atom_count, 3)}")
    if not np.isfinite(mode).all():
        raise ValueError("MODECAR contains non-finite values")
    return mode
