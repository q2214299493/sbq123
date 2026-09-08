from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    center_score,
    cluster_pairs,
    fe110_rule_defaults,
    identify_top_layer,
    pair_candidates,
    read_poscar,
    triangle_hollow_candidates,
    write_poscar,
)
from scripts.artifact_io import sha256_file
from scripts.workflow_geometry import pbc_xy_distance


def _require_source_shapes(ch: Poscar, h: Poscar, clean: Poscar) -> None:
    if ch.symbols != ["Fe", "C", "H"] or ch.counts != [45, 1, 1]:
        raise ValueError("CH source must contain Fe45 C1 H1 in Fe C H order")
    if h.symbols != ["Fe", "H"] or h.counts != [45, 1]:
        raise ValueError("H source must contain Fe45 H1 in Fe H order")
    if clean.symbols != ["Fe"] or clean.counts != [45]:
        raise ValueError("clean reference must contain Fe45")
    if not np.allclose(ch.cell, h.cell, atol=1e-8) or not np.allclose(ch.cell, clean.cell, atol=1e-8):
        raise ValueError("CH, H, and clean references must use the same cell")
    for name, source in (("CH", ch), ("H", h), ("clean", clean)):
        if any(flag != ("F", "F", "F") for flag in source.flags[:18]):
            raise ValueError(f"{name} source does not keep the bottom 18 Fe atoms fixed")
        if any(flag != ("T", "T", "T") for flag in source.flags[18:]):
            raise ValueError(f"{name} source contains unexpected constraints above the bottom 18 Fe atoms")


def _hollow_centers(clean: Poscar) -> list[np.ndarray]:
    rules = fe110_rule_defaults()
    top = identify_top_layer(clean, rules["z_tolerance"])
    pairs = pair_candidates(clean, top)
    groups = [
        group
        for group in cluster_pairs(pairs, rules["pair_tolerance"])
        if np.mean([candidate.distance for candidate in group]) > 1.0
    ]
    if len(groups) < 2:
        raise ValueError("clean Fe(110) slab lacks two bridge-distance classes")
    short_distance = float(np.mean([candidate.distance for candidate in groups[0]]))
    long_distance = float(np.mean([candidate.distance for candidate in groups[1]]))
    return triangle_hollow_candidates(
        clean,
        top,
        short_distance,
        long_distance,
        rules["pair_tolerance"],
        rules["site_tolerance"],
        [candidate.midpoint for candidate in pairs],
    )


def _top_centers(clean: Poscar) -> list[np.ndarray]:
    rules = fe110_rule_defaults()
    return [clean.frac[index].copy() for index in identify_top_layer(clean, rules["z_tolerance"])]


def _site_centers(clean: Poscar, site: str) -> list[np.ndarray]:
    if site == "hollow":
        return _hollow_centers(clean)
    if site == "top":
        return _top_centers(clean)
    raise ValueError(f"unsupported incoming H site: {site}")


def _nearest_fe_distance(structure: Poscar, atom_index: int) -> float:
    cart = structure.frac @ structure.cell
    return min(pbc_xy_distance(structure.cell, cart[atom_index], cart[index]) for index in range(45))


def _place_at_fe_distance(structure: Poscar, site_frac: np.ndarray, target: float) -> np.ndarray:
    cart = structure.frac @ structure.cell
    xy = site_frac @ structure.cell
    top_fe_z = float(np.max(cart[:45, 2]))

    def nearest(z: float) -> float:
        trial = np.array([xy[0], xy[1], z], dtype=float)
        return min(pbc_xy_distance(structure.cell, trial, fe) for fe in cart[:45])

    lower = top_fe_z
    upper = top_fe_z + 5.0
    if nearest(lower) > target or nearest(upper) < target:
        raise ValueError("target Fe-H distance cannot be placed above the surface")
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if nearest(midpoint) < target:
            lower = midpoint
        else:
            upper = midpoint
    return np.array([xy[0], xy[1], (lower + upper) / 2.0], dtype=float)


def build(
    ch_path: Path,
    h_path: Path,
    clean_path: Path,
    output: Path,
    *,
    candidate: str = "CH_long_bridge_plus_H_adjacent_hollow",
    ch_site_label: str = "long_bridge",
    h_site_label: str = "hollow",
    h_proximity_label: str = "adjacent",
    selection_basis: str = (
        "lowest local CH and H relaxation energies with CH long-bridge preserved "
        "toward the lowest local CH2 long-bridge product candidate"
    ),
    min_c_h: float = 1.80,
    max_c_h: float = 2.20,
    min_h_h: float = 1.60,
) -> dict[str, object]:
    ch = read_poscar(ch_path)
    h = read_poscar(h_path)
    clean = read_poscar(clean_path)
    _require_source_shapes(ch, h, clean)

    ch_cart = ch.frac @ ch.cell
    carbon = ch_cart[45]
    bonded_h = ch_cart[46]
    target_fe_h = _nearest_fe_distance(h, 45)
    candidates: list[tuple[float, float, np.ndarray, np.ndarray]] = []
    for site_center in _site_centers(clean, h_site_label):
        incoming_h = _place_at_fe_distance(ch, site_center, target_fe_h)
        c_h = pbc_xy_distance(ch.cell, carbon, incoming_h)
        h_h = pbc_xy_distance(ch.cell, bonded_h, incoming_h)
        if min_c_h <= c_h <= max_c_h and h_h >= min_h_h:
            candidates.append((center_score(ch.cell, site_center), c_h, site_center, incoming_h))
    if not candidates:
        raise ValueError(f"no adjacent {h_site_label} H candidate passes the C-H/H-H separation gate")

    _, c_h, selected_site, incoming_h = min(candidates, key=lambda row: (row[0], abs(row[1] - 2.0)))
    incoming_frac = incoming_h @ np.linalg.inv(ch.cell)
    incoming_frac[:2] %= 1.0
    structure = Poscar(
        comment=f"Fe45 CH+H coadsorption CH_{ch_site_label} H_{h_proximity_label}_{h_site_label}",
        cell=ch.cell.copy(),
        symbols=["Fe", "C", "H"],
        counts=[45, 1, 2],
        frac=np.vstack((ch.frac, incoming_frac)),
        flags=[*ch.flags, ("T", "T", "T")],
    )
    output.mkdir(parents=True, exist_ok=True)
    poscar_path = output / "POSCAR"
    write_poscar(poscar_path, structure)

    final_cart = structure.frac @ structure.cell
    incoming_index = 47
    manifest: dict[str, object] = {
        "version": 1,
        "surface": "true Fe(110), Fe45, five layers, bottom 18 Fe fixed",
        "candidate": candidate,
        "selection_basis": selection_basis,
        "source_files": {
            "ch_contcar": str(ch_path),
            "ch_sha256": sha256_file(ch_path),
            "h_contcar": str(h_path),
            "h_sha256": sha256_file(h_path),
            "clean_contcar": str(clean_path),
            "clean_sha256": sha256_file(clean_path),
        },
        "atom_map_zero_based": {
            "carbon": 45,
            "preexisting_ch_hydrogen": 46,
            "incoming_surface_hydrogen": incoming_index,
        },
        "initial_connectivity": [[45, 46]],
        "target_formed_bond": [45, incoming_index],
        "site_labels": {
            "carbon": ch_site_label,
            "incoming_hydrogen": f"{h_proximity_label}_{h_site_label}",
        },
        "geometry_angstrom": {
            "existing_c_h": pbc_xy_distance(ch.cell, final_cart[45], final_cart[46]),
            "incoming_c_h": c_h,
            "h_h": pbc_xy_distance(ch.cell, final_cart[46], final_cart[47]),
            "incoming_h_nearest_fe": _nearest_fe_distance(structure, incoming_index),
        },
        "selected_h_site_fractional": [float(value) for value in selected_site],
        "poscar": "POSCAR",
        "poscar_sha256": sha256_file(poscar_path),
        "local_relaxation_required": True,
    }
    (output / "candidate_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one path-compatible Fe(110) CH*+H* coadsorption candidate.")
    parser.add_argument("--ch", required=True, type=Path)
    parser.add_argument("--h", required=True, type=Path)
    parser.add_argument("--clean", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate", default="CH_long_bridge_plus_H_adjacent_hollow")
    parser.add_argument("--ch-site-label", default="long_bridge")
    parser.add_argument("--h-site-label", choices=("hollow", "top"), default="hollow")
    parser.add_argument("--h-proximity-label", default="adjacent")
    parser.add_argument("--min-c-h", type=float, default=1.80)
    parser.add_argument("--max-c-h", type=float, default=2.20)
    parser.add_argument("--min-h-h", type=float, default=1.60)
    parser.add_argument(
        "--selection-basis",
        default=(
            "lowest local CH and H relaxation energies with CH long-bridge preserved "
            "toward the lowest local CH2 long-bridge product candidate"
        ),
    )
    args = parser.parse_args()
    manifest = build(
        args.ch,
        args.h,
        args.clean,
        args.output,
        candidate=args.candidate,
        ch_site_label=args.ch_site_label,
        h_site_label=args.h_site_label,
        h_proximity_label=args.h_proximity_label,
        selection_basis=args.selection_basis,
        min_c_h=args.min_c_h,
        max_c_h=args.max_c_h,
        min_h_h=args.min_h_h,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
