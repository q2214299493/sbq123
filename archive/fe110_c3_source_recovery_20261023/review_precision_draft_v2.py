"""Review recovered C3 outputs with existing scientific parsers; no execution."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from ase.geometry import find_mic
from ase.io import read

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.review_completed_batch import compatibility_checks
from scripts.adsmind_lite.relaxed_analysis import connectivity_change, connectivity_edges, minimum_cross_distance
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.vasp_result_gate import final_scf_status, validate_vasp_relaxation

from .collect import CASES, FILES, OUTPUT


def candidate_status(*, technical: bool, ionic: bool, unchanged_graph: bool, fmax: float) -> dict:
    return {"raw_force_label_candidate": technical,
            "low_force_candidate_below_0p05": technical and fmax <= .05,
            "intact_C3_anchor_candidate": technical and ionic and unchanged_graph and fmax <= .02,
            "scientific_acceptance": False, "training_authorized": False}


def fragments(atoms, edges: list) -> list[str]:
    remaining, components = set(range(len(atoms) - 45)), []
    while remaining:
        group, pending = set(), {min(remaining)}
        while pending:
            current = pending.pop()
            group.add(current)
            neighbors = {b if a == current else a for a, b in edges if current in (a, b)}
            pending.update(neighbors - group)
        remaining.difference_update(group)
        components.append(atoms[[45 + index for index in sorted(group)]].get_chemical_formula())
    return sorted(components)


def last_force_tokens(path: Path, count: int) -> list[list[str]]:
    latest = None
    with path.open(encoding="utf-8", errors="strict") as handle:
        iterator = iter(handle)
        for line in iterator:
            if "TOTAL-FORCE (eV/Angst)" in line:
                next(iterator)
                latest = [next(iterator).split() for _ in range(count)]
    if latest is None or any(len(row) != 6 for row in latest):
        raise ValueError("incomplete final raw force table")
    return latest


def rounding_bounds(tokens: list[list[str]]) -> np.ndarray:
    bounds = []
    for row in tokens:
        widths = []
        for token in row[:3]:
            mantissa, *exponent = token.lower().split("e")
            digits = len(mantissa.split(".")[1]) if "." in mantissa else 0
            widths.append(.5 * 10. ** ((int(exponent[0]) if exponent else 0) - digits))
        bounds.append(float(np.linalg.norm(widths)))
    return np.asarray(bounds)


def review(case: dict, clean, expected: dict, rules: dict) -> dict:
    directory = OUTPUT / case["job_id"]
    receipt = load_json_object(directory / "collection.json")
    for name in FILES:
        if sha256_file(directory / name) != receipt["remote"][name]["sha256"]:
            raise ValueError("recovered file hash changed: " + name)
    initial, final = [read_poscar(directory / name) for name in ("POSCAR", "CONTCAR")]
    first, last = [read(directory / name, format="vasp") for name in ("POSCAR", "CONTCAR")]
    first.pbc = last.pbc = [True, True, False]
    parsed = parse_final_outcar(directory / "OUTCAR")
    out = parse_outcar(directory / "OUTCAR")
    osz = parse_oszicar(directory / "OSZICAR")
    scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
    forces = np.asarray(parsed["forces_eV_per_A"])
    ase_out = read(directory / "OUTCAR", format="vasp-out", index=-1)
    force_match = forces.shape == (len(last), 3) and np.isfinite(forces).all() and np.array_equal(
        forces, ase_out.get_forces(apply_constraint=False))
    _, deltas = find_mic(ase_out.positions - last.positions, last.cell, [True, True, False])
    tokens = last_force_tokens(directory / "OUTCAR", len(last))
    raw_positions = np.asarray([[float(v) for v in row[:3]] for row in tokens])
    raw_forces = np.asarray([[float(v) for v in row[3:]] for row in tokens])
    if not np.array_equal(raw_positions, ase_out.positions) or not np.array_equal(raw_forces, forces):
        raise ValueError("raw/canonical/ASE force table disagreement")
    coordinate_bound = rounding_bounds(tokens)
    coordinate_match = bool(np.all(deltas <= coordinate_bound + 1e-8))
    fmax = float(np.max(np.linalg.norm(forces[18:], axis=1)))
    ads = list(range(45, len(last)))
    edges = [connectivity_edges(atoms, ads, rules["connectivity"]["covalent_radius_scale"],
                                rules["connectivity"]["minimum_bond_distance_angstrom"]) for atoms in (first, last)]
    chemistry = connectivity_change(len(ads), edges[0], edges[1])
    try:
        signature_match = molecular_signature(initial) == molecular_signature(final)
    except ValueError:
        signature_match = False
    adapter = {"remote": {"files": receipt["remote"]},
               "submission": {"potcar_sha256": "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"}}
    compatibility = compatibility_checks(directory, initial, final, clean, {"builder": {"incar": expected}}, adapter)
    try:
        convergence = {"passed": True, **validate_vasp_relaxation(directory)}
    except ValueError as error:
        convergence = {"passed": False, "reason": str(error)}
    mag = osz["magnetization_history_muB"]
    moment_valid = bool(mag and np.isfinite(mag).all())
    minimum_contact = minimum_cross_distance(last, list(range(45)), ads)
    technical = bool(all(compatibility.values()) and scf["electronically_converged"] and out["normal_completion"]
                     and not out["fatal_keywords"] and force_match and coordinate_match and moment_valid
                     and minimum_contact >= rules["contact_validation"]["hard_contact_distance_angstrom"])
    unchanged = not chemistry["connectivity_changed"] and signature_match
    moments = out["local_magnetization_last_muB"]
    return {"job_id": case["job_id"], "case": case["name"], "source_directory": str(directory),
            "collection_sha256": sha256_file(directory / "collection.json"), "ionic_steps": osz["ionic_steps"],
            "normal_completion": out["normal_completion"], "final_SCF": scf, "relaxation_gate": convergence,
            "fmax_movable_eV_A": fmax, "adsorbate_fmax_eV_A": float(np.max(np.linalg.norm(forces[45:], axis=1))),
            "final_TOTEN_eV_metadata_only": parsed["final_toten_eV"], "reportable_energy": False,
            "canonical_ASE_raw_force_match": bool(force_match), "force_CONTCAR_coordinate_match": coordinate_match,
            "force_CONTCAR_max_difference_A": float(np.max(deltas)), "compatibility_checks": compatibility,
            "OUTCAR_position_rounding_bound_max_A": float(np.max(coordinate_bound)),
            "minimum_Fe_adsorbate_A": minimum_contact, "chemistry": chemistry, "signature_match": signature_match,
            "initial_edges_local_0based": edges[0], "final_edges_local_0based": edges[1],
            "final_fragment_formulas_geometry_diagnostic": fragments(last, edges[1]),
            "magnetism": {"total_last_muB": mag[-1] if mag else None,
                          "total_range_muB": [min(mag), max(mag)] if mag else None,
                          "local_moment_count": len(moments), "local_moments_complete": len(moments) == len(last),
                          "global_magnetic_minimum_verified": False,
                          "scope": "No LORBIT local-moment table in legacy output; total moment and input branch only."},
            **candidate_status(technical=technical, ionic=convergence["passed"], unchanged_graph=unchanged, fmax=fmax)}


if __name__ == "__main__":
    production = yaml.safe_load(Path("configs/true_fe110_production.yaml").read_text(encoding="utf-8"))
    expected = {**production["routine_production"]["incar"],
                "GGA": production["scope"]["incar_gga"], "ENCUT": production["scope"]["encut_eV"]}
    rules = yaml.safe_load(Path("configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    clean = read_poscar(Path("calculations/true_fe110_clean_20260629/POSCAR"))
    rows = []
    for case in CASES:
        result = review(case, clean, expected, rules)
        write_json_exclusive(OUTPUT / case["job_id"] / "review_precision_v2.json", result)
        rows.append(result)
        print({key: result[key] for key in ("job_id", "fmax_movable_eV_A", "ionic_steps", "intact_C3_anchor_candidate")}, flush=True)
    sources = [Path(__file__), Path(__file__).with_name("collect.py"), Path("configs/true_fe110_production.yaml"),
               Path("configs/adsmind_lite/analysis_rules.yaml"), Path("scripts/vasp_result_gate.py"),
               Path("scripts/aqcat25_calibration.py"), Path("scripts/neb_agent/utils_vasp.py"),
               Path("scripts/adsorption/review_completed_batch.py")]
    write_json_exclusive(OUTPUT / "review_summary_precision_v2.json", {"cases": rows, "source_files": source_file_manifest(sources),
                         "supersedes": "review_summary.json: initial diagnostic assumed six decimal places; actual raw table uses five.",
                         "new_calculations": False, "model_or_training_run": False, "scheduler_state_rechecked": False})
