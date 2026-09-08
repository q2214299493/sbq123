from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.artifact_io import sha256_file, write_json

from scripts.workflow_geometry import minimum_image_delta_xy, pbc_xy_distance

from .build_fe110_adsorption import (
    Poscar,
    center_score,
    expanded_symbols,
    fe110_anchor_site_distances,
    fe110_rule_defaults,
    identify_top_layer,
    read_poscar,
    write_poscar,
)


RADII = {"H": 0.31, "C": 0.76, "O": 0.66}
SITE_CODES = {"top": "t", "short_bridge": "sb", "long_bridge": "lb", "hollow": "h"}
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
ASCII_SITE_LABEL = str.maketrans({"η": "eta", "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"})


def selected_rows(care_root: Path) -> list[dict[str, str]]:
    manifest = care_root / "fe48_adsorption_candidate_manifest.csv"
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["vasp_candidate_priority"] == "RELAX_FIRST"]
    rows.sort(key=lambda row: (row["formula"], row["code"]))
    if len(rows) != 8 or Counter(row["formula"] for row in rows) != {"C2H2O": 4, "C3H2O": 4}:
        raise ValueError("CARE manifest must contain exactly four C2H2O and four C3H2O RELAX_FIRST rows")
    if len({row["code"] for row in rows}) != 8:
        raise ValueError("CARE RELAX_FIRST rows must represent eight unique molecular graphs")
    if any(row["geometry_gate"] != "PASS_EXPORT_CANDIDATE" for row in rows):
        raise ValueError("every selected CARE structure must pass its source export geometry gate")
    return rows


def surface_basis(poscar: Poscar, top: np.ndarray) -> np.ndarray:
    vectors: list[np.ndarray] = []
    for first in top:
        for second in top:
            if first == second:
                continue
            vector = minimum_image_delta_xy(poscar.frac[second] - poscar.frac[first]) @ poscar.cell
            distance = float(np.linalg.norm(vector[:2]))
            if 2.3 <= distance <= 3.0:
                vectors.append(vector[:2])
    long = [vector for vector in vectors if np.linalg.norm(vector) > 2.65 and vector[0] > 0]
    short = [vector for vector in vectors if np.linalg.norm(vector) < 2.65 and vector[1] > 0 and vector[0] > 0]
    if not long or not short:
        raise ValueError("could not identify the Fe(110) local surface basis")
    u = min(long, key=lambda vector: abs(vector[1]))
    v = max(short, key=lambda vector: vector[0])
    basis = np.vstack((u, v))
    if abs(float(np.linalg.det(basis))) < 1.0:
        raise ValueError("degenerate Fe(110) local surface basis")
    return basis


def adsorbate_indices(poscar: Poscar) -> list[int]:
    return [index for index, symbol in enumerate(expanded_symbols(poscar)) if symbol != "Fe"]


def binding_origin(poscar: Poscar, top: np.ndarray, adsorbate: list[int]) -> int:
    symbols = expanded_symbols(poscar)
    heavy = [index for index in adsorbate if symbols[index] != "H"]
    anchor = min(
        heavy,
        key=lambda index: min(pbc_xy_distance(poscar.cell, poscar.frac[index] @ poscar.cell, poscar.frac[fe] @ poscar.cell) for fe in top),
    )
    anchor_cart = poscar.frac[anchor] @ poscar.cell
    return min(top.tolist(), key=lambda fe: pbc_xy_distance(poscar.cell, anchor_cart, poscar.frac[fe] @ poscar.cell))


def transfer_pose(source: Poscar, slab: Poscar) -> tuple[Poscar, list[int]]:
    defaults = fe110_rule_defaults()
    source_top = identify_top_layer(source, defaults["z_tolerance"])
    target_top = identify_top_layer(slab, defaults["z_tolerance"])
    source_symbols = expanded_symbols(source)
    species = list(dict.fromkeys(symbol for symbol in source.symbols if symbol != "Fe"))
    original_adsorbate = adsorbate_indices(source)
    adsorbate = [index for symbol in species for index in original_adsorbate if source_symbols[index] == symbol]
    source_origin = binding_origin(source, source_top, adsorbate)
    target_origin = min(target_top.tolist(), key=lambda index: center_score(slab.cell, slab.frac[index]))
    source_basis = surface_basis(source, source_top)
    target_basis = surface_basis(slab, target_top)
    target_origin_cart = slab.frac[target_origin] @ slab.cell
    mapped = []
    for index in adsorbate:
        delta = minimum_image_delta_xy(source.frac[index] - source.frac[source_origin]) @ source.cell
        coefficients = delta[:2] @ np.linalg.inv(source_basis)
        mapped.append(target_origin_cart + np.array([*(coefficients @ target_basis), delta[2]]))
    mapped_frac = np.asarray(mapped) @ np.linalg.inv(slab.cell)
    mapped_frac[:, :2] %= 1.0
    ads_symbols = [source_symbols[index] for index in adsorbate]
    expected = [symbol for symbol in species for _ in range(ads_symbols.count(symbol))]
    if ads_symbols != expected:
        raise ValueError("CARE adsorbate atoms are not grouped by the POSCAR species order")
    structure = Poscar(
        comment="Fe45 Fe(110) CARE RELAX_FIRST pose transfer",
        cell=slab.cell.copy(),
        symbols=["Fe", *species],
        counts=[45, *(ads_symbols.count(symbol) for symbol in species)],
        frac=np.vstack((slab.frac, mapped_frac)),
        flags=[*slab.flags, *(("T", "T", "T") for _ in adsorbate)],
    )
    return structure, adsorbate


def pair_distances(poscar: Poscar, indices: list[int]) -> dict[tuple[int, int], float]:
    cart = poscar.frac @ poscar.cell
    return {
        (first, second): pbc_xy_distance(poscar.cell, cart[first], cart[second])
        for position, first in enumerate(indices)
        for second in indices[position + 1 :]
    }


def connectivity(poscar: Poscar, indices: list[int]) -> list[tuple[int, int]]:
    symbols = expanded_symbols(poscar)
    cart = poscar.frac @ poscar.cell
    edges = []
    for first in range(len(indices)):
        for second in range(first + 1, len(indices)):
            first_global, second_global = indices[first], indices[second]
            distance = pbc_xy_distance(poscar.cell, cart[first_global], cart[second_global])
            if distance <= 1.25 * (RADII[symbols[first_global]] + RADII[symbols[second_global]]):
                edges.append((first, second))
    return edges


def review(source: Poscar, structure: Poscar, source_ads: list[int]) -> dict[str, object]:
    symbols = expanded_symbols(structure)
    ads = list(range(45, len(symbols)))
    cart = structure.frac @ structure.cell
    fe = list(range(45))
    top_z = max(cart[index, 2] for index in fe)
    nearest = [min(pbc_xy_distance(structure.cell, cart[index], cart[iron]) for iron in fe) for index in ads]
    source_edges = connectivity(source, source_ads)
    target_edges = connectivity(structure, ads)
    source_cart = source.frac @ source.cell
    bond_deltas = [
        abs(
            pbc_xy_distance(source.cell, source_cart[source_ads[first]], source_cart[source_ads[second]])
            - pbc_xy_distance(structure.cell, cart[ads[first]], cart[ads[second]])
        )
        for first, second in source_edges
    ]
    max_bond_delta = max(bond_deltas, default=0.0)
    binding_symbols: list[str] = []
    binding_sites: list[str] = []
    site_details: list[dict[str, object]] = []
    element_counts: Counter[str] = Counter()
    for local, (index, distance) in enumerate(zip(ads, nearest, strict=True), start=1):
        symbol = symbols[index]
        element_counts[symbol] += 1
        atom_label = f"{symbol}{element_counts[symbol]}"
        if symbol == "H":
            continue
        distances = fe110_anchor_site_distances(structure, structure.frac[index])
        site, lateral = min(distances.items(), key=lambda item: item[1])
        site_details.append({"atom": atom_label, "nearest_fe_angstrom": distance, "site": site, "lateral_offset_angstrom": lateral})
        if distance <= 2.65 and lateral <= 0.80:
            binding_symbols.append(symbol)
            binding_sites.append(SITE_CODES[site])
    fixed_fe = sum(all(flag.upper() == "F" for flag in structure.flags[index]) for index in fe)
    heavy_nearest = [distance for index, distance in zip(ads, nearest, strict=True) if symbols[index] != "H"]
    hydrogen_nearest = [distance for index, distance in zip(ads, nearest, strict=True) if symbols[index] == "H"]
    minimum_height = float(min(cart[index, 2] - top_z for index in ads))
    minimum_h_fe = min(hydrogen_nearest) if hydrogen_nearest else None
    warnings = []
    if minimum_h_fe is not None and minimum_h_fe < 1.90:
        warnings.append("short_H-Fe_contact_below_1.90_angstrom_review_at_early_relaxation")
    if minimum_height < 1.60:
        warnings.append("adsorbate_atom_below_1.60_angstrom_above_top_Fe_review_at_early_relaxation")
    checks = {
        "composition_and_order": structure.counts[0] == 45 and sum(structure.counts[1:]) == len(source_ads),
        "bottom_18_fe_fixed": fixed_fe == 18,
        "adsorbate_fully_mobile": all(all(flag.upper() == "T" for flag in structure.flags[index]) for index in ads),
        "connectivity_preserved": source_edges == target_edges,
        "internal_geometry_preserved": max_bond_delta <= 0.01,
        "adsorbate_above_surface": minimum_height >= 1.35,
        "no_hard_heavy_fe_contact": min(heavy_nearest) >= 1.65,
        "no_hard_h_fe_contact": not hydrogen_nearest or min(hydrogen_nearest) >= 1.35,
    }
    return {
        "verdict": "pass" if all(checks.values()) else "block",
        "site_label": (
            f"η{str(len(binding_symbols)).translate(SUPERSCRIPT)}(" + ",".join(binding_symbols) + ")/" + "-".join(binding_sites)
            if binding_symbols
            else "unclassified"
        ),
        "atom_site_details": site_details,
        "nearest_heavy_fe_angstrom": min(heavy_nearest),
        "nearest_h_fe_angstrom": minimum_h_fe,
        "minimum_adsorbate_height_angstrom": minimum_height,
        "maximum_bond_length_change_angstrom": float(max_bond_delta),
        "connectivity_edges_local_0based": target_edges,
        "checks": checks,
        "warnings": warnings,
        "needs_early_relaxation_review": bool(warnings),
    }


def build(slab_path: Path, care_root: Path, output: Path) -> dict[str, object]:
    slab = read_poscar(slab_path)
    if slab.symbols != ["Fe"] or slab.counts != [45]:
        raise ValueError("builder requires the verified clean Fe45 Fe(110) slab")
    if sum(all(flag.upper() == "F" for flag in slab.flags[index]) for index in range(45)) != 18:
        raise ValueError("Fe45 slab must keep exactly the bottom 18 Fe atoms fixed")
    records = []
    for number, row in enumerate(selected_rows(care_root), start=1):
        source_path = Path(row["poscar_path"])
        source = read_poscar(source_path)
        if source.counts[0] != 48 or source.symbols[0] != "Fe":
            raise ValueError(f"{source_path}: expected a CARE Fe48 adsorption structure")
        structure, source_ads = transfer_pose(source, slab)
        geometry = review(source, structure, source_ads)
        if geometry["verdict"] != "pass":
            raise ValueError(f"{row['code']}: transferred geometry failed review: {geometry['checks']}")
        short_code = row["code"].split("-", 1)[0][:8]
        name = f"{number:02d}_{row['formula']}_{short_code}_cfg{row['care_config_id']}"
        ascii_site = str(geometry["site_label"]).translate(ASCII_SITE_LABEL)
        structure = Poscar(f"Fe45 {row['formula']} {row['smiles']} {ascii_site}", structure.cell, structure.symbols, structure.counts, structure.frac, structure.flags)
        write_poscar(output / name / "POSCAR", structure)
        records.append(
            {
                "name": name,
                "formula": row["formula"],
                "exact_smiles": row["smiles"],
                "care_code": row["code"],
                "care_level": int(row["care_level_loaded"]),
                "care_config_id": int(row["care_config_id"]),
                "source_selection": "RELAX_FIRST",
                "care_mu_relative_order_only_ev": float(row["care_mu"]),
                "care_energy_imported_as_local_result": False,
                "source_poscar": str(source_path),
                "source_poscar_sha256": sha256_file(source_path),
                "poscar": f"{name}/POSCAR",
                "geometry_review": geometry,
            }
        )
    manifest = {
        "version": 1,
        "surface": "true Fe(110), Fe45, five layers, bottom 18 Fe fixed",
        "source_slab": str(slab_path),
        "source_slab_sha256": sha256_file(slab_path),
        "selection_rule": "one CARE RELAX_FIRST pose per exact molecular graph; no fixed site sweep",
        "transfer_method": "map the CARE Fe48 local Fe(110) surface basis onto Fe45; preserve height, orientation, connectivity, and atom order",
        "local_relaxation_required_before_stability_claim": True,
        "submitted": False,
        "candidates": records,
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "candidate_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Transfer eight CARE Fe48 RELAX_FIRST isomer poses to the verified Fe45 Fe(110) slab.")
    parser.add_argument("--slab", required=True, type=Path)
    parser.add_argument("--care-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build(args.slab, args.care_root, args.output)
    print(f"generated={len(manifest['candidates'])} submitted=0")
    for item in manifest["candidates"]:
        review_data = item["geometry_review"]
        print(f"{item['name']} {review_data['verdict']}")


if __name__ == "__main__":
    main()
