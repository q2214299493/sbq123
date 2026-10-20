"""Prepare six matched inputs from reviewed seed-origin outputs; never execute."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.execution_backends import load_execution_backends, require_vasp_backend
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
SOURCE = BASE / "adsorption_control_geometry3_20261020_v1"
DEST = BASE / "adsorption_control_paired_vasp3_20261020_v1"
NAMES = ("06_C", "09_C", "10_A")
ARMS = ("baseline", "candidate")
MODEL_HASHES = {
    "baseline": "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50",
    "candidate": "cfcac123cd56b866a1ea36cc780a3aee634f3aeec979bda4ae8bee2cc831e523",
}


def select_rows(review: dict) -> dict:
    rows = [r for r in review["geometry"] if r["origin"] == "seed"]
    keyed = {(r["name"], r["model"]): r for r in rows}
    if len(rows) != 6 or set(keyed) != {(n, a) for n in NAMES for a in ARMS}:
        raise ValueError("expected exactly three unique seed-origin pairs")
    for row in rows:
        if not (row["converged"] and row["status"] == "ML_CONVERGED"
                and row["same_graph_as_seed"] and row["same_graph_as_DFT"]):
            raise ValueError("source final geometry requires new review")
    return keyed


def verify_geometry(path: Path, seed: Path, row: dict) -> None:
    if sha256_file(path) != row["final_POSCAR_sha256"]:
        raise ValueError("reviewed final POSCAR bytes changed")
    pose, original = read_poscar(path), read_poscar(seed)
    if (pose.symbols != original.symbols or pose.counts != original.counts
            or pose.flags != original.flags or not np.isfinite(pose.frac).all()
            or not np.allclose(pose.cell, original.cell, atol=1e-12, rtol=0)
            or not np.allclose(pose.frac[:18], original.frac[:18], atol=1e-12, rtol=0)):
        raise ValueError("atom order/cell/fixed geometry changed")
    graph = sorted(tuple(edge) for edge in connectivity(pose, list(range(45, len(pose.frac)))))
    if graph != sorted(tuple(edge) for edge in row["final_graph"]):
        raise ValueError("final molecular graph no longer matches review")


def check_pair(a: Path, b: Path) -> dict:
    for folder in (a, b):
        if any((folder / name).exists() for name in ("WAVECAR", "CHGCAR", "CONTCAR", "OUTCAR", "OSZICAR")):
            raise ValueError("paired benchmark must start fresh, without restart/results")
    common = ("INCAR", "KPOINTS", "POTCAR.spec", "script.lsf")
    hashes = {name: sha256_file(a / name) for name in common}
    if any(sha256_file(b / name) != hashes[name] for name in common):
        raise ValueError("paired method/resource inputs differ")
    pa, pb = read_poscar(a / "POSCAR"), read_poscar(b / "POSCAR")
    if (pa.symbols != pb.symbols or pa.counts != pb.counts or pa.flags != pb.flags
            or not np.allclose(pa.cell, pb.cell, atol=1e-12, rtol=0)
            or not np.allclose(pa.frac[:18], pb.frac[:18], atol=1e-12, rtol=0)):
        raise ValueError("pair atom order/cell/fixed mask differs")
    return {"identical_method_resource_hashes": hashes, "fresh_start": True,
            "same_atom_order_cell_fixed_mask": True}


def prepare() -> dict:
    receipt = load_json_object(SOURCE / "validation_receipt.json")
    required = ("geometry_comparison_review_v2.json", "validation_request.json",
                "returned/return_manifest.json", "trajectory_audit.json")
    bindings = {r["path"]: r["sha256"] for r in receipt["sources"]}
    for relative in required:
        path = SOURCE / relative
        if sha256_file(path) != bindings[path.relative_to(ROOT).as_posix()]:
            raise ValueError("upstream review/return/audit binding changed")
    review = load_json_object(SOURCE / required[0])
    request = load_json_object(SOURCE / "validation_request.json")
    if (receipt["status"] != "PAIRED_GEOMETRY_DIAGNOSTIC_COMPLETE_MIXED_RESULTS_NO_SPEEDUP_CLAIM"
            or review["request_sha256"] != sha256_file(SOURCE / "validation_request.json")
            or any(request["models"][a]["sha256"] != MODEL_HASHES[a] for a in ARMS)):
        raise ValueError("frozen source review/model mismatch")
    rows = select_rows(review)
    returned = {r["path"]: r["sha256"] for r in load_json_object(SOURCE / "returned/return_manifest.json")["files"]}
    cases = {c["name"]: c for c in request["geometry_cases"]}
    old = {r["name"]: r for r in load_json_object(BASE / "vasp_batch_v1/submission_summary.json")["records"]}
    backend = load_execution_backends().vasp
    require_vasp_backend(backend.server_alias, backend.name)
    for (name, arm), row in rows.items():
        relative = f"output/{arm}/{name}/seed/POSCAR"
        source = SOURCE / "returned" / relative
        if sha256_file(source) != returned[relative]:
            raise ValueError("returned artifact bytes changed")
        seed = ROOT / cases[name]["seed_source_path"]
        if sha256_file(seed) != cases[name]["seed_sha256"]:
            raise ValueError("original common seed changed")
        verify_geometry(source, seed, row)

    DEST.mkdir(exist_ok=False)
    jobs = []
    for name in NAMES:
        for arm in ARMS:
            row = rows[name, arm]
            folder = DEST / name / arm
            folder.mkdir(parents=True, exist_ok=False)
            source = SOURCE / f"returned/output/{arm}/{name}/seed/POSCAR"
            shutil.copyfile(source, folder / "POSCAR")
            settings = build_fe110_adsorption_relaxation(folder, cores=32)
            metadata = {
                "name": f"{name}_{arm}", "pair_id": name, "arm": arm,
                "formula": old[name]["formula"], "connectivity": old[name]["connectivity"],
                "source_role": "work_reviewed_seed_origin_ML_final_not_minimum_drift",
                "source_structure": source.relative_to(ROOT).as_posix(),
                "source_sha256": sha256_file(source), "checkpoint": request["models"][arm],
                "common_original_seed_sha256": cases[name]["seed_sha256"],
                "review_path": (SOURCE / required[0]).relative_to(ROOT).as_posix(),
                "review_sha256": sha256_file(SOURCE / required[0]),
                "geometry_checks": row, "original_source_case": cases[name],
                "role": "paired_benchmark_candidate_only_not_accepted_DFT_result",
                "warning": receipt["retained_warning"],
            }
            write_json_exclusive(folder / "candidate_manifest.json", metadata)
            # This canonical check only reads the retry history. It cannot submit.
            report = preflight(folder, "adsorption_relaxation")
            jobs.append({
                "name": name, "arm": arm, "path": folder.relative_to(ROOT).as_posix(),
                "source_POSCAR_sha256": row["final_POSCAR_sha256"],
                "common_original_seed_sha256": cases[name]["seed_sha256"],
                "checkpoint_sha256": MODEL_HASHES[arm], "settings": settings,
                "bundle_sha256": report["bundle_sha256"], "files": report["files"],
                "preflight_passed": report["passed"], "preflight_errors": report["errors"],
                "preflight_sha256": sha256_file(folder / "submission_preflight.json"),
                "host": backend.server_alias,
                "proposed_remote_dir": f"~/sbq/Fe110/adsorption/control_paired3_20261020_v1/{name}/{arm}",
                "potcar_source": old[name]["potcar_source"],
                "potcar_sha256": old[name]["potcar_sha256"],
                "potcar_verification": "historical approved binding;fresh remote recheck required before submission",
                "scheduler_job_id": None, "scheduler_status": "NOT_SUBMITTED",
            })
    pairs = [{"name": n, **check_pair(DEST / n / ARMS[0], DEST / n / ARMS[1])} for n in NAMES]
    manifest = {
        "status": "PREPARED_LOCAL_ONLY" if all(j["preflight_passed"] for j in jobs) else "PREPARATION_BLOCKED",
        "schema_version": 1, "user_request": "准备3组配对VASP松弛，共6个任务",
        "pair_count": 3, "job_count": 6, "jobs": jobs, "pairs": pairs,
        "sources": [{"path": (SOURCE / p).relative_to(ROOT).as_posix(), "sha256": sha256_file(SOURCE / p)}
                    for p in (*required, "validation_receipt.json")],
        "generation_sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in (
            Path(__file__), ROOT / "scripts/vasp_inputs.py", ROOT / "scripts/vasp_lsf.py",
            ROOT / "scripts/templates/sunboquan_vasp.lsf", ROOT / "scripts/adsorption/preflight_fe110_adsorption.py",
            ROOT / "configs/true_fe110_production.yaml", ROOT / "configs/execution_backends.yaml")],
        "execution_authorized": False, "ALLOWED_ACTIONS": [], "uploaded": False,
        "new_VASP": 0, "new_GPU": 0, "model_promoted": False, "measured_speedup": False,
        "budget": {"MPI_ranks_per_job": 32, "ranks_per_node": 32, "max_ionic_steps_per_job": 300,
                   "six_job_step_budget": 1800, "all_six_simultaneous_ranks": 192,
                   "walltime_estimate": None, "simultaneous_execution_authorized": False},
        "benchmark_requirements": [
            "Normal completion,electronic and movable-force convergence;retained atom order,cell and fixed mask.",
            "Review molecular identity AND adsorption basin/coordination before matching final minima.",
            "Compare ionic steps,total SCF iterations,elapsed runtime and CPU core-hours;exclude queue wait.",
            "Account for per-arm ML time;report GPU and shared training/label cost separately with declared amortization.",
            "Different final minima or uncompleted jobs are outcomes,not a valid speedup ratio.",
            "Old131/101/114-step jobs are references,not these exact matched controls.",
        ],
        "fresh_start_policy": "New empty workdirs;no WAVECAR/CHGCAR/optimizer history;canonical routine production inputs.",
        "remaining_before_execution": ["Explicit exact-six-job user submission authorization and current hash-bound gate.",
                                       "Live backend/POTCAR/source hash check and duplicate-submission check."],
    }
    write_json_exclusive(DEST / "batch_manifest.json", manifest)
    return {"status": manifest["status"], "jobs": len(jobs), "preflight_passes": sum(j["preflight_passed"] for j in jobs),
            "path": str(DEST), "new_VASP": 0}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(prepare())


if __name__ == "__main__":
    main()
