"""Analyze collected C2 evidence; produce no acceptance or registry writes."""
from __future__ import annotations

import hashlib
import itertools
from pathlib import Path

from ase.io import read
import numpy as np
import yaml

from archive.fe110_coads_registry_20261021.prepare import geometry
from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import verify_frame
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.prepare_completion_registration import compatibility
from scripts.adsorption.review_completed_batch import compatibility_checks, surface_equivalence
from scripts.adsmind_lite.relaxed_analysis import maximum_slab_displacement, minimum_cross_distance
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import validate_lsf_done_evidence, validate_vasp_relaxation

from .collect import BASE, OUT, ROOT

CLEAN = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
POLICY = ROOT / "configs/adsmind_lite/analysis_rules.yaml"


def production_settings():
    profile = yaml.safe_load((ROOT / "configs/true_fe110_production.yaml").read_text())
    return {**profile["routine_production"]["incar"], "GGA": profile["scope"]["incar_gga"],
            "ENCUT": profile["scope"]["encut_eV"]}


def recorded_scheduler():
    saved = BASE / "adsorption_control_paired_vasp3_20261020_v1/runtime_evidence_20261023T115308Z"
    result = {}
    for path in sorted(saved.glob("scheduler_*.json")):
        row = load_json_object(path)
        if row.get("status") != "DONE":
            continue
        query = row["query"]
        if query["returncode"] or hashlib.sha256(query["stdout"].encode()).hexdigest() != query["stdout_sha256"]:
            raise ValueError("saved scheduler raw binding failed")
        matches = [s.split() for s in query["stdout"].splitlines() if s.split() and s.split()[0] == row["job_id"]]
        if len(matches) != 1 or matches[0][2] != "DONE":
            raise ValueError("saved scheduler ID/status mismatch")
        validate_lsf_done_evidence(row)
        result[row["job_id"]] = {**row, "evidence_path": str(path), "evidence_sha256": sha256_file(path)}
    snapshot = (OUT / "scheduler/bjobs.stdout.txt").read_text()
    receipt = load_json_object(OUT / "scheduler/receipt.json")
    for line in snapshot.splitlines():
        values = line.split()
        if len(values) > 2 and values[0] == "9926807" and values[2] == "DONE":
            result[values[0]] = {"server_alias": "sunboquan-codex", "scheduler": "LSF", "job_id": values[0],
                "status": "DONE", "checked_at": receipt["checked_at"], "source_command": receipt["commands"][0]["command"],
                "source_text": line, "evidence_path": str(OUT / "scheduler/bjobs.stdout.txt"),
                "evidence_sha256": sha256_file(OUT / "scheduler/bjobs.stdout.txt")}
    return result


def final_frame(path):
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 1024 * 1024))
        text = stream.read().decode("utf-8", "strict")
    tail = text.rsplit("TOTAL-FORCE (eV/Angst)", 1)
    if len(tail) != 2:
        raise ValueError("final force table absent from bounded OUTCAR tail")
    rows = []
    for line in tail[1].splitlines()[1:]:
        fields = line.split()
        if len(fields) != 6:
            if rows:
                break
            continue
        try:
            [float(x) for x in fields]
        except ValueError:
            if rows:
                break
            continue
        rows.append(fields)
    return {"positions_A": [[float(x) for x in r[:3]] for r in rows],
            "position_tokens": [r[:3] for r in rows],
            "forces_eV_per_A": [[float(x) for x in r[3:]] for r in rows]}


def analyze_one(directory, slab, policy, production):
    receipt = load_json_object(directory / "collection.json")
    for name, metadata in receipt["remote"]["files"].items():
        if name != "POTCAR" and sha256_file(directory / name) != metadata["sha256"]:
            raise ValueError("collected source changed")
    initial, final = [read_poscar(directory / name) for name in ("POSCAR", "CONTCAR")]
    atoms_initial, atoms = [read(directory / name, format="vasp") for name in ("POSCAR", "CONTCAR")]
    atoms_initial.pbc = atoms.pbc = [True, True, False]
    checks = compatibility_checks(directory, initial, final, slab, {"builder": {"incar": production}}, receipt)
    blockers = []
    try:
        convergence = validate_vasp_relaxation(directory)
    except ValueError as exc:
        convergence = {"status": "FAIL", "reason": str(exc)}
        blockers.append("convergence")
    parsed = parse_final_outcar(directory / "OUTCAR")
    frame = final_frame(directory / "OUTCAR")
    forces = verify_frame(atoms, frame)
    if not np.array_equal(forces, np.asarray(parsed["forces_eV_per_A"])):
        raise ValueError("canonical energy parser and coordinate-bound final frame disagree")
    fmax = float(np.linalg.norm(forces[18:], axis=1).max())
    if fmax > -float(production["EDIFFG"]):
        blockers.append("force_limit")
    if not all(checks.values()):
        blockers.append("compatibility")
    contact = minimum_cross_distance(atoms, list(range(45)), list(range(45, len(atoms))))
    if contact < policy["contact_validation"]["hard_contact_distance_angstrom"]:
        blockers.append("collision")
    displacement = maximum_slab_displacement(atoms_initial, atoms, list(range(45)))
    if displacement > policy["surface_reconstruction"]["maximum_slab_displacement_angstrom"]:
        blockers.append("surface_reconstruction_review")
    try:
        signature = molecular_signature(final)
        intact = signature == molecular_signature(initial)
    except ValueError:
        signature, intact = None, False
    if not intact:
        blockers.append("chemical_identity_review")
    measurements = geometry(final, slab)
    comp = compatibility(receipt["submission"], receipt,
                         {"slab": {"path": str(CLEAN), "sha256": sha256_file(CLEAN)}})
    return {"name": directory.name, "job_id": receipt["job_id"],
        "calculation_id": receipt["submission"]["calculation_id"], "directory": str(directory),
        "collection_sha256": sha256_file(directory / "collection.json"),
        "source_files": {n: v["sha256"] for n, v in receipt["remote"]["files"].items()},
        "formula": receipt["submission"]["formula"], "target_graph": receipt["submission"]["connectivity"],
        "final_signature": signature, "intact": intact, "measurements": measurements,
        "convergence": convergence, "compatibility_checks": checks, "compatibility": comp,
        "fmax_eV_A": fmax, "toten_eV": parsed["final_toten_eV"],
        "ionic_steps": parse_oszicar(directory / "OSZICAR")["ionic_steps"],
        "minimum_Fe_adsorbate_A": contact, "maximum_slab_displacement_A": displacement,
        "force_coordinate_correspondence": True, "blockers": blockers, "scientific_acceptance": False}


def main():
    output = OUT / "analysis.json"
    if output.exists():
        raise FileExistsError(output)
    slab = read_poscar(CLEAN)
    policy = yaml.safe_load(POLICY.read_text())
    production = production_settings()
    schedulers = recorded_scheduler()
    records = []
    for path in sorted((OUT / "sources").glob("*/collection.json")):
        cache = path.parent / "analysis.json"
        if cache.exists():
            row = load_json_object(cache)
            if row["collection_sha256"] != sha256_file(path):
                raise ValueError("analysis cache source changed")
        else:
            row = analyze_one(path.parent, slab, policy, production)
            write_json_exclusive(cache, row)
        records.append(row)
        print(row["name"], "fmax", round(row["fmax_eV_A"], 6), "blockers", row["blockers"], flush=True)
    operations = surface_pose_symmetries(slab)
    comparisons = []
    for first, second in itertools.combinations(records, 2):
        if first["formula"] != second["formula"] or first["final_signature"] != second["final_signature"]:
            continue
        poses = [read_poscar(Path(r["directory"]) / "CONTCAR") for r in (first, second)]
        metrics = surface_equivalence(*poses, slab, operations)
        delta = abs(first["toten_eV"] - second["toten_eV"])
        duplicate = max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= policy["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"] and delta <= policy["duplicate_detection"]["energy_tolerance_ev"]
        comparisons.append({"first": first["name"], "second": second["name"], **metrics,
                            "energy_difference_eV": delta, "duplicate": duplicate})
    write_json_exclusive(output, {"records": records, "scheduler_evidence": schedulers, "comparisons": comparisons,
        "clean_sha256": sha256_file(CLEAN), "policy_sha256": sha256_file(POLICY),
        "analyzer_sha256": sha256_file(Path(__file__)), "scientific_acceptance": False})


if __name__ == "__main__":
    main()
