"""One-off provenance for the 2026-07-16 CARE candidate revisions and selected inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    center_score,
    expanded_symbols,
    fe110_rule_defaults,
    identify_top_layer,
    read_poscar,
    write_poscar,
)
from scripts.adsorption.build_fe110_care_isomers import connectivity, review
from scripts.workflow_geometry import minimum_image_delta_xy


REVISIONS = {
    1: "rotate both H atoms +60 deg about C1-C2; lower adsorbate 0.14 A",
    5: "rigid rotation -12 deg about C2 and in-plane axis phi=80 deg; lower 0.06 A",
    7: "turn surface-facing H away; rigid rotation -1 deg about C3 and phi=90 deg; lower 0.14 A",
    8: "rigid rotation -12 deg about C2 and in-plane axis phi=160 deg; lower 0.08 A",
}
SELECTED = (4, 8)
PROVENANCE_SCRIPT = "calculations/fe110_care8_isomers_20260716/provenance/reproduce_revisions_and_selected_inputs.py"
REBUILD_8_RECIPE = (
    "place the terminal CH carbon 2.00 A above a central top Fe; orient the C-C axis "
    "with z-component 0.55 so the C-O-C skeleton points away from the surface while "
    "retaining more than 10 A periodic vacuum; rotate "
    "the terminal H into the surface plane while preserving its C-H length"
)


def rotate(points: np.ndarray, origin: np.ndarray, axis: np.ndarray, degrees: float) -> np.ndarray:
    unit = axis / np.linalg.norm(axis)
    angle = np.deg2rad(degrees)
    shifted = points - origin
    return (
        shifted * np.cos(angle)
        + np.cross(unit, shifted) * np.sin(angle)
        + np.outer(shifted @ unit, unit) * (1.0 - np.cos(angle))
        + origin
    )


def unwrapped_cart(structure: Poscar, anchor: int) -> np.ndarray:
    cart = structure.frac @ structure.cell
    result = cart.copy()
    adsorbate = list(range(45, len(cart)))
    edges = connectivity(structure, adsorbate)
    placed = {anchor}
    while len(placed) < len(adsorbate):
        progress = False
        for first_local, second_local in edges:
            first, second = adsorbate[first_local], adsorbate[second_local]
            if first in placed and second not in placed:
                delta = minimum_image_delta_xy(structure.frac[second] - structure.frac[first])
                result[second] = result[first] + delta @ structure.cell
                placed.add(second)
                progress = True
            elif second in placed and first not in placed:
                delta = minimum_image_delta_xy(structure.frac[first] - structure.frac[second])
                result[first] = result[second] + delta @ structure.cell
                placed.add(first)
                progress = True
        if not progress:
            raise ValueError("adsorbate connectivity graph is disconnected")
    return result


def with_cart(structure: Poscar, cart: np.ndarray, comment: str) -> Poscar:
    frac = cart @ np.linalg.inv(structure.cell)
    frac[:, :2] %= 1.0
    return Poscar(comment, structure.cell.copy(), structure.symbols.copy(), structure.counts.copy(), frac, structure.flags.copy())


def revise(number: int, structure: Poscar) -> Poscar:
    symbols = expanded_symbols(structure)
    adsorbate = list(range(45, len(symbols)))
    cart = unwrapped_cart(structure, 45)

    if number == 1:
        hydrogen = [index for index in adsorbate if symbols[index] == "H"]
        cart[hydrogen] = rotate(cart[hydrogen], cart[45], cart[46] - cart[45], 60.0)
        cart[adsorbate, 2] -= 0.14
    elif number == 5:
        axis = np.array([np.cos(np.deg2rad(80.0)), np.sin(np.deg2rad(80.0)), 0.0])
        cart[adsorbate] = rotate(cart[adsorbate], cart[46], axis, -12.0)
        cart[adsorbate, 2] -= 0.06
    elif number == 7:
        hydrogen = 49
        carbon = 45
        vector = cart[hydrogen] - cart[carbon]
        length = float(np.linalg.norm(vector))
        xy = vector[:2]
        xy *= np.sqrt(1.0 - 0.65**2) * length / np.linalg.norm(xy)
        cart[hydrogen] = cart[carbon] + np.array([xy[0], xy[1], 0.65 * length])
        axis = np.array([0.0, 1.0, 0.0])
        cart[adsorbate] = rotate(cart[adsorbate], cart[47], axis, -1.0)
        cart[adsorbate, 2] -= 0.14
    elif number == 8:
        axis = np.array([np.cos(np.deg2rad(160.0)), np.sin(np.deg2rad(160.0)), 0.0])
        cart[adsorbate] = rotate(cart[adsorbate], cart[46], axis, -12.0)
        cart[adsorbate, 2] -= 0.08
    else:
        raise ValueError(f"no revision recipe for candidate {number}")

    return with_cart(structure, cart, f"{structure.comment} revised candidate {number}")


def rebuild_candidate_8_intact(structure: Poscar) -> Poscar:
    """Build a failure-informed, singly C-bound start without changing its graph."""
    symbols = expanded_symbols(structure)
    if symbols[45:] != ["C", "C", "C", "O", "H", "H"]:
        raise ValueError("candidate 8 must use Fe45 C3 O H2 atom ordering")
    source_edges = connectivity(structure, list(range(45, 51)))
    if source_edges != [(0, 1), (0, 4), (1, 3), (1, 5), (2, 3)]:
        raise ValueError(f"unexpected candidate 8 molecular graph: {source_edges}")

    source_cart = unwrapped_cart(structure, 45)
    relative = source_cart[45:] - source_cart[45]

    source_axis_1 = relative[1] / np.linalg.norm(relative[1])
    source_axis_2 = relative[3] - relative[1]
    source_axis_2 -= source_axis_1 * np.dot(source_axis_2, source_axis_1)
    source_axis_2 /= np.linalg.norm(source_axis_2)
    source_axis_3 = np.cross(source_axis_1, source_axis_2)
    source_frame = np.column_stack((source_axis_1, source_axis_2, source_axis_3))

    target_axis_1 = np.array([np.sqrt(1.0 - 0.55**2), 0.0, 0.55])
    surface_normal = np.array([0.0, 0.0, 1.0])
    target_axis_2 = surface_normal - target_axis_1 * np.dot(surface_normal, target_axis_1)
    target_axis_2 /= np.linalg.norm(target_axis_2)
    target_axis_3 = np.cross(target_axis_1, target_axis_2)
    target_frame = np.column_stack((target_axis_1, target_axis_2, target_axis_3))
    rotation = target_frame @ source_frame.T
    rebuilt_relative = relative @ rotation.T

    cart = structure.frac @ structure.cell
    top = identify_top_layer(structure, fe110_rule_defaults()["z_tolerance"])
    anchor_fe = min(top.tolist(), key=lambda index: center_score(structure.cell, structure.frac[index]))
    anchor_fe_cart = cart[anchor_fe]
    top_z = max(cart[index, 2] for index in range(45))
    anchor = np.array([anchor_fe_cart[0], anchor_fe_cart[1], top_z + 2.00])
    cart[45:] = anchor + rebuilt_relative

    terminal_h_vector = cart[49] - cart[45]
    terminal_h_length = float(np.linalg.norm(terminal_h_vector))
    terminal_h_xy = terminal_h_vector[:2]
    terminal_h_xy *= terminal_h_length / np.linalg.norm(terminal_h_xy)
    cart[49] = cart[45] + np.array([terminal_h_xy[0], terminal_h_xy[1], 0.0])

    return with_cart(
        structure,
        cart,
        "Fe45 C3H2O [C]O[CH][CH] eta1(C_terminal)/top failure-informed intact rebuild",
    )


def write_candidate_8_rebuild(candidate_root: Path, output: Path) -> dict[str, object]:
    candidate_dirs = sorted(candidate_root.glob("08_C3H2O_XXNRTDXE_cfg0"))
    if len(candidate_dirs) != 1:
        raise ValueError("candidate root must contain exactly one 08_C3H2O_XXNRTDXE_cfg0")
    source_path = candidate_dirs[0] / "POSCAR"
    source = read_poscar(source_path)
    rebuilt = rebuild_candidate_8_intact(source)
    geometry = review(source, rebuilt, list(range(45, 51)))
    geometry["site_label"] = "eta1(C_terminal)/top"
    heavy_distances = [row["nearest_fe_angstrom"] for row in geometry["atom_site_details"]]
    recovery_checks = {
        "base_geometry_gate": geometry["verdict"] == "pass" and not geometry["warnings"],
        "terminal_ch_carbon_is_only_close_heavy_atom": (
            heavy_distances[0] <= 2.10 and min(heavy_distances[1:]) >= 3.00
        ),
        "terminal_h_clear_of_surface": geometry["nearest_h_fe_angstrom"] >= 1.90,
        "exact_connectivity_preserved": geometry["checks"]["connectivity_preserved"],
    }
    if not all(recovery_checks.values()):
        raise ValueError(f"candidate 8 intact rebuild failed recovery gate: {recovery_checks}")

    output.mkdir(parents=True, exist_ok=True)
    target_path = output / "POSCAR"
    write_poscar(target_path, rebuilt)
    plan_path = output / "prescreen_plan.json"
    if not plan_path.is_file():
        raise ValueError("mandatory prescreen_plan.json is missing from rebuild output")
    manifest = {
        "version": 1,
        "provenance_script": PROVENANCE_SCRIPT,
        "species": "XXNRTDXEMRDEQZ-UHFFFAOYSA-N*",
        "exact_smiles": "[C]O[CH][CH]",
        "surface": "true Fe(110), Fe45, five layers, bottom 18 Fe fixed",
        "source_poscar": str(source_path),
        "source_poscar_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "prescreen_plan": str(plan_path),
        "prescreen_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "failed_relaxation_evidence": {
            "job_id": "9627285",
            "final_identity": "CO*+C2H2*",
            "use": "orientation-recovery rationale only; final failed geometry is not reused",
        },
        "recipe": REBUILD_8_RECIPE,
        "geometry_review": geometry,
        "recovery_checks": recovery_checks,
        "submitted": False,
        "stability_claim": "none; local relaxation and chemical review are required",
    }
    write_text(output / "rebuild_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def incar(system: str, counts: list[int]) -> str:
    magmom = " ".join(f"{count}*{2.2 if index == 0 else 0.0:.1f}" for index, count in enumerate(counts))
    return f"""SYSTEM = {system}
PREC = Accurate
ENCUT = 400
EDIFF = 1E-5
EDIFFG = -0.02
NELM = 200
NELMIN = 5
NPAR = 4
NSW = 300
IBRION = 2
POTIM = 0.20
ISIF = 2
PSTRESS = 0
GGA = PE
ISPIN = 2
MAGMOM = {magmom}
ISMEAR = 1
SIGMA = 0.20
ALGO = Fast
LREAL = .FALSE.
LASPH = .TRUE.
ISYM = 0
LDIPOL = .FALSE.
LCHARG = .FALSE.
LWAVE = .FALSE.
"""


KPOINTS = """Gamma mesh
0
Gamma
5 5 1
0 0 0
"""

LSF = """#!/bin/sh
APP_NAME=Gkn_normal
NP=32
NP_PER_NODE=32
RUN=\"RAW\"
CURDIR=$PWD
export OMP_NUM_THREADS=1
source /home_gkx/env/intel/intel2016.sh
VASP=$HOME/soft/vasp.5.4.1/bin/vasp_std
cd \"$CURDIR\" || exit 10
TARGET=$(readlink -f POTCAR.link)
test -s \"$TARGET\" || exit 11
ln -sfn \"$TARGET\" POTCAR
rm -f nodelist
for host in $LSB_HOSTS; do echo \"$host\" >> nodelist; done
mpirun -np $NP -machinefile nodelist $VASP > vasp.out 2>&1
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def prepare(candidate_root: Path, run_root: Path) -> dict[str, object]:
    existing_manifest = run_root / "run_manifest.json"
    if existing_manifest.exists():
        existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if any(run.get("job_id") for run in existing.get("runs", [])):
            raise ValueError("run root contains submitted jobs; refusing to overwrite inputs or job records")
    candidates = {int(path.name[:2]): path for path in candidate_root.glob("[0-9][0-9]_*")}
    if set(candidates) != set(range(1, 9)):
        raise ValueError("candidate root must contain exactly candidates 01 through 08")

    revised: dict[int, Poscar] = {}
    records = []
    for number in REVISIONS:
        source_path = candidates[number] / "POSCAR"
        source = read_poscar(source_path)
        target = revise(number, source)
        geometry = review(source, target, list(range(45, sum(source.counts))))
        if geometry["verdict"] != "pass" or geometry["warnings"]:
            raise ValueError(f"candidate {number} revision failed geometry gate: {geometry}")
        revised[number] = target
        output = candidate_root / "revised" / candidates[number].name / "POSCAR"
        write_poscar(output, target)
        records.append(
            {
                "candidate": number,
                "name": candidates[number].name,
                "recipe": REVISIONS[number],
                "source_poscar": str(source_path),
                "revised_poscar": str(output),
                "geometry_review": geometry,
                "submitted": number in SELECTED,
            }
        )

    runs = []
    for number in SELECTED:
        source = revised[number] if number in revised else read_poscar(candidates[number] / "POSCAR")
        run_dir = run_root / candidates[number].name
        write_poscar(run_dir / "POSCAR", source)
        write_text(run_dir / "INCAR", incar(f"Fe45_CARE_candidate_{number:02d}", source.counts))
        write_text(run_dir / "KPOINTS", KPOINTS)
        write_text(run_dir / "POTCAR.spec", "Fe_C_O_H\n")
        write_text(run_dir / "script.lsf", LSF)
        runs.append(
            {
                "candidate": number,
                "name": candidates[number].name,
                "source": "raw" if number == 4 else "revised",
                "local_directory": str(run_dir),
                "nsw": 300,
                "job_id": None,
                "scheduler_state": "NOT_SUBMITTED",
            }
        )

    revision_manifest = {
        "provenance_script": PROVENANCE_SCRIPT,
        "surface": "true Fe(110), Fe45, five layers, bottom 18 Fe fixed",
        "raw_candidates_preserved": True,
        "revision_scope": [1, 5, 7, 8],
        "submission_scope": [4, 8],
        "records": records,
    }
    write_text(candidate_root / "revised" / "revision_manifest.json", json.dumps(revision_manifest, indent=2, ensure_ascii=False) + "\n")
    run_manifest = {
        "provenance_script": PROVENANCE_SCRIPT,
        "surface": "true Fe(110), Fe45, five layers, bottom 18 Fe fixed",
        "purpose": "ordinary VASP relaxation of selected CARE isomers before any coadsorption or NEB work",
        "submission_scope": [4, 8],
        "deferred": "candidates 1, 5, and 7 are revised locally only; candidates 2, 3, and 6 remain unchanged",
        "runs": runs,
    }
    write_text(run_root / "run_manifest.json", json.dumps(run_manifest, indent=2, ensure_ascii=False) + "\n")
    return {"revisions": records, "runs": runs}


def main() -> None:
    parser = argparse.ArgumentParser(description="Revise CARE poses 1/5/7/8 and prepare only Fe45 candidates 4/8 for relaxation.")
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--rebuild-candidate-8", action="store_true")
    parser.add_argument("--rebuild-output", type=Path)
    args = parser.parse_args()
    if args.rebuild_candidate_8:
        if args.rebuild_output is None:
            parser.error("--rebuild-output is required with --rebuild-candidate-8")
        result = write_candidate_8_rebuild(args.candidate_root, args.rebuild_output)
        print(
            "rebuilt=1 submitted=0 verdict="
            f"{result['geometry_review']['verdict']} site={result['geometry_review']['site_label']}"
        )
        return
    if args.run_root is None:
        parser.error("--run-root is required unless --rebuild-candidate-8 is used")
    result = prepare(args.candidate_root, args.run_root)
    print(f"revised={len(result['revisions'])} prepared={len(result['runs'])} submitted=0")


if __name__ == "__main__":
    main()
