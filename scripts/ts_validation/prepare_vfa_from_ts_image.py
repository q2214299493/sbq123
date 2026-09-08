from __future__ import annotations

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file
from scripts.neb_agent.cli_common import comma_tokens
from scripts.neb_agent.utils_report import write_json
from scripts.neb_agent.utils_structure import read_poscar, write_poscar
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.handoff import prepare_ts_handoff, resolve_ts_candidate
from scripts.ts_validation.dimer_frequency_gate import evaluate_dimer_frequency_gate


def prepare_vfa_handoff(
    source_image: Path,
    destination: Path,
    active_indices: list[int],
    contract: dict,
    saddle_analysis_path: Path,
    dry_run: bool,
    dimer_soft_gate_review_path: Path | None = None,
) -> None:
    reaction_indices = contract["reaction_atoms"]
    if not active_indices:
        raise SystemExit("VFA requires an explicit partial-Hessian active atom set")
    if not set(reaction_indices) <= set(active_indices):
        raise SystemExit("Every reaction atom must be included in the VFA active atom set")
    source = resolve_ts_candidate(source_image)
    structure = read_poscar(source)
    if any(index < 0 or index >= structure.atom_count for index in active_indices):
        raise SystemExit("VFA active atom index is outside the TS structure")
    originally_fixed = {
        index
        for index, flags in enumerate(structure.flags)
        if structure.selective and flags and all(value == "F" for value in flags)
    }
    forbidden = sorted(set(active_indices) & originally_fixed)
    if forbidden:
        raise SystemExit("VFA active set includes fixed slab atoms: " + ",".join(map(str, forbidden)))
    if not saddle_analysis_path.is_file():
        raise SystemExit(f"saddle analysis not found: {saddle_analysis_path}")
    analysis = load_json_object(saddle_analysis_path)
    if any(
        analysis.get(key) != contract[key]
        for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
    ):
        raise SystemExit("VFA saddle analysis does not match the active reaction contract")
    valid_neb = bool(
        analysis.get("technically_converged")
        and analysis.get("geometry_validated")
        and analysis.get("path_reviewed")
        and analysis.get("path_binding_valid")
        and analysis.get("internal_maximum")
        and str(analysis.get("maximum_image")) == source_image.name
    )
    dimer_gate = evaluate_dimer_frequency_gate(
        analysis,
        saddle_analysis_path,
        source,
        dimer_soft_gate_review_path,
    )
    valid_dimer = dimer_gate["frequency_handoff_allowed"]
    if not (valid_neb or valid_dimer):
        raise SystemExit("VFA requires a contract-bound converged NEB maximum or negative-curvature DIMER candidate")
    prepare_ts_handoff(
        source_image,
        destination,
        handoff_name="VFA",
        manifest_name="vfa_handoff.json",
        manifest_fields={
            "active_atom_indices_zero_based": active_indices,
            "reaction_atom_indices_zero_based": reaction_indices,
            "saddle_analysis_source": str(saddle_analysis_path),
            "saddle_analysis_sha256": sha256_file(saddle_analysis_path),
            "source_method": "dimer" if valid_dimer else "neb",
            "dimer_frequency_gate": dimer_gate if valid_dimer else None,
            "contract_sha256": contract["contract_sha256"],
            "atom_map_sha256": contract["atom_map_sha256"],
            "compatibility_sha256": contract["compatibility_sha256"],
            "frequency_method": "finite_difference_partial_hessian",
            "active_set_policy": "contract_defined_local",
            "active_indices_source": "explicit_reaction_contract_review",
            "full_hessian_required": False,
            "frequency_settings_owner": "configs/true_fe110_production.yaml",
            "grade": "Ungraded",
            "database_eligible": False,
            "submitted": False,
        },
        dry_run=dry_run,
    )
    if dry_run:
        return
    active = set(active_indices)
    structure.selective = True
    structure.flags = [("T", "T", "T") if index in active else ("F", "F", "F") for index in range(structure.atom_count)]
    write_poscar(destination / "POSCAR", structure)
    manifest_path = destination / "vfa_handoff.json"
    manifest = load_json_object(manifest_path)
    manifest["frequency_poscar_sha256"] = sha256_file(destination / "POSCAR")
    write_json(manifest_path, manifest)
    write_json(
        destination / "vfa_scope_review.json",
        {
            "status": "needs_review",
            "frequency_method": "finite_difference_partial_hessian",
            "active_set_policy": "contract_defined_local",
            "active_indices_source": "explicit_reaction_contract_review",
            "full_hessian_required": False,
            "active_atom_indices_zero_based": active_indices,
            "reaction_atom_indices_zero_based": reaction_indices,
            "scope_convergence_status": "local_scope_review_required",
            "frequency_poscar_sha256": sha256_file(destination / "POSCAR"),
            "vfa_handoff_sha256": sha256_file(manifest_path),
            "reviewer": None,
            "reviewed_at": None,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a reviewed partial-Hessian TS vibrational-validation handoff.")
    parser.add_argument("--source-image", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--active-indices", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--saddle-analysis", type=Path, required=True)
    parser.add_argument("--dimer-soft-gate-review", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    prepare_vfa_handoff(
        args.source_image,
        args.destination,
        [int(value) for value in comma_tokens(args.active_indices)],
        load_contract(args.contract),
        args.saddle_analysis,
        args.dry_run,
        args.dimer_soft_gate_review,
    )
    print("DRY_RUN" if args.dry_run else args.destination)


if __name__ == "__main__":
    main()
