"""Prepare the remaining H-migration interval; no model or remote job execution."""
from __future__ import annotations

import csv
import argparse
import os
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib
import numpy as np
from ase.geometry import find_mic

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.utils_structure import copy_with_frac, read_poscar, write_poscar
from scripts.ts_strategy_engine.contract import normalize_contract
from scripts.ts_strategy_engine.workflow import PlanRequest, plan

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
DEST = BASE / "h_migration_is_a_int06_path_20260926"
SOURCE = BASE / "gpu_split_paths_dual_model_20260901/gpu_return_job1357"
TOOLS = ROOT / "archive/is_int06_path_20260926/vtst_tools"
PERL = Path("C:/Program Files/Git/usr/bin/perl.exe")


def mic(vector, cell):
    return find_mic(vector, cell, pbc=[True, True, False])[0]


def distance(structure, left, right):
    cart = structure.frac @ structure.cell
    return float(np.linalg.norm(mic(cart[right] - cart[left], structure.cell)))


def verify_reference(manifest):
    for image in manifest["images"]:
        if sha256_file(SOURCE / image["structure_path"]) != image["structure_sha256"]:
            raise ValueError("GPU1357 source structure hash mismatch")


def main():
    if DEST.exists():
        raise ValueError("Destination exists; inspect it rather than overwrite or retry")
    source_manifest = SOURCE / "dual_model_gpu_ml_neb_path_manifest.candidate.json"
    manifest = load_json_object(source_manifest)
    verify_reference(manifest)
    first_contract = load_json_object(BASE / "gpu_split_paths_dual_model_20260901/segment_01_IS_A_to_MID/contract.normalized.json")
    second_contract = load_json_object(BASE / "h_migration_int06_to_mid_path_20260910/plan/reaction_contract.normalized.json")
    initial_source = BASE / "vasp_nonduplicate_relaxations/IS_A_C2HO_H_adjacent_long_bridge/CONTCAR"
    final_source = BASE / "h_migration1357_valley06_relax_20260909/completed_review_20260910/CONTCAR"
    expected = ["6800e98e36e32c09bc7c2514f52998e641416dca4d3b62a4aa0acc95ad50a2ed",
                "2b53dedc909c678c2e8f7f1e4fc9643c6f87e78e26c8a818b8d9c8dfa7c73029"]
    for path, digest in zip((initial_source, final_source), expected):
        if sha256_file(path) != digest:
            raise ValueError("Registered endpoint hash changed")
    start, end = read_poscar(initial_source), read_poscar(final_source)
    h = first_contract["reaction_atoms"][0]
    if h != 49 or start.labels[h] != "H" or len(start.labels) != 50:
        raise ValueError("This case-specific script requires verified mapped H49/50 atoms")
    if start.labels != end.labels or not np.allclose(start.cell, end.cell, atol=1e-10, rtol=0):
        raise ValueError("Endpoint order/cell mismatch")
    fixed = [i for i, flags in enumerate(start.flags) if all(x == "F" for x in flags)]
    if fixed != list(range(18)) or start.flags != end.flags:
        raise ValueError("Fixed mask mismatch")
    if np.max(np.abs(mic((end.frac[fixed] - start.frac[fixed]) @ start.cell, start.cell))) > 1e-10:
        raise ValueError("Fixed-layer endpoint drift")
    DEST.mkdir(parents=True)
    shutil.copyfile(initial_source, DEST / "IS.vasp")
    shutil.copyfile(final_source, DEST / "FS.vasp")
    waypoint_dir = DEST / "waypoints"
    waypoint_dir.mkdir()
    reference_images = [manifest["images"][i] for i in (2, 3, 4)]
    h_positions = [start.frac[h] @ start.cell]
    for item in reference_images:
        point = read_poscar(SOURCE / item["structure_path"])
        h_positions.append(h_positions[-1] + mic(point.frac[h] @ start.cell - h_positions[-1], start.cell))
    h_positions.append(h_positions[-1] + mic(end.frac[h] @ end.cell - h_positions[-1], start.cell))
    lengths = np.linalg.norm(np.diff(h_positions, axis=0), axis=1)
    progress = np.r_[0.0, np.cumsum(lengths)] / sum(lengths)
    endpoint_delta = mic((end.frac - start.frac) @ start.cell, start.cell) @ np.linalg.inv(start.cell)
    waypoints = []
    for i, item in enumerate(reference_images, 1):
        frac = start.frac + progress[i] * endpoint_delta
        frac[h] = h_positions[i] @ np.linalg.inv(start.cell)
        frac[fixed] = start.frac[fixed]
        waypoint = waypoint_dir / f"reference1357_image{item['image']}_H_only.vasp"
        write_poscar(waypoint, copy_with_frac(start, frac, "Proposed H-only waypoint; other atoms endpoint-blended"))
        waypoints.append(waypoint)
    raw_contract = {k: v for k, v in first_contract.items() if not k.endswith("sha256")}
    raw_contract.update(
        reaction_id="fe110_c2ho_h_migration_ISA9725473_to_INT06_9748648",
        product_id="c2ho_plus_h_int06_job9748648",
        endpoints={"initial": first_contract["endpoints"]["initial"], "final": second_contract["endpoints"]["initial"]},
        waypoint_files=[str(x.resolve()) for x in waypoints],
        site_changes=["h49:fe43_fe36_fe42_to_fe40_fe39_fe37_via_fe42_fe40"],
        reaction_coordinates=[{"name": "H50_to_arriving_Fe38", "kind": "distance", "atoms": [h, 37],
                               "important_interval_A": sorted([distance(start, h, 37), distance(end, h, 37)]), "role": "primary"}],
        retrieval_constraints={"accepted_local_inputs_only": True,
                               "source_gate": str(BASE / "retrieval/transferability_review.json"),
                               "decision": "REUSE_VERIFIED_LOCAL_ENDPOINTS_AND_H_ONLY_REFERENCE_CORRIDOR",
                               "reason": "No new external structure/parameter; source1357 supplies candidate H corridor only. Its low point02 is not an accepted DFT intermediate."},
    )
    contract = normalize_contract(raw_contract)
    contract_path = write_json(DEST / "reaction_contract.normalized.json", contract)
    write_json(DEST / "preparation_sources.json", {
        "initial": {"path": str(initial_source), "sha256": expected[0]},
        "final": {"path": str(final_source), "sha256": expected[1]},
        "reference_manifest": {"path": str(source_manifest), "sha256": sha256_file(source_manifest)},
        "method": "Three H-only surface-corridor waypoints, smooth full-coordinate endpoint blending, segmented IDPP; no physical restraints",
        "submitted": False, "gpu_model_executed": False, "reference_low_point_status": "unverified_ML_minimum_not_endpoint",
    })
    strategy = plan(PlanRequest(DEST / "IS.vasp", DEST / "FS.vasp", contract_path, DEST / "plan",
                                ROOT / "data/project_registry.sqlite3", ROOT / "configs/ts_strategy_engine/families.yaml",
                                ROOT / "configs/neb_agent/default_thresholds.yaml", initialize_path=True, images=9))
    if strategy["status"].startswith("STOP"):
        raise ValueError("Canonical planning stopped; preserve all diagnostic files")
    review_path(strategy)


def review_path(strategy):
    start = read_poscar(DEST / "IS.vasp")
    h = 49
    fixed = list(range(18))
    path = DEST / "plan/path_candidate"
    frames = [read_poscar(path / f"{i:02d}/POSCAR") for i in range(11)]
    rows, raw_steps, branch_errors = [], [], []
    for i, frame in enumerate(frames):
        cart = frame.frac @ frame.cell
        d = np.linalg.norm(mic(cart[:45] - cart[h], frame.cell), axis=1)
        neighbors = np.argsort(d)[:3]
        step = np.zeros((50, 3)) if i == 0 else mic((frame.frac - frames[i - 1].frac) @ frame.cell, frame.cell)
        if i:
            raw = (frame.frac - frames[i - 1].frac) @ frame.cell
            raw_steps.append(float(np.max(np.linalg.norm(raw, axis=1))))
            branch_errors.append(float(np.max(np.abs(raw - step))))
        rows.append({"image": f"{i:02d}", "H50_x_A": float(cart[h, 0]), "H50_y_A": float(cart[h, 1]),
                     "H50_z_A": float(cart[h, 2]), "H50_nearest_Fe_1based": "/".join(str(x + 1) for x in neighbors),
                     "H50_nearest_Fe_distances_A": "/".join(f"{d[x]:.6f}" for x in neighbors),
                     "O48_H50_A": distance(frame, 47, h), "C46_C47_A": distance(frame, 45, 46),
                     "C47_O48_A": distance(frame, 46, 47), "C46_H49_A": distance(frame, 45, 48),
                     "neighbor_movable_RMSD_A": float(np.sqrt(np.mean(np.sum(step[18:] ** 2, axis=1)))),
                     "neighbor_max_atom_step_A": float(np.max(np.linalg.norm(step, axis=1)))})
    table = DEST / "geometry_table.csv"
    if table.exists():
        with table.open(encoding="utf-8", newline="") as stream:
            previous = list(csv.DictReader(stream))
        if previous != [{k: str(v) for k, v in row.items()} for row in rows]:
            raise ValueError("Existing geometry table does not match current images")
    else:
        with table.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    vtst_records = []
    tool_env = os.environ.copy()
    tool_env["PATH"] = "C:/Program Files/Git/usr/bin;" + tool_env["PATH"]
    for i in range(10):
        run = subprocess.run([str(PERL), "-I", TOOLS.as_posix(), (TOOLS / "dist.pl").as_posix(), (path / f"{i:02d}/POSCAR").as_posix(), (path / f"{i + 1:02d}/POSCAR").as_posix()], capture_output=True, text=True, encoding="utf-8", errors="replace", env=tool_env, cwd=path, check=True)
        vtst_records.append({"left": f"{i:02d}", "right": f"{i+1:02d}", "exit_code": run.returncode, "stdout": run.stdout})
    run = subprocess.run([str(PERL), "-I", TOOLS.as_posix(), (TOOLS / "nebmovie.pl").as_posix(), "0"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=tool_env, cwd=path, check=True)
    write_json(DEST / "vtst_preparation_checks.json", {"dist_pl": vtst_records, "nebmovie_pl_0": {"exit_code": run.returncode, "stdout": run.stdout},
               "tool_sources": [{"path": str(TOOLS / name), "sha256": sha256_file(TOOLS / name)} for name in ("dist.pl", "nebmovie.pl", "Vasp.pm", "pos2con.pl", "con2xyz.pl")]})
    write_json(DEST / "exact_mic_checks.json", {"pbc": [True, True, False], "max_raw_atom_step_A": max(raw_steps),
               "max_raw_minus_exact_mic_A": max(branch_errors), "fixed_layer_max_cartesian_drift_A": max(float(np.max(np.abs((x.frac[fixed] - start.frac[fixed]) @ start.cell))) for x in frames),
               "all_frames": [{"image": row["image"], "path": str(path / row["image"] / "POSCAR"), "sha256": sha256_file(path / row["image"] / "POSCAR")} for row in rows]})
    plot(frames, rows, h)
    print(json.dumps({"package": str(DEST), "strategy_status": strategy["status"], "geometry_status": strategy["path_geometry"]["status"],
                      "total_frames": len(frames), "max_atom_step_A": max(raw_steps), "max_branch_error_A": max(branch_errors), "submitted": False}))


def plot(frames, rows, h):
    start = frames[0]
    cart = start.frac @ start.cell
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), constrained_layout=True)
    for shift_a in (-1, 0, 1):
        for shift_b in (-1, 0, 1):
            fe = cart[36:45] + shift_a * start.cell[0] + shift_b * start.cell[1]
            axes[0].scatter(fe[:, 0], fe[:, 1], s=145, color="#bcc5cf", edgecolors="#66717d")
            for i, pos in enumerate(fe, 37):
                if 1 < pos[0] < 7 and -0.2 < pos[1] < 6.3:
                    axes[0].text(pos[0], pos[1] + 0.15, f"Fe{i}", ha="center", fontsize=8)
    hp = np.array([x.frac[h] @ x.cell for x in frames])
    axes[0].plot(hp[:, 0], hp[:, 1], "o-", color="#c83f45", lw=2, label="H50 proposed migration")
    for i, pos in enumerate(hp):
        axes[0].annotate(f"{i:02d}", pos[:2], xytext=(4, 5), textcoords="offset points", fontsize=8)
    axes[0].set(xlim=(1, 7), ylim=(-0.2, 6.3), xlabel="x (A)", ylabel="y (A)", title="Top layer / H50 path (1-based labels)")
    axes[0].set_aspect("equal")
    axes[0].legend(fontsize=8)
    axes[1].plot(range(len(rows)), [x["H50_z_A"] for x in rows], "o-", label="H50 height")
    axes[1].axhline(float(np.mean(cart[36:45, 2])), color="#66717d", linestyle="--", label="mean top Fe height")
    axes[1].set(xlabel="Image", ylabel="z (A)", title="H remains in surface adsorption corridor")
    axes[1].legend(fontsize=8)
    fig.savefig(DEST / "path_review.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-existing", action="store_true", help="Resume read-only structural checks/exports without rebuilding images")
    args = parser.parse_args()
    try:
        if args.review_existing:
            review_path(load_json_object(DEST / "plan/ts_strategy.json"))
        else:
            main()
    except Exception as exc:
        if DEST.is_dir() and not (DEST / "preparation_failure.json").exists():
            write_json(DEST / "preparation_failure.json", {"status": "FAILED_PREPARATION", "error_type": type(exc).__name__, "error": str(exc), "submitted": False})
        raise
