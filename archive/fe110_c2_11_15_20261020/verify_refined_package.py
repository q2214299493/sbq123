"""Read the final POSCAR bytes back and independently verify geometry invariants."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

from archive.fe110_c2_11_15_20261020.verify_and_document import mol_signature
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020"
OUTPUT = TASK / "candidates_v5"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_record(row, slab):
    path = OUTPUT / row["structure"]
    pose = read_poscar(path)
    symbols = expanded_symbols(pose)
    cart = pose.frac @ pose.cell
    shifts = np.array(list(itertools.product((-2, -1, 0, 1, 2), (-2, -1, 0, 1, 2), (-1, 0, 1)))) @ pose.cell

    def vector(first, second):
        values = cart[second] - cart[first] + shifts
        return values[int(np.argmin(np.linalg.norm(values, axis=1)))]

    radii = {"C": .76, "H": .31, "O": .66}
    ads = list(range(45, len(symbols)))
    edges = {(a, b) for a, b in itertools.combinations(ads, 2)
             if np.linalg.norm(vector(a, b)) <= 1.25 * (radii[symbols[a]] + radii[symbols[b]])}
    signature = []
    for atom in ads:
        neighbors = [b if a == atom else a for a, b in edges if atom in (a, b)]
        if symbols[atom] == "H":
            assert len(neighbors) == 1 and symbols[neighbors[0]] != "H"
        else:
            signature.append([symbols[atom], sum(symbols[other] == "H" for other in neighbors),
                              sorted(symbols[other] for other in neighbors if symbols[other] != "H")])
    original_mol = TASK / "candidates_v3/originals" / row["species_id"] / "source_molecule.mol"
    assert sorted(signature) == mol_signature(original_mol), row["name"]
    parent = read_poscar(Path(row["source_path"]))
    parent_cart = parent.frac @ parent.cell
    differences = []
    for a, b in edges:
        parent_values = parent_cart[b] - parent_cart[a] + shifts
        old = np.linalg.norm(parent_values, axis=1).min()
        differences.append(abs(float(np.linalg.norm(vector(a, b))) - float(old)))
    assert max(differences, default=0.) < 1e-10
    assert np.array_equal(pose.cell, slab.cell) and np.array_equal(pose.frac[:45], slab.frac)
    assert pose.flags[:45] == slab.flags and all(flags == ("T", "T", "T") for flags in pose.flags[45:])
    assert sha(path) == row["structure_sha256"]
    assert row["changed"] or sha(path) == row["source_sha256"]
    angles = []
    for center in ads:
        neighbors = [b if a == center else a for a, b in edges if center in (a, b)]
        if symbols[center] == "H":
            continue
        for first, last in itertools.combinations(neighbors, 2):
            if "H" in (symbols[first], symbols[last]):
                continue
            a, b = vector(center, first), vector(center, last)
            angles.append(float(np.degrees(np.arccos(np.clip(np.dot(a, b) / np.linalg.norm(a) / np.linalg.norm(b), -1., 1.)))))
    if row["species_id"] in {"12", "13"}:
        assert len(angles) == 1 and abs(angles[0] - 120.) < 1e-7
    assert all(row["geometry"]["checks"].values())
    return {"name": row["name"], "status": "PASS_INITIAL_GEOMETRY_ONLY", "source_molecule_graph": "PASS",
            "maximum_bond_length_change_A": max(differences, default=0.), "heavy_angles_deg": angles,
            "exact_slab_cell_flags": True, "structure_sha256": sha(path), "changed": row["changed"]}


def main():
    manifest_path = OUTPUT / "candidate_review.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slab = read_poscar(Path(manifest["slab_path"]))
    assert sha(Path(__file__).with_name("refine_and_audit.py")) == manifest["builder_sha256"]
    receipts = [inspect_record(row, slab) for row in manifest["candidates"]]
    assert len(receipts) == 15 and sum(row["changed"] for row in receipts) == 6
    result = {"status": "PASS", "status_scope": "INDEPENDENT_POSCAR_READBACK_NOT_STABILITY_ACCEPTANCE",
              "scientific_acceptance": False, "source_manifest_sha256": sha(manifest_path),
              "verifier_sha256": sha(Path(__file__)), "checked": 15, "corrected": 6, "byte_identical_retained": 9,
              "candidates": receipts}
    path = OUTPUT / "independent_readback.json"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print("independent_readback=15/15 corrected=6 byte_identical_retained=9 bond_lengths_and_graphs_preserved=True")


if __name__ == "__main__":
    main()
