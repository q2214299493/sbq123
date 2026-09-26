"""Freeze the user-approved IS-A/INT06 candidate for one GPU run; never submit."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.dual_model_ml_neb import _assert_geometry_guards, _load_images, _load_request
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
SOURCE = BASE / "h_migration_is_a_int06_path_20260926"
TEMPLATE = BASE / "h_migration_int06_mid_ci_seed_gpu_20260926"
DEST = SOURCE / "gpu_execution_20260926"


def main(*, resume_review_only: bool = False) -> None:
    if DEST.exists():
        if not resume_review_only or {p.name for p in DEST.iterdir()} != {"path_review.user_accepted.json"}:
            raise FileExistsError(f"Refuse duplicate preparation: {DEST}")
    path = SOURCE / "plan/path_candidate"
    contract_path = SOURCE / "plan/reaction_contract.normalized.json"
    contract = load_json_object(contract_path)
    binding = validate_path_binding(path, contract)
    if not binding["valid"]:
        raise ValueError(binding)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    accepted = load_json_object(path / "path_review.json")
    accepted.update(status="accepted", reviewer="user", reviewed_at=now,
                    notes="User: 可以先拿去gpu加速吧. Accept this candidate initialization and one GPU run, not a TS or VASP submission.")
    if not DEST.exists():
        DEST.mkdir()
        write_json(DEST / "path_review.user_accepted.json", accepted)
    passed, _ = validate_path_review(DEST / "path_review.user_accepted.json", path / "path_generation_report.json")
    if not passed:
        raise ValueError("User path review does not match current VTST/path evidence")
    request = load_json_object(TEMPLATE / "request.json")
    request.update(request_id="is_a9725473_to_int06_9748648_ordinary_gpu_20260926",
                   run_kind="production_gpu_path_candidate",
                   source_plan={"method": "user-reviewed H surface waypoints and segmented IDPP; preserve exact 00-10 POSCAR bytes",
                                "source_path_review_sha256": sha256_file(DEST / "path_review.user_accepted.json"),
                                "reference_ML_valley02": "not_verified_DFT_minimum"})
    if contract["broken_bonds"] or contract["formed_bonds"]:
        raise ValueError("This preparation is only for the no-bond-change H site migration")
    request["reaction"] = {key: contract[key] for key in ("reaction_id", "contract_sha256", "atom_map_sha256", "compatibility_sha256", "reaction_coordinates")}
    request["reaction"]["indexed_bond_changes"] = []
    request["images"] = []
    (DEST / "structures").mkdir()
    for index in range(11):
        source = path / f"{index:02d}/POSCAR"
        target = DEST / f"structures/{index:02d}.vasp"
        shutil.copyfile(source, target)
        request["images"].append({"image": f"{index:02d}", "path": target.relative_to(DEST).as_posix(),
                                  "sha256": sha256_file(target), "source_path": source.relative_to(ROOT).as_posix(),
                                  "source_sha256": sha256_file(source)})
    request["preconditioning"] = {"enabled": False, "purpose": "No additional H/O-H/C-C coordinate restraints"}
    request["ordinary_ml_neb"].update(max_steps=400, fmax_eV_per_A=0.10, ml_ci="off",
                                      purpose="One unrestrained ordinary ML-NEB of the reviewed IS-A to INT06 interval; no automatic retry")
    inactive = {"enforce_monitored_bond_monotonicity": False, "monitored_bond_backtrack_mode": "off",
                "require_monitored_bond_interval_coverage": False}
    request["ordinary_ml_neb"]["monitored_geometry_guard"] = inactive
    request["final_geometry_guard"] = inactive.copy()
    coordinate = contract["reaction_coordinates"][0]
    request["geometry_guards"]["monitored_bonds"] = [{"name": coordinate["name"],
        "atoms_zero_based": coordinate["atoms"], "important_interval_A": coordinate["important_interval_A"],
        "minimum_internal_images": 0}]
    request["geometry_guards"]["preserved_bonds"][2]["name"] = "C1_H49_original"
    request["production_limits"].update(image_count=11, production_submission_authorized=True)
    request["domain_validation"] = {"status": "new_interval_not_exact_structure_VASP_validated",
        "quantitative_uncertainty_calibrated": False,
        "note": "Reuse frozen epoch6. Previous INT06-MID screening/drift success does not validate this longer IS-A-INT06 interval."}
    request["fallback_policy"] = {"gpu_attempts": 1, "automatic_submission": False,
        "on_drift": "Preserve last-valid/failure geometry, assess exact MatRIS/AQCat25/VASP labels before deciding fine-tune versus path repair/local VASP."}
    evidence = {"reaction_contract.normalized.json": contract_path,
                "review/path_generation_report.json": path / "path_generation_report.json",
                "review/path_review.user_accepted.json": DEST / "path_review.user_accepted.json",
                "review/exact_mic_checks.json": SOURCE / "exact_mic_checks.json",
                "review/dist.dat": path / "dist.dat", "review/movie": path / "movie",
                "review/vtst_checks.json": SOURCE / "vtst_preparation_checks.json",
                "review/path_review.png": SOURCE / "path_review.png"}
    request["source_evidence_files"] = {}
    for name, source in evidence.items():
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        request["source_evidence_files"][name] = sha256_file(target)
    (DEST / "runtime").mkdir()
    for name, expected in request["runtime_bindings"].items():
        source = TEMPLATE / "runtime" / name
        if sha256_file(source) != expected:
            raise ValueError(f"Previously tested runtime changed: {name}")
        shutil.copyfile(source, DEST / "runtime" / name)
    preflight = Path(__file__).with_name("gpu_preflight.py")
    shutil.copyfile(preflight, DEST / "runtime/gpu_preflight.py")
    request["runtime_bindings"]["gpu_preflight.py"] = sha256_file(preflight)
    write_json(DEST / "request.json", request)
    loaded = _load_request(DEST / "request.json")
    images = _load_images(loaded, DEST)
    _assert_geometry_guards(images, loaded, "work_preflight", monitored_guard_policy=inactive)
    write_json(DEST / "local_preflight.json", {"status": "PASS", "request_sha256": sha256_file(DEST / "request.json"),
        "image_count": len(images), "atom_count": len(images[0]), "fixed_atom_count": 18,
        "accepted_path_binding": binding, "geometry_checked_without_model": True,
        "model_executed": False, "submitted": False, "created_at": now})
    print(json.dumps({"status": "PASS", "package": str(DEST), "request_sha256": sha256_file(DEST / "request.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-review-only", action="store_true",
                        help="Resume only the inspected initial failure that left one accepted review and no payload")
    main(resume_review_only=parser.parse_args().resume_review_only)
