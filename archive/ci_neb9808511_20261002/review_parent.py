"""Bounded review of the completed IS-A to INT06 ordinary NEB; no submission."""
from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from ase.geometry import find_mic

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.path_quality_service import PathQualityRequest, build_path_quality_report
from scripts.neb_agent.utils_structure import pbc_distance, read_poscar
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.review_completed_neb_parent import last_positions
from scripts.aqcat25_calibration import parse_final_outcar

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
BUNDLE = BASE / "h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930"
DEST = BUNDLE / "completed_review_20261002"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
LEFT = BASE / "vasp_nonduplicate_relaxations/IS_A_C2HO_H_adjacent_long_bridge"
RIGHT = BASE / "h_migration1357_valley06_relax_20260909/completed_review_20260910"
ENDPOINT_EVIDENCE = BASE / "h_migration_is_a_int06_path_20260926/plan/endpoint_evidence.json"


def extract() -> None:
    if DEST.exists():
        raise FileExistsError("Review destination exists; inspect it rather than overwrite.")
    DEST.mkdir()
    archives = [BUNDLE / "return_neb9808511_ci_review_20261002.tar.gz",
                BUNDLE / "return_neb9808511_ci_review_extras_20261002.tar.gz"]
    expected = {f"{i:02d}/{name}" for i in range(1, 10)
                for name in ("POSCAR", "CONTCAR", "OUTCAR", "OSZICAR", "XDATCAR")}
    found = set()
    for archive in archives:
        with tarfile.open(archive) as payload:
            members = payload.getmembers()
            for item in members:
                if not item.isfile() or item.name not in expected | {"movie"} or item.name in found:
                    raise ValueError(f"Unexpected/duplicate archive member: {item.name}")
                found.add(item.name)
            payload.extractall(DEST, members=members, filter="data")
    if found != expected | {"movie"}:
        raise ValueError("Incomplete source output archive")
    for name in ("INCAR", "KPOINTS", "POTCAR.spec", "reaction_contract.normalized.json",
                 "path_generation_report.json", "path_review.json"):
        shutil.copyfile(BUNDLE / name, DEST / name)
    for image in ("00", "10"):
        (DEST / image).mkdir()
        shutil.copyfile(BUNDLE / image / "POSCAR", DEST / image / "POSCAR")
    for i in range(1, 10):
        name = f"{i:02d}"
        if sha256_file(DEST / name / "POSCAR") != sha256_file(BUNDLE / name / "POSCAR"):
            raise ValueError(f"Uploaded POSCAR differs from approved input: {name}")


def review() -> None:
    endpoint = load_json_object(ENDPOINT_EVIDENCE)["endpoints"]
    structure_files = []
    rows = []
    energies = []
    histories = []
    endpoint_sources = []
    for i in range(11):
        name = f"{i:02d}"
        path = DEST / name / ("POSCAR" if i in (0, 10) else "CONTCAR")
        structure = read_poscar(path)
        if structure.labels != ["Fe"] * 45 + ["C", "C", "O", "H", "H"]:
            raise ValueError(f"Unexpected atom mapping: {name}")
        outcar = LEFT / "OUTCAR" if i == 0 else RIGHT / "OUTCAR" if i == 10 else DEST / name / "OUTCAR"
        if i in (0, 10):
            side = "initial" if i == 0 else "final"
            if sha256_file(outcar) != endpoint[side]["source_sha256"]:
                raise ValueError(f"Endpoint OUTCAR hash mismatch: {side}")
            endpoint_sources.append(outcar)
        parsed = parse_final_outcar(outcar)
        positions = last_positions(outcar, structure.atom_count)
        _, mismatch = find_mic(positions - structure.frac @ structure.cell, structure.cell, pbc=True)
        mismatch_max = float(np.max(mismatch))
        if mismatch_max > 2e-5:
            raise ValueError(f"Final energy/structure mismatch {name}: {mismatch_max}")
        energy = parsed["final_toten_eV"]
        energies.append(energy)
        histories.append([energy] * 5 if i in (0, 10)
                         else parse_oszicar(DEST / name / "OSZICAR")["energies"][-5:])
        nearest = sorted((pbc_distance(structure, 49, j), j) for j in range(45))[:3]
        distances = {"CC": pbc_distance(structure, 45, 46),
                     "CO": pbc_distance(structure, 46, 47),
                     "original_CH": pbc_distance(structure, 45, 48),
                     "OH": pbc_distance(structure, 47, 49),
                     "new_CH": min(pbc_distance(structure, 45, 49), pbc_distance(structure, 46, 49)),
                     "H50_Fe38": pbc_distance(structure, 49, 37)}
        rows.append({"image": name, "toten_eV": energy,
                     "energy_structure_mic_error_A": mismatch_max,
                     "distances_A": distances,
                     "nearest_Fe_zero_based": [{"index": j, "distance_A": d} for d, j in nearest]})
        structure_files.append(path)
    if any(len(history) != 5 for history in histories):
        raise ValueError("Insufficient genuine final five-step energy history")
    monitor = {
        "highest_image_history": [f"{max(range(11), key=lambda i: histories[i][step]):02d}" for step in range(5)],
        "endpoint_history_role": "Fixed endpoint energies from hash-verified accepted OUTCARs; internal histories are actual OSZICAR records.",
        "source_files": source_file_manifest([ENDPOINT_EVIDENCE, *endpoint_sources,
                                             *(DEST / f"{i:02d}/OSZICAR" for i in range(1, 10))]),
    }
    monitor_path = DEST / "quality_monitor_evidence.json"
    write_json(monitor_path, monitor)
    geometry = diagnose(DEST, ["49"], [str(i) for i in range(18)], THRESHOLDS,
                        expected_interior=9)
    analysis = analyze(DEST, THRESHOLDS, [49])
    quality = build_path_quality_report(PathQualityRequest(
        DEST, (49, 37), (1.8067732026191474, 3.313119570535061),
        ROOT / "configs/neb_path_quality_control_v2.yaml", THRESHOLDS,
        monitor_evidence=monitor_path,
    ))
    write_json(DEST / "neb_path_quality.json", quality)
    write_json(DEST / "parent_chemical_evidence.json", {
        "source_job_id": "9808511", "rows": rows,
        "source_files": source_file_manifest([*structure_files, ENDPOINT_EVIDENCE, *endpoint_sources]),
        "scope": "Completed ordinary path evidence only; no TS or barrier acceptance.",
    })
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), constrained_layout=True)
    axes[0].plot(range(11), np.asarray(energies) - energies[0], "o-")
    axes[0].set_ylabel("Relative electronic energy (eV)")
    axes[0].set_title("Ordinary NEB9808511 final path (not a validated barrier)")
    for key in ("CC", "CO", "original_CH", "OH", "H50_Fe38"):
        axes[1].plot(range(11), [row["distances_A"][key] for row in rows], "o-", label=key)
    axes[1].set_xlabel("Image")
    axes[1].set_ylabel("Minimum-image distance (A)")
    axes[1].legend(ncol=3)
    fig.savefig(DEST / "parent_energy_geometry.png", dpi=130)
    plt.close(fig)
    print("GEOMETRY", geometry["status"], "ANALYSIS", analysis["status"],
          "TECHNICAL", analysis["technically_converged"], "QUALITY", quality["PATH_QUALITY_STATUS"])
    print("QUALITY_REASONS", quality["REASON_CODES"])
    print("IMAGE TOTEN CC CO original_CH OH new_CH H50_Fe38 nearest_Fe(zero-based)")
    for row in rows:
        print(row["image"], f"{row['toten_eV']:.8f}",
              *(f"{x:.4f}" for x in row["distances_A"].values()),
              [item["index"] for item in row["nearest_Fe_zero_based"]])


if __name__ == "__main__":
    extract()
    review()
