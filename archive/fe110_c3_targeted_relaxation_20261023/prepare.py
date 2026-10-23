"""Prepare exactly two existing C3 candidates locally; never transfer or submit."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.adsorption.build_fe110_adsorption import read_poscar  # noqa: E402
from scripts.adsorption.build_fe110_care_isomers import review  # noqa: E402
from scripts.artifact_io import sha256_file, write_json  # noqa: E402
from scripts.neb_agent.submission import preflight  # noqa: E402
from scripts.vasp_inputs import build_fe110_adsorption_relaxation  # noqa: E402
from scripts.workflow_geometry import minimum_image_delta_xy, pbc_xy_distance  # noqa: E402


NAMES = ("05_C3H2O_FLJNAOYG_cfg2", "07_C3H2O_POVFFVOJ_cfg2")


def geometry(raw_path: Path, revised_path: Path, slab_path: Path) -> dict:
    raw, revised, slab = map(read_poscar, (raw_path, revised_path, slab_path))
    if revised.symbols != ["Fe", "C", "O", "H"] or revised.counts != [45, 3, 1, 2]:
        raise ValueError("Unexpected C3 composition/order")
    if not np.allclose(revised.cell, slab.cell, rtol=0, atol=1e-10):
        raise ValueError("Slab cell changed")
    if not np.allclose(minimum_image_delta_xy(revised.frac[:45]-slab.frac), 0, rtol=0, atol=1e-10):
        raise ValueError("Slab coordinates changed")
    if revised.flags[:45] != slab.flags:
        raise ValueError("Slab selective dynamics changed")
    result = review(raw, revised, list(range(45, 51)))
    if result["verdict"] != "pass" or result["warnings"]:
        raise ValueError(f"Candidate requires geometry repair: {revised_path}")
    cart = revised.frac @ revised.cell
    result["bonds_A"] = [
        {"adsorbate_local_0based": [i, j], "distance": pbc_xy_distance(revised.cell, cart[45+i], cart[45+j])}
        for i, j in result["connectivity_edges_local_0based"]
    ]
    result["nearest_Fe"] = []
    for index in range(45, 51):
        distances = [pbc_xy_distance(revised.cell, cart[index], cart[fe]) for fe in range(45)]
        nearest = int(np.argmin(distances))
        result["nearest_Fe"].append({"atom_1based": index+1, "Fe_1based": nearest+1, "distance_A": distances[nearest]})
    return result


def timing_reference(root: Path) -> list[dict]:
    references = []
    for job in ("9629858", "9629859"):
        path = root / "calculations/fe110_c3_existing_recovery_20261023/collection_v1" / job / "OUTCAR"
        with path.open("rb") as handle:
            header = handle.read(10000).decode("ascii", errors="replace")
            handle.seek(max(0, path.stat().st_size-12000))
            tail = handle.read().decode("ascii", errors="replace")
        ranks = int(re.search(r"running on\s+(\d+) total cores", header)[1])
        elapsed = float(re.search(r"Elapsed time \(sec\):\s*([\d.]+)", tail)[1])
        references.append({"job_id": job, "OUTCAR_sha256": sha256_file(path), "cores": ranks,
                           "ionic_steps": 80, "elapsed_seconds": elapsed,
                           "allocated_core_hours_estimate": elapsed*ranks/3600})
    return references


def prepare(output: Path, custodian: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing run root: {output}")
    source = ROOT / "calculations/fe110_care8_isomers_20260716"
    manifest_path = source / "candidate_manifest.json"
    revision_path = source / "revised/revision_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision = json.loads(revision_path.read_text(encoding="utf-8"))
    slab_path = ROOT / manifest["source_slab"]
    if sha256_file(slab_path) != manifest["source_slab_sha256"]:
        raise ValueError("Clean slab source hash mismatch")
    candidates = {record["name"]: record for record in manifest["candidates"]}
    revisions = {record["name"]: record for record in revision["records"]}
    reviewed = {}
    for name in NAMES:
        if revisions[name]["geometry_review"]["verdict"] != "pass":
            raise ValueError(f"Historical revision not reviewed: {name}")
        reviewed[name] = geometry(source / name / "POSCAR", source / "revised" / name / "POSCAR", slab_path)
    references = timing_reference(ROOT)
    output.mkdir(parents=True)
    write_json(output / "preparation_state.json", {"status": "PREPARING", "submitted": False})
    cases = []
    for name in NAMES:
        destination = output / name
        destination.mkdir()
        poscar = source / "revised" / name / "POSCAR"
        shutil.copyfile(poscar, destination / "POSCAR")
        metadata = build_fe110_adsorption_relaxation(destination, screening=True, write_local_moments=True)
        record = {
            "name": name, "formula": "C3H2O", "exact_smiles": candidates[name]["exact_smiles"],
            "purpose": "intact_C3_near_equilibrium_label_source_search",
            "relaxation_stage": metadata["relaxation_stage"], "write_local_moments": True,
            "geometry_review": reviewed[name], "builder": metadata,
            "source": {"kind": "previously_reviewed_local_CARE_candidate_prediction_only",
                       "revised_POSCAR_sha256": sha256_file(poscar),
                       "raw_POSCAR_sha256": sha256_file(source / name / "POSCAR"),
                       "manifest_sha256": sha256_file(manifest_path),
                       "revision_manifest_sha256": sha256_file(revision_path),
                       "clean_slab_sha256": sha256_file(slab_path)},
            "accepted_endpoint": False, "stability_verified": False, "submitted": False,
        }
        write_json(destination / "candidate_manifest.json", record)
        command = [sys.executable, "-X", "utf8", str(custodian), "--mode", "validate",
                   "--workdir", str(destination), "--incar", str(destination/"INCAR"),
                   "--poscar", str(destination/"POSCAR"), "--calculation-type", "adsorption_GO",
                   "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
        process = subprocess.run(command, capture_output=True, cwd=ROOT)
        (destination / "incar_custodian_validation.json").write_bytes(process.stdout)
        if process.returncode:
            (destination / "incar_custodian_error.txt").write_bytes(process.stderr)
            raise RuntimeError(f"Custodian failed for {name}: exit={process.returncode}")
        custodian_result = json.loads(process.stdout)
        if custodian_result["status"] != "VALIDATION_ONLY" or custodian_result["blockers"]:
            raise ValueError(f"Custodian blocked {name}")
        gate = preflight(destination, "adsorption_relaxation")
        cases.append({"name": name, "exact_smiles": record["exact_smiles"],
                      "preflight_passed": gate["passed"], "errors": gate["errors"],
                      "bundle_sha256": gate["bundle_sha256"],
                      "custodian_validation_sha256": sha256_file(destination / "incar_custodian_validation.json")})
    plan = {"schema_version": 1, "status": "PREPARED" if all(c["preflight_passed"] for c in cases) else "BLOCKED",
            "submitted": False, "new_ML_run": False, "cases": cases,
            "budget": {"jobs": 2, "cores_per_job": 32, "max_parallel_jobs": 2,
                       "max_concurrent_cores": 64, "max_ionic_steps_per_job": 80,
                       "automatic_continuation": False, "account_core_quota": 128,
                       "live_queue_headroom_check_required_before_submission": True},
            "timing_references": references,
            "two_job_core_hour_reference_range": [2*min(r["allocated_core_hours_estimate"] for r in references),
                                                  2*max(r["allocated_core_hours_estimate"] for r in references)],
            "timing_is_estimate_not_cost_cap": True,
            "submission_requires_fresh_explicit_authority": True,
            "POTCAR": {"contents_copied": False, "order": ["Fe", "C", "O", "H"],
                       "historical_same_order_sha256": "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85",
                       "remote_reverification_required": True}}
    write_json(output / "plan.json", plan)
    write_json(output / "preparation_state.json", {"status": plan["status"], "submitted": False})
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--custodian", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Refusing to overwrite existing run root: {output}")
    try:
        plan = prepare(output, args.custodian.resolve())
    except Exception as exc:
        if output.exists():
            write_json(output / "preparation_state.json", {"status": "FAILED", "error": str(exc), "submitted": False})
        raise
    print(json.dumps({"status": plan["status"], "jobs": len(plan["cases"]), "submitted": False}))
    raise SystemExit(0 if plan["status"] == "PREPARED" else 1)
