from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    classify_fe110_anchor_site,
    read_poscar,
)
from scripts.artifact_io import sha256_file
from scripts.workflow_geometry import pbc_xy_distance


IONIC_RE = re.compile(
    r"^\s*(\d+)\s+F=\s*([-+0-9.Ee]+)\s+E0=\s*([-+0-9.Ee]+)\s+d E\s*=\s*([-+0-9.Ee]+)"
)
ELECTRONIC_RE = re.compile(r"^\s*(?:DAV|RMM):\s*(\d+)")
TOTEN_RE = re.compile(r"free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)\s+eV")


def parse_oszicar(path: Path, nelm: int) -> dict[str, object]:
    ionic_steps: list[dict[str, float | int]] = []
    current_electronic_iterations = 0
    electronic_iterations: list[int] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            electronic = ELECTRONIC_RE.match(line)
            if electronic:
                current_electronic_iterations = int(electronic.group(1))
                continue
            ionic = IONIC_RE.match(line)
            if ionic:
                electronic_iterations.append(current_electronic_iterations)
                ionic_steps.append(
                    {
                        "step": int(ionic.group(1)),
                        "F_eV": float(ionic.group(2)),
                        "E0_eV": float(ionic.group(3)),
                        "dE_eV": float(ionic.group(4)),
                        "electronic_iterations": current_electronic_iterations,
                    }
                )
                current_electronic_iterations = 0
    return {
        "ionic_steps": len(ionic_steps),
        "last_ionic": ionic_steps[-1] if ionic_steps else None,
        "final_electronic_converged": bool(electronic_iterations and electronic_iterations[-1] < nelm),
        "nelm_exhausted_ionic_steps": [
            index + 1 for index, count in enumerate(electronic_iterations) if count >= nelm
        ],
    }


def parse_outcar(path: Path, movable_indices: list[int]) -> dict[str, object]:
    last_toten = None
    last_forces: list[list[float]] = []
    collecting_forces = False
    force_rows: list[list[float]] = []
    reached_accuracy = False
    normal_footer = False
    fatal_markers: list[str] = []
    markers = ("VERY BAD NEWS", "BRMIX: very serious problems", "ZBRENT: fatal error", "ERROR FEXCF")
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = TOTEN_RE.search(line)
            if match:
                last_toten = float(match.group(1))
            if "reached required accuracy - stopping structural energy minimisation" in line:
                reached_accuracy = True
            if "General timing and accounting informations for this job" in line:
                normal_footer = True
            for marker in markers:
                if marker in line and marker not in fatal_markers:
                    fatal_markers.append(marker)
            if "TOTAL-FORCE (eV/Angst)" in line:
                collecting_forces = True
                force_rows = []
                continue
            if collecting_forces:
                fields = line.split()
                if len(fields) >= 6:
                    try:
                        force_rows.append([float(value) for value in fields[-3:]])
                    except ValueError:
                        pass
                elif force_rows:
                    last_forces = force_rows
                    collecting_forces = False
    if collecting_forces and force_rows:
        last_forces = force_rows
    max_force = None
    max_force_index = None
    if last_forces:
        norms = [(index, float(np.linalg.norm(last_forces[index]))) for index in movable_indices]
        max_force_index, max_force = max(norms, key=lambda item: item[1])
    return {
        "final_TOTEN_eV": last_toten,
        "reached_required_accuracy": reached_accuracy,
        "normal_timing_footer": normal_footer,
        "fatal_markers": fatal_markers,
        "max_movable_force_eV_per_A": max_force,
        "max_movable_force_zero_based_index": max_force_index,
    }


def nearest_fe(structure, atom_index: int) -> tuple[int, float]:
    cart = structure.frac @ structure.cell
    distance, index = min(
        (pbc_xy_distance(structure.cell, cart[atom_index], cart[fe_index]), fe_index)
        for fe_index in range(45)
    )
    return index, distance


def analyze_geometry(contcar: Path, clean_reference: Path) -> dict[str, object]:
    structure = read_poscar(contcar)
    clean = read_poscar(clean_reference)
    if structure.symbols != ["Fe", "C", "H"] or structure.counts != [45, 1, 2]:
        raise ValueError("expected Fe45 C1 H2 in Fe C H order")
    cart = structure.frac @ structure.cell
    c_h_1 = pbc_xy_distance(structure.cell, cart[45], cart[46])
    c_h_2 = pbc_xy_distance(structure.cell, cart[45], cart[47])
    h_h = pbc_xy_distance(structure.cell, cart[46], cart[47])
    bonded = [distance < 1.35 for distance in (c_h_1, c_h_2)]
    if sum(bonded) == 2:
        chemical_identity = "CH2*"
        verdict = "RECLASSIFY"
    elif sum(bonded) == 1 and max(c_h_1, c_h_2) > 1.55:
        chemical_identity = "CH* + H*"
        verdict = "PASS"
    else:
        chemical_identity = "ambiguous_CHx"
        verdict = "NEEDS_REVIEW"
    c_site, c_offset = classify_fe110_anchor_site(structure, structure.frac[45], reference_poscar=clean)
    h1_site, h1_offset = classify_fe110_anchor_site(structure, structure.frac[46], reference_poscar=clean)
    h2_site, h2_offset = classify_fe110_anchor_site(structure, structure.frac[47], reference_poscar=clean)
    c_fe_index, c_fe = nearest_fe(structure, 45)
    h2_fe_index, h2_fe = nearest_fe(structure, 47)
    return {
        "chemical_identity": chemical_identity,
        "verdict": verdict,
        "C_H_distances_A": [c_h_1, c_h_2],
        "H_H_distance_A": h_h,
        "C_site": c_site,
        "C_site_lateral_offset_A": c_offset,
        "H_sites": [h1_site, h2_site],
        "H_site_lateral_offsets_A": [h1_offset, h2_offset],
        "C_nearest_Fe": {"zero_based_index": c_fe_index, "distance_A": c_fe},
        "incoming_H_nearest_Fe": {"zero_based_index": h2_fe_index, "distance_A": h2_fe},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one completed Fe(110) CH+H relaxation.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--initial-poscar", required=True, type=Path)
    parser.add_argument("--clean-reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--nelm", type=int, default=200)
    args = parser.parse_args()
    initial = read_poscar(args.initial_poscar)
    movable = [index for index, flags in enumerate(initial.flags) if flags == ("T", "T", "T")]
    oszicar = parse_oszicar(args.run_dir / "OSZICAR", args.nelm)
    outcar = parse_outcar(args.run_dir / "OUTCAR", movable)
    geometry = analyze_geometry(args.run_dir / "CONTCAR", args.clean_reference)
    result = {
        "schema_version": 1,
        "job_id": args.job_id,
        "scheduler_status": "DONE",
        "electronic": oszicar,
        "ionic": {
            "converged": outcar["reached_required_accuracy"],
            "max_movable_force_eV_per_A": outcar["max_movable_force_eV_per_A"],
            "max_movable_force_zero_based_index": outcar["max_movable_force_zero_based_index"],
        },
        "energy": {"final_TOTEN_eV": outcar["final_TOTEN_eV"], "convention": "fe110_converged_toten_sigma0p20_v1"},
        "geometry": geometry,
        "technical": {
            "normal_timing_footer": outcar["normal_timing_footer"],
            "fatal_markers": outcar["fatal_markers"],
        },
        "files": {
            name: {"sha256": sha256_file(args.run_dir / name), "byte_size": (args.run_dir / name).stat().st_size}
            for name in ("OUTCAR", "OSZICAR", "CONTCAR", "vasp.out")
        },
    }
    result["technical_acceptance"] = bool(
        result["electronic"]["final_electronic_converged"]
        and result["ionic"]["converged"]
        and result["technical"]["normal_timing_footer"]
        and not result["technical"]["fatal_markers"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
