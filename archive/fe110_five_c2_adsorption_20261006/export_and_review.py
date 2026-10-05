"""Export existing local CARE poses; no model execution or scientific acceptance."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

from scripts.artifact_io import sha256_file, write_json
from scripts.adsorption.build_fe110_adsorption import Poscar, read_poscar, write_poscar
from scripts.adsorption.build_fe110_care_isomers import transfer_pose, review, expanded_symbols


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("C:/Users/86177/Desktop/app/CARE_Fe110_FT_C1_C6/evaluated_networks/ft_C2O1_Fe110_eval.pkl.json.gz")
SLAB = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
OUTPUT = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
TARGETS = [
    ("01", "XEHVFKKSDRMODV", "C2H", "[C][CH]"),
    ("02", "SNVLJLYUUXKWOJ", "C2H2", "[C][CH2]"),
    ("03", "QEJQAPYSVNHDJF", "C2HO", "[CH][C][O]"),
    ("04", "YOHSXODKVUPAKH", "C2HO", "[C][CH][O]"),
    ("05", "XMHKKYSQISNWMY", "C2HO", "[C][C]O"),
]
ELEMENTS = {26: "Fe", 6: "C", 8: "O", 1: "H"}


def source_poscar(raw: dict) -> Poscar:
    data = raw["ase"]["data"]
    symbols = [ELEMENTS[n] for n in data["numbers"]]
    assert symbols[:48] == ["Fe"] * 48, "Expected original CARE Fe48 order"
    cell = np.asarray(data["cell"], dtype=float)
    positions = np.asarray(data["positions"], dtype=float)
    assert cell.shape == (3, 3) and positions.shape == (len(symbols), 3)
    assert np.isfinite(positions).all() and abs(np.linalg.det(cell)) > 1
    species = list(dict.fromkeys(symbols))
    assert symbols == [s for s in species for _ in range(symbols.count(s))], "CARE order not grouped"
    # Original Fe48 flags are not transferred; canonical Fe45 slab owns constraints.
    return Poscar("Unreviewed local CARE Fe48 prediction", cell, species,
                  [symbols.count(s) for s in species], positions @ np.linalg.inv(cell),
                  [("T", "T", "T")] * len(symbols))


def main() -> None:
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        network = json.load(stream)
    assert str(network["surface"]["facet"]) == "110"
    slab = read_poscar(SLAB)
    assert slab.symbols == ["Fe"] and slab.counts == [45]
    candidates, groups = [], []
    for number, prefix, formula, connectivity in TARGETS:
        matches = [(k, v) for k, v in network["species_registry"].items() if k.startswith(prefix)]
        assert len(matches) == 1, prefix
        code, species = matches[0]
        assert species["phase"] == "ads"
        group = OUTPUT / f"{number}_{formula}_{prefix}"
        group.mkdir(parents=True, exist_ok=True)
        (group / "source_molecule.mol").write_text(species["molecule"], encoding="utf-8")
        ads_coordinates = []
        for cfg, raw in species["ads_configs"].items():
            source = source_poscar(raw)
            target, original_ads = transfer_pose(source, slab)
            result = review(source, target, original_ads)
            directory = group / f"cfg{cfg}"
            directory.mkdir(parents=True, exist_ok=True)
            source_path, target_path = directory / "CARE_Fe48.vasp", directory / "POSCAR"
            write_poscar(source_path, source)
            write_poscar(target_path, target)
            atoms = expanded_symbols(target)
            expected = {"C": 2, "H": 2 if number == "02" else 1, "O": 1 if number in {"03", "04", "05"} else 0}
            assert all(atoms.count(s) == n for s, n in expected.items())
            ads_coordinates.append((cfg, target.frac[45:].copy()))
            candidates.append({"species_id": number, "formula": formula, "connectivity": connectivity,
                               "care_code": code, "config_id": cfg,
                               "source_structure": str(source_path.relative_to(ROOT)),
                               "structure": str(target_path.relative_to(ROOT)),
                               "structure_sha256": sha256_file(target_path),
                               "CARE_mu_source_order_only_eV": raw.get("mu"),
                               "CARE_energy_is_not_VASP": True,
                               "geometry_review": result,
                               "status": "INITIAL_GEOMETRY_REVIEW_ONLY_NOT_STABLE_NOT_GPU_READY"})
        exact_duplicates, height_variants = [], []
        for i, (first, a) in enumerate(ads_coordinates):
            for second, b in ads_coordinates[i + 1:]:
                delta = b - a
                delta[:, :2] -= np.round(delta[:, :2])
                maximum = float(np.linalg.norm(delta @ slab.cell, axis=1).max())
                if maximum < 1e-6:
                    exact_duplicates.append({"configs": [first, second], "max_displacement_A": maximum})
                cart_delta = delta @ slab.cell
                shift = cart_delta.mean(axis=0)
                residual = np.linalg.norm(cart_delta - shift, axis=1).max()
                if residual < 1e-5 and np.linalg.norm(shift[:2]) < 1e-5:
                    height_variants.append({"configs": [first, second], "height_shift_A": float(shift[2]),
                                            "translation_residual_max_A": float(residual)})
        groups.append({"species_id": number, "stored_config_count": len(ads_coordinates),
                       "exact_same_order_duplicates": exact_duplicates,
                       "height_only_seed_variants": height_variants,
                       "symmetry_equivalence": "NOT_YET_REVIEWED"})
    manifest = {"source_network": str(SOURCE), "source_network_sha256": sha256_file(SOURCE),
                "slab": str(SLAB.relative_to(ROOT)), "slab_sha256": sha256_file(SLAB),
                "role": "Review exports from user-owned local predicted CARE poses; no stable-motif or global-minimum claim",
                "submitted": False, "candidate_groups": groups, "candidates": candidates}
    write_json(OUTPUT / "candidate_review.json", manifest)
    for group in groups:
        subset = [c for c in candidates if c["species_id"] == group["species_id"]]
        print(group["species_id"], "stored", group["stored_config_count"], "geometry_pass",
              sum(c["geometry_review"]["verdict"] == "pass" for c in subset),
              "exact_duplicates", group["exact_same_order_duplicates"])
        for c in subset:
            r = c["geometry_review"]
            print(" cfg", c["config_id"], [(a["atom"], a["site"]) for a in r["atom_site_details"]], r["verdict"],
                  "failed", [k for k, v in r["checks"].items() if not v], "warnings", r["warnings"])


if __name__ == "__main__":
    main()
