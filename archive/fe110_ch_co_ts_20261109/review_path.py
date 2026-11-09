"""Measure and visualize the proposed seven-frame path without a calculator."""
from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from ase.io import read

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/review_ready_v2"
PATH = BASE / "plan/path_candidate"


def main():
    report = BASE / "path_numeric_review.json"
    if report.exists():
        raise SystemExit("Review evidence already exists; no overwrite.")
    roles = load_json_object(BASE / "endpoint_provenance.json")["identity"]
    c1, c2, oxygen, hydrogen = (roles[k] for k in ("CH_carbon", "CO_carbon", "O", "H"))
    ads = [c1, c2, oxygen, hydrogen]
    names = [f"{i:02d}" for i in range(7)]
    poses = [read_poscar(PATH / name / "POSCAR") for name in names]
    perl = "C:/Program Files/Git/usr/bin/perl.exe"
    tool = ROOT / "archive/vtst_review_job9745217/dist.pl"
    dist_rows = []
    for left, right in zip(names, names[1:]):
        result = subprocess.run([perl, tool.as_posix(), (PATH / left / "POSCAR").as_posix(),
                                 (PATH / right / "POSCAR").as_posix()],
                                check=True, capture_output=True, text=True)
        dist_rows.append({"left": left, "right": right, "distance_A": float(result.stdout.strip())})
    dist_record = {"tool": str(tool), "sha256": sha256_file(tool), "pairs": dist_rows}
    dist_file = BASE / "dist.json"
    if dist_file.exists():
        if load_json_object(dist_file) != dist_record:
            raise ValueError("Existing dist evidence does not match current path/tool.")
    else:
        write_json_exclusive(dist_file, dist_record)
    # This unmodified VTST version retains 'movie' and per-image POSCAR.xyz;
    # it deliberately removes movie.xyz when its default xyzflag is zero.
    frames = [read(PATH / name / "POSCAR.xyz", format="xyz") for name in names]
    if len(frames) != len(poses) or any(len(frame) != len(poses[0].frac) for frame in frames):
        raise ValueError("VTST movie frame/atom count mismatch.")
    rows = []
    for index, (name, pose) in enumerate(zip(names, poses, strict=True)):
        if pose.flags != poses[0].flags or not np.array_equal(pose.cell, poses[0].cell):
            raise ValueError("Image cell or fixed flags changed.")
        delta = minimum_image_delta_xy(pose.frac[:, None] - pose.frac[None]) @ pose.cell
        distances = np.linalg.norm(delta, axis=2)
        np.fill_diagonal(distances, np.inf)
        fixed_shift = float(np.linalg.norm((pose.frac[:18] - poses[0].frac[:18]) @ pose.cell, axis=1).max())
        row = {"image": name, "C_C_A": float(distances[c1, c2]),
               "C_O_A": float(distances[c2, oxygen]), "C_H_A": float(distances[c1, hydrogen]),
               "min_any_distance_A": float(distances.min()),
               "min_ads_Fe_A": float(distances[ads, :45].min()), "fixed_shift_A": fixed_shift,
               "ads_edges_local": connectivity(pose, ads),
               "max_atom_step_from_previous_A": 0.0 if index == 0 else float(np.linalg.norm(
                   (pose.frac - poses[index-1].frac) @ pose.cell, axis=1).max())}
        rows.append(row)
    if any(row["fixed_shift_A"] > 1e-8 for row in rows):
        raise ValueError("Fixed atoms drifted.")
    if any((0, 3) not in row["ads_edges_local"] or (1, 2) not in row["ads_edges_local"] for row in rows):
        raise ValueError("C-H or C-O backbone lost; review instead of submitting.")
    write_json_exclusive(report, {"status": "NUMERIC_REVIEW_ONLY_USER_APPROVAL_PENDING", "rows": rows,
                                 "movie": {"path": str(PATH / "movie"),
                                           "sha256": sha256_file(PATH / "movie"), "frames": len(frames)},
                                 "energies_or_forces_computed": False})
    render(poses, rows, ads)
    for row in rows:
        print(row["image"], *(f"{row[k]:.6f}" for k in
              ("C_C_A", "C_O_A", "C_H_A", "min_ads_Fe_A", "max_atom_step_from_previous_A")))


def render(poses, rows, ads):
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(2, len(poses), figsize=(18, 5.8))
    colors = ["#202c39", "#202c39", "#dc2626", "#38bdf8"]
    sizes = [90, 90, 100, 60]
    for col, (pose, row) in enumerate(zip(poses, rows, strict=True)):
        cart = pose.frac @ pose.cell
        top = np.argsort(cart[:45, 2])[-9:]
        surface = np.argsort(cart[:45, 2])[-18:]
        for tx in (-1, 0, 1):
            for ty in (-1, 0, 1):
                shift = np.array([tx, ty, 0]) @ pose.cell
                atoms = cart + shift
                axes[0, col].scatter(atoms[top, 0], atoms[top, 1], s=115, c="#a1a1aa", alpha=0.65)
                axes[1, col].scatter(atoms[surface, 0], atoms[surface, 2], s=75, c="#a1a1aa", alpha=0.4)
        for r, dims in enumerate(((0, 1), (0, 2))):
            ax = axes[r, col]
            for (a, b), style in (((0, 3), "-"), ((1, 2), "-"), ((0, 1), "--")):
                ax.plot(cart[[ads[a], ads[b]], dims[0]], cart[[ads[a], ads[b]], dims[1]], style,
                        color="#475569", linewidth=1.5, zorder=4)
            for atom, color, size in zip(ads, colors, sizes, strict=True):
                ax.scatter(cart[atom, dims[0]], cart[atom, dims[1]], c=color, s=size,
                           edgecolors="white", linewidths=0.8, zorder=5)
            ax.set_xlim(4.2, 9.5)
            ax.set_ylim((0.8, 4.8) if r == 0 else (14.0, 19.0))
            ax.set_aspect("equal")
            ax.grid(alpha=0.12)
            if col == 0:
                ax.set_ylabel("y / A" if r == 0 else "z / A")
            ax.set_xlabel("x / A")
        axes[0, col].set_title(f"{row['image']}  C-C {row['C_C_A']:.3f} A", fontsize=10)
    fig.suptitle("Fe(110): CH* + CO* -> CH-C-O* | Geometry/IDPP candidate, NOT a calculated TS\n"
                 "Grey Fe; black C; red O; blue H. Dashed: forming C-C bond. No GPU/DFT job submitted.", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .89))
    fig.savefig(BASE / "path_review.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
