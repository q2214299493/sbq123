"""Lossless force-only export for a bounded NequIP comparison;never trains."""
from pathlib import Path

import numpy as np
from ase.db import connect
from ase.io import read
from ase.io.extxyz import key_val_dict_to_str

from scripts.adsorption.force_finetune import load_manifest
from scripts.artifact_io import sha256_file, write_json_exclusive


def write_frame(handle, atoms, weights, info):
    """ASE's default eight-decimal XYZ is insufficient for exact label replay."""
    forces = atoms.get_forces(apply_constraint=False)
    weights = np.asarray(weights, dtype=float)
    if forces.shape != (len(atoms), 3) or weights.shape != (len(atoms),):
        raise ValueError("force/weight shape mismatch")
    if not np.isfinite(forces).all() or not np.isfinite(weights).all() or np.any(weights < 0):
        raise ValueError("nonfinite force or invalid weight")
    fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
    free = sorted(set(range(len(atoms))) - set(fixed))
    if not free or np.any(weights[fixed] != 0) or np.any(weights[free] <= 0) or not np.isclose(weights.sum(), 1., rtol=0, atol=1e-12):
        raise ValueError("normalized movable-atom mask changed")
    header = {**info, "Lattice": atoms.cell.array.T, "pbc": atoms.pbc,
        "Properties": "species:S:1:pos:R:3:forces:R:3:force_loss_weights:R:1"}
    handle.write(str(len(atoms)) + "\n" + key_val_dict_to_str(header) + "\n")
    for symbol, xyz, force, weight in zip(atoms.get_chemical_symbols(), atoms.positions, forces, weights, strict=True):
        handle.write(symbol + " " + " ".join(format(float(v), ".17g") for v in [*xyz, *force, weight]) + "\n")


def check_export(path, originals, records):
    frames = read(path, index=":", format="extxyz")
    if len(frames) != len(originals):
        raise ValueError("export frame count changed")
    for actual, original, record in zip(frames, originals, records, strict=True):
        pairs = [(actual.positions, original.positions), (actual.cell.array, original.cell.array),
            (actual.pbc, original.pbc), (actual.get_forces(apply_constraint=False), record["forces_eV_per_A"]),
            (actual.arrays["force_loss_weights"], record["proposed_per_atom_loss_weights"])]
        if any(not np.array_equal(a, b) for a, b in pairs):
            raise ValueError("lossless coordinate/raw-force/mask replay failed")
        if actual.get_chemical_symbols() != record["symbols"] or actual.info["sample_id"] != record["sample_id"]:
            raise ValueError("export atom or frame order changed")
        if actual.info["magnetic_review_level"] != record["magnetic_review_level"]:
            raise ValueError("magnetic review level changed")
        if "energy" in actual.calc.results:
            raise ValueError("energy target must not enter this force-only export")
    return len(frames)


def export_data(manifest_path: Path, output: Path):
    manifest = load_manifest(manifest_path)
    output.mkdir(exist_ok=False, parents=True)
    counts, metadata, all_atoms = {}, {}, {}
    for split in ["train", "development"]:
        records = manifest["splits"][split]
        originals = []
        with connect(manifest_path.parent / (split + ".db")) as database:
            rows = list(database.select())
        if len(rows) != len(records):
            raise ValueError("ASE row count changed")
        with (output / (split + ".xyz")).open("x", encoding="utf-8", newline="\n") as handle:
            for row, record in zip(rows, records, strict=True):
                atoms = row.toatoms()
                if row.data.sid != record["sample_id"] or not np.array_equal(atoms.get_forces(apply_constraint=False), record["forces_eV_per_A"]):
                    raise ValueError("database identity/raw-force changed")
                original = read(manifest_path.parent / record["structure_path"], format="vasp")
                if (atoms.get_chemical_symbols() != record["symbols"] or not np.allclose(atoms.positions, original.positions, atol=1e-12, rtol=0)
                        or not np.array_equal(atoms.cell.array, original.cell.array) or not np.array_equal(atoms.pbc, original.pbc)):
                    raise ValueError("source coordinates/cell/order changed")
                info = {k: record[k] for k in ["sample_id", "calculation_group", "magnetic_review_level"]}
                write_frame(handle, atoms, record["proposed_per_atom_loss_weights"], info)
                originals.append(atoms)
        counts[split] = check_export(output / (split + ".xyz"), originals, records)
        all_atoms[split] = originals
        metadata[split] = [{k: r.get(k) for k in ["sample_id", "calculation_group", "source_job_id", "structure_equivalence_sha256",
            "magnetic_review_level", "source_OUTCAR_sha256", "formula_without_slab"]} for r in records]
        # Four training-only diagnostic frames and up to four development frames.
        selected = []
        for composition in ["C2HO", "C2H2O", "C2H3", "C3H2O"]:
            index = next(i for i, r in enumerate(records) if r.get("composition", r.get("formula_without_slab")) == composition)
            selected.append(index)
        with (output / ("smoke_" + split + ".xyz")).open("x", encoding="utf-8", newline="\n") as handle:
            for i in selected:
                r = records[i]
                write_frame(handle, originals[i], r["proposed_per_atom_loss_weights"],
                    {k: r[k] for k in ["sample_id", "calculation_group", "magnetic_review_level"]})
    # Initialization statistics use training data only and no energies.
    from ase.neighborlist import neighbor_list
    squared, free_count, neighbors, atoms_count = 0., 0, 0, 0
    for atoms, record in zip(all_atoms["train"], manifest["splits"]["train"], strict=True):
        free = np.asarray(record["proposed_per_atom_loss_weights"]) > 0
        squared += float(np.square(atoms.get_forces(apply_constraint=False)[free]).sum())
        free_count += int(free.sum())
        neighbors += len(neighbor_list("i", atoms, 5.0, self_interaction=False))
        atoms_count += len(atoms)
    summary = {"counts": counts, "source_manifest_sha256": sha256_file(manifest_path), "source_members": metadata,
        "training_only_initialization": {"cutoff_A": 5., "avg_num_neighbors": neighbors / atoms_count,
            "movable_force_component_rms_eV_A": (squared / (3 * free_count))**.5,
            "per_type_energy_shifts": [0., 0., 0., 0.], "energy_offsets_unidentified_force_only": True},
        "raw_fixed_forces_preserved_but_loss_weights_zero": True, "heldout_exported": False,
        "files": {p.name: sha256_file(p) for p in sorted(output.glob("*.xyz"))}}
    write_json_exclusive(output / "export.json", summary)
    return summary
