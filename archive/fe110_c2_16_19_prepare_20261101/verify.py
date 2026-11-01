"""Independent saved-file readback, with enumerated xy periodic images."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from .prepare import OUT, REUSE, SLAB

EXPECTED_EDGES = {
    "16": {(45, 46), (45, 47), (47, 48), (46, 49), (46, 50), (46, 51)},
    "17": {(45, 46), (46, 47), (45, 48), (45, 49), (46, 50), (46, 51)},
    "18": {(45, 47), (46, 47), (45, 48), (46, 49), (46, 50), (46, 51)},
    "19": {(45, 46), (45, 47), (45, 48), (45, 49), (46, 50), (46, 51), (46, 52)},
}
RADII = {"C": .76, "O": .66, "H": .31}


def audit_geometry(pose, slab, number):
    counts = [45, 2, 6] if number == "19" else [45, 2, 1, 4]
    assert pose.counts == counts
    np.testing.assert_allclose(pose.cell, slab.cell, rtol=0, atol=1e-12)
    np.testing.assert_allclose(pose.frac[:45], slab.frac, rtol=0, atol=1e-12)
    assert pose.flags[:45] == slab.flags
    assert pose.flags[45:] == [("T", "T", "T")] * (sum(counts) - 45)
    xyz = pose.frac @ pose.cell
    symbols = expanded_symbols(pose)
    images = np.array([[i, j, 0] for i, j in itertools.product(range(-1, 2), repeat=2)]) @ pose.cell

    def distance(i, j):
        return float(np.linalg.norm(xyz[j] - xyz[i] + images, axis=1).min())

    edges, nonbonded = set(), []
    for i in range(45, sum(counts)):
        for j in range(i + 1, sum(counts)):
            value = distance(i, j)
            if value <= 1.25 * (RADII[symbols[i]] + RADII[symbols[j]]):
                edges.add((i, j))
                assert value >= .35
            else:
                nonbonded.append(value)
    assert edges == EXPECTED_EDGES[number], (number, edges)
    assert min(nonbonded) > 1.0
    contacts = []
    for i in range(45, sum(counts)):
        nearest = min((distance(i, j), j) for j in range(45))
        assert nearest[0] >= (1.35 if symbols[i] == "H" else 1.65)
        contacts.append({"atom_zero_based": i, "element": symbols[i],
                         "Fe_zero_based": nearest[1], "distance_A": nearest[0]})
    height = float(xyz[45:, 2].min() - xyz[:45, 2].max())
    assert height >= 1.35
    return {"name": number, "composition": dict(zip(pose.symbols, pose.counts, strict=True)),
            "expected_bonds_verified": len(edges), "minimum_nonbonded_distance_A": min(nonbonded),
            "minimum_height_above_top_Fe_A": height, "nearest_Fe": contacts}


def main():
    manifest_path = OUT / "candidate_review.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == 12
    assert manifest["execution"] == {"GPU": 0, "VASP": 0}
    assert not manifest["submitted"] and not manifest["scientific_acceptance"] and not manifest["gpu_ready"]
    assert not manifest["stable_top_three_claim"] and not manifest["source_energies_imported"]
    slab = read_poscar(SLAB)
    records = []
    for candidate in manifest["candidates"]:
        path = Path(candidate["structure"])
        assert sha256_file(path) == candidate["structure_sha256"]
        assert candidate["energy_eV"] is None and not candidate["relaxed"]
        result = audit_geometry(read_poscar(path), slab, candidate["species_number"])
        result["name"] = candidate["name"]
        if candidate["species_number"] == "17":
            original = REUSE / candidate["name"][-1] / "POSCAR"
            assert path.read_bytes() == original.read_bytes()
            result["byte_exact_prior_candidate_reuse"] = True
        records.append(result)
    assert len({c["name"] for c in manifest["candidates"]}) == 12
    assert len(manifest["seed_only_deduplication"]["pairwise"]) == 12
    summary = {"status": "PASS_GEOMETRY_READBACK_ONLY", "records": records,
               "manifest_sha256": sha256_file(manifest_path), "scientific_acceptance": False,
               "scope": "Independent distance/graph/slab/mask checks, not a stability, model, GPU or DFT validation."}
    write_json_exclusive(OUT / "independent_verification.json", summary)
    print(json.dumps({"status": summary["status"], "verified_candidates": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
