"""Read-only checks of exported structures and their retained provenance."""
import json
from pathlib import Path

import jsonschema
import numpy as np

from scripts.artifact_io import sha256_file, write_json
from scripts.adsorption.build_fe110_adsorption import read_poscar, expanded_symbols
from scripts.workflow_geometry import pbc_xy_distance

root = Path(__file__).resolve().parents[2]
folder = root / "archive/fe110_five_c2_adsorption_20261006"
manifest = json.loads((root / "calculations/fe110_five_c2_adsorption_20261006/candidate_review.json").read_text())
image = json.loads((folder / "image_query.json").read_text())
schema = json.loads((root / "skills/catalysis-data-retrieval/references/image_query_schema.json").read_text())
jsonschema.validate(image, schema)
assert sha256_file(Path(manifest["source_network"])) == manifest["source_network_sha256"]
slab = read_poscar(root / manifest["slab"])
assert sha256_file(root / manifest["slab"]) == manifest["slab_sha256"]
checks = []
for entry in manifest["candidates"]:
    path = root / entry["structure"]
    assert sha256_file(path) == entry["structure_sha256"]
    atoms = read_poscar(path)
    symbols = expanded_symbols(atoms)
    assert np.array_equal(atoms.cell, slab.cell)
    assert np.allclose(atoms.frac[:45], slab.frac, atol=1e-14)
    assert atoms.flags[:45] == slab.flags
    assert [i for i, f in enumerate(atoms.flags) if f == ("F", "F", "F")] == list(range(18))
    assert all(f == ("T", "T", "T") for f in atoms.flags[45:])
    xyz = atoms.frac @ atoms.cell
    nearest = []
    for i in range(45, len(symbols)):
        distance, iron = min((pbc_xy_distance(atoms.cell, xyz[i], xyz[j]), j) for j in range(45))
        nearest.append({"atom_index_zero_based": i, "element": symbols[i], "nearest_Fe_zero_based": iron, "distance_A": distance})
        if symbols[i] == "H":
            bond, heavy = min((pbc_xy_distance(atoms.cell, xyz[i], xyz[j]), j) for j in range(45, len(symbols)) if symbols[j] != "H")
            assert heavy == 45 and bond < 1.2, "Unexpected hydrogen-placement change"
            assert symbols[heavy] == ("O" if entry["species_id"] == "05" else "C")
    checks.append({"species_id": entry["species_id"], "config_id": entry["config_id"], "nearest_contacts": nearest})
assert len(checks) == 15
assert sum(e["geometry_review"]["verdict"] == "pass" for e in manifest["candidates"]) == 14
variants = next(g for g in manifest["candidate_groups"] if g["species_id"] == "03")["height_only_seed_variants"]
assert len(variants) == 3
assert not manifest["submitted"]
write_json(folder / "export_verification.json", {"status": "PASS_EXPORT_IDENTITY_AND_PROVENANCE_ONLY", "structures_checked": 15, "initial_geometry_pass": 14,
           "initial_height_flag": "02/cfg0", "species03_height_only_pairs": len(variants), "nearest_contacts": checks,
           "not_validated": ["Stable minima", "Surface-symmetry equivalence", "GPU handoff", "DFT energies", "Adsorption-energy references"]})
print("PASS: 15 export hashes, unchanged slab/cell/constraints, H placement; 14 initial geometry passes, one height flag; CHCO height variants identified; no submission")
