"""Persist owner-parsed completion and chemistry evidence, including failures."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json

import numpy as np

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature, pose_measurements
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.vasp_result_gate import final_scf_state, read_incar_values
from scripts.workflow_geometry import minimum_image_delta_xy
from .collect import OUT


def review(job):
    folder = OUT / "sources" / job["name"]
    initial, final = (read_poscar(folder / name) for name in ("POSCAR", "CONTCAR"))
    symbols = expanded_symbols(final)
    ads = [i for i, s in enumerate(symbols) if s != "Fe"]
    values = read_incar_values(folder / "INCAR")
    oszicar, outcar = parse_oszicar(folder / "OSZICAR"), parse_outcar(folder / "OUTCAR")
    scf = final_scf_state(oszicar, values, outcar)
    parsed = parse_final_outcar(folder / "OUTCAR")
    forces = np.asarray(parsed["forces_eV_per_A"], float)
    if forces.shape != (len(symbols), 3) or not np.isfinite(forces).all():
        raise ValueError("Incomplete/nonfinite final force block: " + job["name"])
    errors = []
    try:
        same_signature = molecular_signature(initial) == molecular_signature(final)
        final_signature = molecular_signature(final)
    except ValueError as error:
        same_signature, final_signature = False, str(error)
    initial_graph, final_graph = connectivity(initial, ads), connectivity(final, ads)
    finite = np.isfinite(final.frac).all()
    fixed = [i for i, flag in enumerate(initial.flags) if flag == ("F", "F", "F")]
    checks = {
        "cell": bool(np.allclose(initial.cell, final.cell, atol=1e-10, rtol=0)),
        "atom_order": expanded_symbols(initial) == symbols,
        "flags": initial.flags == final.flags,
        "fixed_indices": fixed == list(range(18)),
        "fixed_positions": bool(np.max(np.abs(minimum_image_delta_xy(final.frac[fixed]-initial.frac[fixed]) @ initial.cell)) < 1e-7),
        "GGA": values["GGA"].upper() == "PE", "ENCUT": float(values["ENCUT"]) == 400.0,
        "SIGMA": float(values["SIGMA"]) == .2, "ISMEAR": int(values["ISMEAR"]) == 1,
        "EDIFF": float(values["EDIFF"]) == 1e-5, "EDIFFG": float(values["EDIFFG"]) == -.02,
        "ISPIN": int(values["ISPIN"]) == 2,
    }
    kpoints = (folder / "KPOINTS").read_text().splitlines()
    checks["KPOINTS"] = kpoints[2].lower().startswith("g") and kpoints[3].split() == ["5", "5", "1"]
    fmax = float(np.linalg.norm(forces[18:], axis=1).max())
    for test, passed in (("normal_completion", outcar["normal_completion"]),
                         ("electronic", scf["electronically_converged"]),
                         ("ionic", outcar["reached_required_accuracy"]),
                         ("force", fmax <= .02), ("intended_chemistry", same_signature),
                         ("finite_coordinates", finite), ("compatibility", all(checks.values()))):
        if not passed:
            errors.append(test)
    if outcar["fatal_keywords"]:
        errors.append("fatal_keywords")
    delta = minimum_image_delta_xy(final.frac[:, None] - final.frac[None]) @ final.cell
    distances = np.linalg.norm(delta, axis=2)
    np.fill_diagonal(distances, np.inf)
    return {**job, "directory": str(folder), "normal_completion": outcar["normal_completion"],
            "ionic_converged": outcar["reached_required_accuracy"], "scf": scf,
            "fatal_keywords": outcar["fatal_keywords"], "ionic_steps": oszicar["ionic_steps"],
            "NSW": int(values["NSW"]), "TOTEN_eV": parsed["final_toten_eV"],
            "fmax_movable_eV_A": fmax, "fmax_atom_zero_based": 18+int(np.linalg.norm(forces[18:],axis=1).argmax()),
            "compatibility_checks": checks, "symbols": symbols, "adsorbate_indices": ads,
            "chemistry_same": same_signature, "initial_edges_local": initial_graph,
            "final_edges_local": final_graph, "final_signature": final_signature,
            "min_Fe_adsorbate_A": float(distances[ads, :45].min()),
            "minimum_all_distance_A": float(distances.min()),
            "measurements": pose_measurements(final), "blockers": errors,
            "eligible_for_scientific_review": not errors, "scientifically_accepted": False,
            "source_files": source_file_manifest([folder/name for name in ("POSCAR","CONTCAR","OUTCAR","OSZICAR","INCAR","KPOINTS")])}


def main():
    target = OUT / "completion_geometry_review.json"
    if target.exists():
        raise SystemExit("Saved review exists; reuse it instead of repeating large-file parsing.")
    manifest = load_json_object(OUT / "collection_manifest.json")
    with ThreadPoolExecutor(2) as pool:
        records = list(pool.map(review, manifest["jobs"]))
    write_json_exclusive(target, {"status": "EVIDENCE_PENDING_SCIENTIFIC_REVIEW", "records": records,
                                "source_files": source_file_manifest([OUT/"collection_manifest.json",OUT/"collection_receipt.json",Path(__file__)])})
    for row in records:
        print(json.dumps({key: row[key] for key in ("name","job_id","ionic_steps","fmax_movable_eV_A","chemistry_same","blockers")},ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
