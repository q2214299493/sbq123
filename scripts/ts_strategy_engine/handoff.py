from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np

from scripts.neb_agent.utils_report import write_json
from scripts.neb_agent.utils_structure import compatible, minimum_image_delta, preferred_image_structure, read_poscar
from scripts.artifact_io import load_json_object, sha256_file
from scripts.ts_strategy_engine.dimer_gate import evaluate_candidate_triad
from scripts.ts_strategy_engine.execution_gate import require_action


def resolve_ts_candidate(source_image: Path) -> Path:
    candidate = source_image if source_image.is_file() else preferred_image_structure(source_image)
    if candidate.is_file():
        return candidate
    raise SystemExit(f"TS candidate not found: {candidate}")


def prepare_ts_handoff(
    source_image: Path,
    destination: Path,
    *,
    handoff_name: str,
    manifest_name: str,
    manifest_fields: dict[str, Any],
    dry_run: bool,
) -> Path:
    if destination.exists():
        raise SystemExit(f"Destination already exists; {handoff_name} handoff never overwrites a calculation.")
    source = resolve_ts_candidate(source_image)
    if dry_run:
        return source
    destination.mkdir(parents=True)
    shutil.copy2(source, destination / "POSCAR")
    write_json(
        destination / manifest_name,
        {
            "source_ts_candidate": str(source),
            "source_sha256": sha256_file(source),
            **manifest_fields,
        },
    )
    return source


def prepare_dimer_handoff(
    source_image: Path,
    previous_image: Path,
    next_image: Path,
    destination: Path,
    dry_run: bool,
    *,
    analysis_path: Path,
    path_review_path: Path,
    reaction_indices: list[int],
    contract_binding: dict[str, Any],
    gate_decision: Path | None = None,
    gate_state_sha256: str | None = None,
) -> Path:
    if not dry_run:
        if gate_decision is None or gate_state_sha256 is None:
            raise SystemExit("DIMER handoff requires an authoritative PREPARE_DIMER_HANDOFF decision")
        try:
            require_action(gate_decision, "PREPARE_DIMER_HANDOFF", gate_state_sha256)
        except (OSError, ValueError, PermissionError) as exc:
            raise SystemExit(str(exc)) from exc
    source = resolve_ts_candidate(source_image)
    previous = resolve_ts_candidate(previous_image)
    following = resolve_ts_candidate(next_image)
    analysis = _accepted_json(analysis_path, "NEB analysis")
    review = _accepted_json(path_review_path, "path review")
    if review.get("status") != "accepted":
        raise SystemExit("DIMER requires an accepted path review")
    if not (
        analysis.get("geometry_validated")
        and analysis.get("path_reviewed")
        and analysis.get("path_binding_valid")
    ):
        raise SystemExit("DIMER requires a geometry-reviewed, contract-bound parent NEB path")
    if any(
        analysis.get(key) != contract_binding.get(key)
        for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
    ):
        raise SystemExit("DIMER analysis does not match the active reaction contract")
    candidate_gate = evaluate_candidate_triad(
        previous,
        source,
        following,
        analysis,
        reaction_indices,
        analysis_root=analysis_path.parent,
    )
    if not candidate_gate["hard_gate_passed"]:
        raise SystemExit(
            "DIMER candidate hard gate failed: "
            + ", ".join(candidate_gate["hard_gate_errors"])
        )

    center = read_poscar(source)
    left = read_poscar(previous)
    right = read_poscar(following)
    errors = [f"previous:{error}" for error in compatible(center, left)]
    errors.extend(f"next:{error}" for error in compatible(center, right))
    if errors:
        raise SystemExit("DIMER image incompatibility: " + ", ".join(errors))
    mode = minimum_image_delta(left.frac, right.frac) @ center.cell
    fixed = [
        index
        for index, flags in enumerate(center.flags)
        if center.selective and flags and all(value == "F" for value in flags)
    ]
    if fixed:
        mode[fixed] = 0.0
    norm = float(np.linalg.norm(mode))
    if norm < 1e-12:
        raise SystemExit("DIMER adjacent-image mode has zero norm")
    mode /= norm
    if any(index < 0 or index >= center.atom_count for index in reaction_indices):
        raise SystemExit("DIMER reaction atom index is outside the source image")
    reaction_norm = float(np.linalg.norm(mode[reaction_indices])) if reaction_indices else 0.0
    resolved = prepare_ts_handoff(
        source_image,
        destination,
        handoff_name="DIMER",
        manifest_name="dimer_handoff.json",
        manifest_fields={
            "previous_image": str(previous_image),
            "next_image": str(next_image),
            "mode_source": "adjacent_reviewed_path_images",
            "analysis_source": str(analysis_path),
            "analysis_sha256": sha256_file(analysis_path),
            "path_review_source": str(path_review_path),
            "path_review_sha256": sha256_file(path_review_path),
            "parent_neb_method": analysis.get("parent_neb_method", "needs_confirmation"),
            "modecar_status": "generated_requires_visual_review",
            "mode_norm": 1.0,
            "reaction_atom_mode_fraction": reaction_norm,
            "candidate_hard_gate": candidate_gate,
            "recommended_gate": candidate_gate["recommended_checks"],
            "dimer_gate_policy_sha256": candidate_gate["policy_sha256"],
            "contract_sha256": contract_binding["contract_sha256"],
            "atom_map_sha256": contract_binding["atom_map_sha256"],
            "compatibility_sha256": contract_binding["compatibility_sha256"],
            "path_generation_sha256": contract_binding["report_sha256"],
            "submitted": False,
        },
        dry_run=dry_run,
    )
    if not dry_run:
        shutil.copy2(previous, destination / "PREVIOUS_POSCAR")
        shutil.copy2(following, destination / "NEXT_POSCAR")
        modecar = destination / "MODECAR"
        modecar.write_text(
            "".join(f" {row[0]:20.12f} {row[1]:20.12f} {row[2]:20.12f}\n" for row in mode),
            encoding="ascii",
        )
        manifest_path = destination / "dimer_handoff.json"
        manifest = load_json_object(manifest_path)
        manifest.update(
            {
                "previous_sha256": sha256_file(destination / "PREVIOUS_POSCAR"),
                "next_sha256": sha256_file(destination / "NEXT_POSCAR"),
                "modecar_sha256": sha256_file(modecar),
            }
        )
        manifest["recommended_gate"]["mode_provenance_hash_bound"] = True
        write_json(manifest_path, manifest)
        write_json(
            destination / "mode_review.json",
            {
                "status": "needs_review",
                "mode_norm": 1.0,
                "fixed_atom_indices_zero_based": fixed,
                "reaction_atom_indices_zero_based": reaction_indices,
                "reaction_atom_mode_fraction": reaction_norm,
                "modecar_file": str(modecar),
                "modecar_sha256": sha256_file(modecar),
                "reaction_center_continuity": "needs_review",
                "periodic_mapping": "needs_review",
                "adsorption_site_continuity": "needs_review",
                "reaction_mechanism_continuity": "needs_review",
                "mode_assignment": "needs_review",
                "target_reaction_event": None,
                "candidate_between_is_and_fs": "needs_review",
                "single_target_process_without_stable_intermediate": "needs_review",
                "reviewer": None,
                "reviewed_at": None,
            },
        )
    return resolved


def _accepted_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")
    try:
        payload = load_json_object(path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"invalid {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"invalid {label}: expected JSON object")
    return payload
