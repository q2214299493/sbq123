"""Review returned GPU1802 path and build ordinary VASP NEB; never submit."""
import os
from pathlib import Path
import shutil
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from ase.geometry import find_mic
from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.dual_model_ml_neb import _load_request
from scripts.ml_candidate_source import load_candidate_path
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.path_evidence import write_path_review_draft
from scripts.vasp_inputs import build_fe110_neb

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
SOURCE = BASE / "h_migration_is_a_int06_path_20260926"
PACKAGE = SOURCE / "gpu_execution_20260926"
RUN = BASE / "h_is_a_int06_gpu1802_neb_20260926"
TOOLS = ROOT / "archive/is_int06_path_20260926/vtst_tools"


def main():
    if RUN.exists():
        raise FileExistsError("Preserve prepared/submitted NEB; no identical rebuild")
    request_path = PACKAGE / "request.json"
    manifest_path = PACKAGE / "output/run2/dual_model_gpu_ml_neb_path_manifest.candidate.json"
    manifest = load_json_object(manifest_path)
    request = _load_request(request_path)
    contract = load_contract(SOURCE / "plan/reaction_contract.normalized.json")
    assert manifest["source_request"]["sha256"] == sha256_file(request_path)
    assert manifest["models"] == request["models"]
    assert manifest["reaction"] == request["reaction"]
    for filename in ("endpoint_check.json", "endpoint_evidence.json"):
        assert load_json_object(SOURCE / "plan" / filename)["status"] != "STOP"
    atoms, _ = load_candidate_path(request, manifest, manifest_path, request_path, method="ml_neb")
    RUN.mkdir()
    rows, adjacent = [], []
    for index, (structure, row) in enumerate(zip(atoms, manifest["images"])):
        name = f"{index:02d}"
        folder = RUN / name
        folder.mkdir()
        shutil.copyfile(manifest_path.parent / row["structure_path"], folder / "POSCAR")
        assert sha256_file(folder / "POSCAR") == row["structure_sha256"]
        structure.pbc = (True, True, False)
        distances = structure.get_all_distances(mic=True)
        np.fill_diagonal(distances, np.inf)
        near = np.argsort(distances[49, :45])[:4]
        rows.append({"image": name, "nearest_Fe_one_based": [int(j + 1) for j in near],
                     "H50_Fe_distances_A": [float(distances[49, j]) for j in near],
                     "OH_A": float(distances[47, 49]), "CH_new_A": float(distances[45, 49]),
                     "CC_A": float(distances[45, 46]), "CO_A": float(distances[46, 47]),
                     "CH_original_A": float(distances[45, 48]),
                     "relative_MatRIS_energy_eV": row["predicted_energy_eV"] - manifest["images"][0]["predicted_energy_eV"]})
        if index:
            raw = structure.positions - atoms[index - 1].positions
            mic, lengths = find_mic(raw, structure.cell, pbc=(True, True, False))
            adjacent.append({"pair": f"{index-1:02d}-{name}", "maximum_atom_step_A": float(lengths.max()),
                             "RMSD_movable_A": float(np.sqrt(np.mean(lengths[18:] ** 2))),
                             "raw_minus_MIC_max_A": float(np.linalg.norm(raw - mic, axis=1).max())})
    assert max(r["raw_minus_MIC_max_A"] for r in adjacent) < 1e-8
    report = {"status": "READY_FOR_GEOMETRY_REVIEW", "method_used": "reviewed_complete_MatRIS_GPU1802_path",
              "interior_images": 9, "image_directories": [r["image"] for r in rows],
              "interpolation_strategy": "no_reinterpolation_exact_returned_ML_snapshots",
              "strategy_source": "user_authorized_complete_ML_path_to_ordinary_VASP_NEB",
              "fingerprint_id": build_fingerprint(contract)["fingerprint_id"],
              **{k: contract[k] for k in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")},
              "source_manifest": {"path": str(manifest_path), "sha256": sha256_file(manifest_path)},
              "source_request": {"path": str(request_path), "sha256": sha256_file(request_path)},
              "retrieval_scope": "Reuse verified local registered endpoints and existing returned path; no new external input",
              "source_structure_hashes": {r["image"]: r["structure_sha256"] for r in manifest["images"]},
              "runtime_restraints": [], "multi_peak_role": "DFT exploration of entire migration, not a single-saddle claim"}
    write_json(RUN / "path_generation_report.json", report)
    shutil.copyfile(SOURCE / "plan/reaction_contract.normalized.json", RUN / "reaction_contract.normalized.json")
    build = build_fe110_neb(RUN, images=9, cores=108)
    write_json(RUN / "input_build.json", build)
    geometry = diagnose(RUN, ["49"], [str(i) for i in range(18)],
                        ROOT / "configs/neb_agent/default_thresholds.yaml", reaction_pairs=[[49, 37]], expected_interior=9)
    assert geometry["status"] != "STOP", geometry["errors"]
    env = os.environ.copy()
    env["PATH"] = "C:/Program Files/Git/usr/bin;" + env["PATH"]
    perl = "C:/Program Files/Git/usr/bin/perl.exe"
    dist_lines = []
    checks = []
    for index in range(10):
        result = subprocess.run([perl, "-I", TOOLS.as_posix(), (TOOLS / "dist.pl").as_posix(),
                                 f"{index:02d}/POSCAR", f"{index+1:02d}/POSCAR"], cwd=RUN,
                                env=env, capture_output=True, text=True, check=True)
        dist_lines.append(f"{index:02d} {index+1:02d} {result.stdout.strip()}")
        checks.append({"command": "dist.pl", "exit_code": result.returncode, "stdout": result.stdout})
    movie = subprocess.run([perl, "-I", TOOLS.as_posix(), (TOOLS / "nebmovie.pl").as_posix(), "0"],
                           cwd=RUN, env=env, capture_output=True, text=True, check=True)
    (RUN / "dist.dat").write_text("\n".join(dist_lines) + "\n", encoding="ascii", newline="\n")
    (RUN / "movie.xyz").write_bytes(b"".join((RUN / r["image"] / "POSCAR.xyz").read_bytes() for r in rows))
    frames = read(RUN / "movie.xyz", index=":")
    assert len(frames) == 11
    assert all(np.allclose(a.positions, b.positions, atol=1e-4, rtol=0) for a, b in zip(atoms, frames))
    write_json(RUN / "work_review_evidence.json", {"status": "PASS_NUMERICAL_GEOMETRY_ONLY",
               "images": rows, "adjacent": adjacent, "geometry_status": geometry["status"],
               "VTST_dist_commands": checks, "nebmovie_pl_0_exit": movie.returncode, "movie_frames": len(frames),
               "models_are_predictions_only": True})
    write_path_review_draft(RUN, RUN / "dist.dat", RUN / "movie.xyz")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    xyz = atoms[0].positions
    for ax, dims, title in zip(axes[:2], [(0, 1), (0, 2)], ["Top view", "Side view"]):
        a, b = dims
        ax.scatter(xyz[36:45, a], xyz[36:45, b], s=220, color="silver")
        for j in range(36, 45):
            ax.annotate(str(j + 1), (xyz[j, a], xyz[j, b]), ha="center", va="center", fontsize=8)
        hp = np.array([x.positions[49] for x in atoms])
        ax.plot(hp[:, a], hp[:, b], "o-", color="tab:blue")
        for index, point in enumerate(hp):
            ax.annotate(f"{index:02d}", (point[a], point[b]), xytext=(0, 8), textcoords="offset points", fontsize=8)
        for j, color in [(45, "black"), (46, "black"), (47, "red"), (48, "gray")]:
            ax.scatter(xyz[j, a], xyz[j, b], s=65, color=color)
        ax.set(title=title, xlabel="x / A", ylabel="y / A" if b == 1 else "z / A")
        ax.set_aspect("equal")
    comparisons = manifest["fixed_path_model_comparison"]["images"]
    axes[2].plot(range(11), [r["primary_relative_energy_eV"] for r in comparisons], "o-", label="MatRIS")
    axes[2].plot(range(11), [r["secondary_relative_energy_eV"] for r in comparisons], "s-", label="AQCat25")
    axes[2].set(xlabel="Image", ylabel="Model-relative energy / eV", title="Predicted profiles, not DFT")
    axes[2].legend()
    fig.suptitle("IS-A -> INT06: GPU1802 exact full path; ordinary VASP NEB candidate")
    fig.tight_layout()
    fig.savefig(RUN / "work_review.png", dpi=150)
    plt.close(fig)
    print({"prepared": str(RUN), "geometry": geometry["status"], "images": 11, "cores": 108})


if __name__ == "__main__":
    main()
