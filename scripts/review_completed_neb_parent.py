"""Review the Fe45-C2-O-H2 O-H NEB with its verified 50-atom mapping; no jobs."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
from ase.geometry import find_mic

from scripts.artifact_io import sha256_file, write_json
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.utils_structure import (
    read_poscar, write_poscar, copy_with_frac, compatible, pbc_distance,
)
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.path_evidence import validate_path_binding


def last_positions(path: Path, count: int) -> np.ndarray:
    latest = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "TOTAL-FORCE (eV/Angst)" not in line:
                continue
            next(handle, None)
            rows = []
            for _ in range(count):
                fields = next(handle, "").split()
                if len(fields) < 6:
                    break
                rows.append([float(x) for x in fields[:3]])
            if len(rows) == count:
                latest = np.asarray(rows)
    if latest is None:
        raise ValueError(f"No complete position/force block: {path}")
    return latest


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "input-bundle", "contract", "destination",
                 "left-outcar", "right-outcar"):
        cli.add_argument("--" + name, type=Path, required=True)
    args = cli.parse_args()
    dest = args.destination.resolve()
    if dest.exists():
        raise ValueError("Review destination already exists")
    source, bundle = args.source.resolve(), args.input_bundle.resolve()
    names = sorted(p.name for p in source.iterdir() if p.is_dir() and p.name.isdigit())
    contract = load_contract(args.contract)
    binding = validate_path_binding(bundle, contract)
    if not binding["valid"]:
        raise ValueError(binding["errors"])
    if contract["reaction_atoms"] != [47, 49]:
        raise ValueError("This bounded reviewer requires the verified O48/H50 mapping")
    fixed = contract["compatibility"]["fixed_atom_indices_zero_based"]
    dest.mkdir(parents=True)
    for name in ("INCAR", "KPOINTS", "POTCAR.spec", "path_generation_report.json"):
        shutil.copy2(bundle / name, dest / name)
    write_json(dest / "reaction_contract.normalized.json", contract)
    structures, rows = [], []
    for index, name in enumerate(names):
        raw_path = source / name / ("CONTCAR" if index not in (0, len(names)-1) else "POSCAR")
        raw = read_poscar(raw_path)
        if raw.labels != ["Fe"] * 45 + ["C", "C", "O", "H", "H"]:
            raise ValueError("This bounded reviewer requires Fe45-C2-O-H2 atom order")
        if structures and compatible(structures[0], raw):
            raise ValueError(f"Identity/cell/fixed-mask mismatch: {name}")
        frac = raw.frac.copy()
        shifts = np.zeros_like(frac)
        if structures:
            delta_cart = (frac - structures[-1].frac) @ raw.cell
            mic, _ = find_mic(delta_cart, raw.cell, pbc=True)
            shifts = np.rint((delta_cart - mic) @ np.linalg.inv(raw.cell))
            frac -= shifts
        normed = copy_with_frac(raw, frac, raw.comment)
        residue, _ = find_mic((normed.frac - raw.frac) @ raw.cell, raw.cell, pbc=True)
        assert np.max(np.abs(residue)) < 1e-8
        if structures:
            assert np.max(np.abs(normed.frac[fixed]-structures[0].frac[fixed])) < 1e-10
        target = dest / name
        target.mkdir()
        write_poscar(target / "POSCAR", normed)
        outcar = args.left_outcar if index == 0 else args.right_outcar if index == len(names)-1 else source / name / "OUTCAR"
        parsed = parse_final_outcar(outcar)
        positions = last_positions(outcar, raw.atom_count)
        _, mismatch = find_mic(positions - raw.frac @ raw.cell, raw.cell, pbc=True)
        mismatch_max = float(np.max(mismatch))
        if mismatch_max > 2e-5:
            raise ValueError(f"Energy/structure mismatch {name}: {mismatch_max}")
        if index not in (0, len(names)-1):
            write_poscar(target / "CONTCAR", normed)
            for filename in ("OUTCAR", "OSZICAR"):
                shutil.copy2(source / name / filename, target / filename)
        pairs = {"OH": [47, 49], "CC": [45, 46], "CO": [46, 47], "original_CH": [45, 48]}
        distances = {key: pbc_distance(normed, *pair) for key, pair in pairs.items()}
        rows.append({"image": name, "source_structure": str(raw_path),
                     "source_structure_sha256": sha256_file(raw_path),
                     "normalized_structure_sha256": sha256_file(target / "POSCAR"),
                     "integer_lattice_shifts": shifts.astype(int).tolist(),
                     "source_outcar": str(outcar.resolve()), "source_outcar_sha256": sha256_file(outcar),
                     "energy_structure_mic_error_A": mismatch_max,
                     "toten_eV": parsed["final_toten_eV"], "distances_A": distances,
                     "max_neighbor_step_A": float(np.linalg.norm((normed.frac-structures[-1].frac) @ raw.cell, axis=1).max()) if structures else 0.0})
        structures.append(normed)
    thresholds = Path("configs/neb_agent/default_thresholds.yaml")
    analysis = analyze(dest, thresholds, contract["reaction_atoms"])
    for row, evidence in zip(analysis["images"], rows, strict=True):
        row["diagnostic_sigma0_energy_eV"] = row["final_energy_eV"]
        row["final_energy_eV"] = evidence["toten_eV"]
        row["relative_energy_eV"] = evidence["toten_eV"] - rows[0]["toten_eV"]
        row["energy_source"] = evidence["source_outcar"]
        row["energy_source_sha256"] = evidence["source_outcar_sha256"]
    energies = [r["toten_eV"] for r in rows]
    peak = int(np.argmax(energies))
    analysis.update(complete_energy_profile=True, maximum_image=names[peak],
                    internal_maximum=0 < peak < len(names)-1,
                    contract_sha256=contract["contract_sha256"],
                    atom_map_sha256=contract["atom_map_sha256"],
                    compatibility_sha256=contract["compatibility_sha256"],
                    path_binding=validate_path_binding(dest, contract),
                    path_reviewed=False, scientifically_valid=False,
                    local_boundary_scope="Fixed internal path boundaries, not relaxed reaction IS/FS; no reportable barrier")
    analysis["path_binding_valid"] = analysis["path_binding"]["valid"]
    geometry = diagnose(dest, [str(i) for i in contract["reaction_atoms"]],
                        [str(i) for i in fixed], thresholds, reaction_pairs=contract["formed_bonds"])
    analysis["geometry_validated"] = geometry["status"] == "PASS"
    write_json(dest / "neb_analysis.json", analysis)
    write_json(dest / "normalization_evidence.json", {
        "method": "ASE find_mic followed by integer lattice translations only",
        "original_input_report_sha256": sha256_file(bundle / "path_generation_report.json"),
        "rows": rows, "peak_image": names[peak], "geometry_status": geometry["status"],
        "scientific_scope": "Local NEB parent review, no final barrier"})
    render_review(dest, structures, names, rows, energies)
    print({"path": str(dest), "geometry": geometry["status"], "peak": names[peak],
           "OH": [round(r["distances_A"]["OH"], 4) for r in rows],
           "energies": energies})


def render_review(dest, structures, names, rows, energies):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 4, figsize=(15, 8))
    colors = {"Fe": "#aeb8c5", "C": "#333333", "O": "#e34848", "H": "#3187c4"}
    for n, atoms in enumerate(structures):
        axis = ax.flat[n]
        cart = atoms.frac @ atoms.cell
        for j, (symbol, pos) in enumerate(zip(atoms.labels, cart)):
            if symbol == "Fe" and pos[2] < cart[:45, 2].max()-0.5:
                continue
            axis.scatter(pos[0], pos[2], s=85 if symbol == "Fe" else 65, color=colors[symbol])
            if j >= 45:
                axis.annotate(f"{symbol}{j+1}", (pos[0], pos[2]), fontsize=8)
        axis.set_title(f"{names[n]}  O-H {rows[n]['distances_A']['OH']:.3f} A")
        axis.set_aspect("equal")
        axis.set_xlabel("x (A)")
        axis.set_ylabel("z (A)")
    ax.flat[7].plot(range(len(names)), np.array(energies)-energies[0], "o-")
    ax.flat[7].set(title="Local NEB TOTEN profile", xlabel="image", ylabel="relative eV (local boundary)")
    fig.tight_layout()
    fig.savefig(dest / "final_path_review.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
