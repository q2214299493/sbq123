"""Independent enumeration of xy images for saved supplemental POSCAR readback."""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import yaml

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest_valid, write_json_exclusive
from .prepare import OUT, POLICY, SLAB


EXPECTED = {
    "05": {(45, 46), (46, 47), (45, 48)},
    "06": {(45, 47), (46, 47), (45, 48)},
    "07": {(45, 46), (46, 47), (45, 48), (45, 49)},
    "09": {(45, 47), (46, 47), (45, 48), (45, 49)},
    "11": {(45, 46), (45, 47), (45, 48), (45, 49)},
    "12": {(45, 46), (46, 47), (45, 48), (45, 49), (45, 50)},
    "13": {(45, 46), (46, 47), (45, 48), (47, 49), (47, 50)},
    "14": {(45, 47), (46, 47), (45, 48), (45, 49), (45, 50)},
    "18": {(45, 47), (46, 47), (45, 48), (46, 49), (46, 50), (46, 51)},
}
COMPOSITION = {"05": {"C": 2, "O": 1, "H": 1}, "06": {"C": 2, "O": 1, "H": 1},
    "07": {"C": 2, "O": 1, "H": 2}, "09": {"C": 2, "O": 1, "H": 2}, "11": {"C": 2, "H": 3},
    "12": {"C": 2, "O": 1, "H": 3}, "13": {"C": 2, "O": 1, "H": 3}, "14": {"C": 2, "O": 1, "H": 3},
    "18": {"C": 2, "O": 1, "H": 4}}
RADII = {"C": .76, "O": .66, "H": .31}


def vector(pose, first, second):
    shifts = np.array([[x, y, 0] for x, y in itertools.product((-1, 0, 1), repeat=2)])
    choices = (pose.frac[second] - pose.frac[first] + shifts) @ pose.cell
    return choices[np.argmin(np.linalg.norm(choices, axis=1))]


def check_one(item, slab, rules):
    path = Path(item["structure"])
    assert sha256_file(path) == item["structure_sha256"]
    assert sha256_file(Path(item["source_path"])) == item["source_sha256"]
    pose, original = read_poscar(path), read_poscar(Path(item["source_path"]))
    symbols = expanded_symbols(pose)
    expected = COMPOSITION[item["species_number"]]
    assert {s: symbols[45:].count(s) for s in set(symbols[45:])} == expected
    assert symbols == expanded_symbols(original)
    np.testing.assert_allclose(pose.cell, slab.cell, rtol=0, atol=1e-12)
    np.testing.assert_allclose(pose.frac[:45], slab.frac, rtol=0, atol=1e-12)
    assert pose.flags[:45] == slab.flags and pose.flags[45:] == [("T", "T", "T")] * (len(symbols) - 45)
    edges = set()
    scale = rules["connectivity"]["covalent_radius_scale"]
    for first in range(45, len(symbols)):
        for second in range(first + 1, len(symbols)):
            length = np.linalg.norm(vector(pose, first, second))
            if length <= scale * (RADII[symbols[first]] + RADII[symbols[second]]):
                assert length >= rules["connectivity"]["minimum_bond_distance_angstrom"]
                edges.add((first, second))
    assert edges == EXPECTED[item["species_number"]], (item["name"], edges)
    deltas = [abs(np.linalg.norm(vector(pose, a, b)) - np.linalg.norm(vector(original, a, b))) for a, b in edges]
    angles = []
    for center in range(45, len(symbols)):
        neighbors = [b if a == center else a for a, b in edges if center in (a, b)]
        for a, b in itertools.combinations(neighbors, 2):
            def angle(structure):
                u, v = vector(structure, center, a), vector(structure, center, b)
                return np.degrees(np.arccos(np.clip(u @ v / np.linalg.norm(u) / np.linalg.norm(v), -1, 1)))
            angles.append(abs(angle(pose) - angle(original)))
    assert max(deltas, default=0.) < 1e-9 and max(angles, default=0.) < 1e-7
    contacts = []
    for index in range(45, len(symbols)):
        nearest = sorted((float(np.linalg.norm(vector(pose, index, fe))), fe) for fe in range(45))[:3]
        assert nearest[0][0] >= (1.35 if symbols[index] == "H" else 1.65)
        contacts.append({"atom_0based": index, "element": symbols[index],
            "nearest_Fe": [{"Fe_0based": fe, "distance_A": d} for d, fe in nearest]})
    minimum = min(np.linalg.norm(vector(pose, a, b)) for a in range(len(symbols))
                  for b in range(a + 1, len(symbols)) if (a, b) not in edges)
    assert minimum >= rules["contact_validation"]["hard_contact_distance_angstrom"]
    height = float((pose.frac @ pose.cell)[45:, 2].min() - (slab.frac @ slab.cell)[:, 2].max())
    assert height >= 1.35
    if item["byte_exact_recovery"]:
        assert path.read_bytes() == Path(item["source_path"]).read_bytes()
    assert not item["submitted"] and not item["relaxed"] and item["energy_eV"] is None
    return {"name": item["name"], "status": "PASS_SAVED_GEOMETRY_ONLY", "source_bytes_recovered": item["byte_exact_recovery"],
        "maximum_internal_bond_delta_A": max(deltas, default=0.), "maximum_internal_angle_delta_deg": max(angles, default=0.),
        "minimum_contact_excluding_adsorbate_bonds_A": float(minimum), "minimum_height_above_Fe_A": height,
        "nearest_Fe": contacts}


def main():
    manifest = load_json_object(OUT / "candidate_review.json")
    assert source_file_manifest_valid(manifest)
    assert manifest["candidate_count"] == 12 and manifest["execution"] == {"GPU": 0, "VASP": 0}
    assert not manifest["submitted"] and not manifest["scientific_acceptance"] and not manifest["gpu_ready"]
    slab = read_poscar(SLAB)
    rules = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    records = [check_one(item, slab, rules) for item in manifest["candidates"]]
    write_json_exclusive(OUT / "independent_verification.json", {"status": "PASS_GEOMETRY_READBACK_ONLY",
        "records": records, "manifest_sha256": sha256_file(OUT / "candidate_review.json"),
        "verifier_sha256": sha256_file(Path(__file__)), "scientific_acceptance": False,
        "scope": "Independent periodic geometry/order/graph/contact/rigid-angle readback, not stability or permission."})
    print("VERIFIED", len(records), "saved candidates; no scientific acceptance or execution")


if __name__ == "__main__":
    main()
