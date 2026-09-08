from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from scripts.workflow_geometry import expand_symbols, minimum_image_delta_xy, pbc_xy_distance


SITE_NAMES = ("top", "short_bridge", "long_bridge", "hollow")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITE_RULES = REPOSITORY_ROOT / "configs" / "adsmind_lite" / "site_rules.yaml"
DEFAULT_ANALYSIS_RULES = REPOSITORY_ROOT / "configs" / "adsmind_lite" / "analysis_rules.yaml"


@dataclass(frozen=True)
class Poscar:
    comment: str
    cell: np.ndarray
    symbols: list[str]
    counts: list[int]
    frac: np.ndarray
    flags: list[tuple[str, str, str]]


@dataclass(frozen=True)
class Site:
    name: str
    frac: np.ndarray
    support_indices: tuple[int, ...]
    support_distance: float | None


@dataclass(frozen=True)
class PairCandidate:
    distance: float
    midpoint: np.ndarray
    indices: tuple[int, int]


def read_poscar(path: Path) -> Poscar:
    return parse_poscar_text(path.read_text(encoding="utf-8"), str(path))


def parse_poscar_text(text: str, source: str = "POSCAR") -> Poscar:
    lines = text.splitlines()
    if len(lines) < 8:
        raise ValueError(f"{source}: incomplete POSCAR")
    scale = float(lines[1].split()[0])
    if scale <= 0:
        raise ValueError(f"{source}: only positive POSCAR scale factors are supported")
    cell = np.array([[float(value) for value in lines[index].split()[:3]] for index in range(2, 5)], dtype=float) * scale
    symbols = lines[5].split()
    counts = [int(value) for value in lines[6].split()]
    if len(symbols) != len(counts):
        raise ValueError(f"{source}: symbol/count mismatch")
    selective = lines[7].strip().lower().startswith("s")
    mode_index = 8 if selective else 7
    start = mode_index + 1
    atom_count = sum(counts)
    raw = np.array([[float(value) for value in lines[start + index].split()[:3]] for index in range(atom_count)], dtype=float)
    if lines[mode_index].strip().lower().startswith("d"):
        frac = raw
    else:
        frac = raw * scale @ np.linalg.inv(cell)
    flags: list[tuple[str, str, str]] = []
    for index in range(atom_count):
        fields = lines[start + index].split()
        flags.append(tuple(fields[3:6]) if selective else ("T", "T", "T"))
    return Poscar(lines[0], cell, symbols, counts, frac, flags)


def expanded_symbols(poscar: Poscar) -> list[str]:
    return expand_symbols(poscar.symbols, poscar.counts)


def fe110_rule_defaults() -> dict[str, float]:
    site_rules = yaml.safe_load(DEFAULT_SITE_RULES.read_text(encoding="utf-8"))["defaults"]
    analysis_rules = yaml.safe_load(DEFAULT_ANALYSIS_RULES.read_text(encoding="utf-8"))["site_classification"]
    return {
        "z_tolerance": float(site_rules["exposed_layer_tolerance_angstrom"]),
        "pair_tolerance": float(site_rules["pair_class_tolerance_angstrom"]),
        "site_tolerance": float(site_rules["site_deduplication_tolerance_angstrom"]),
        "lateral_tolerance": float(analysis_rules["top_lateral_tolerance_angstrom"]),
    }


minimum_image_delta = minimum_image_delta_xy


def inplane_fractional_distance(cell: np.ndarray, first: np.ndarray, second: np.ndarray) -> float:
    delta = minimum_image_delta(np.asarray(first) - np.asarray(second))
    delta[2] = 0.0
    return float(np.linalg.norm(delta @ cell))


def identify_top_layer(poscar: Poscar, z_tolerance: float) -> np.ndarray:
    symbols = expanded_symbols(poscar)
    cart = poscar.frac @ poscar.cell
    fe_indices = np.array([index for index, symbol in enumerate(symbols) if symbol == "Fe"], dtype=int)
    if not len(fe_indices):
        raise ValueError("clean slab contains no Fe atoms")
    max_z = float(np.max(cart[fe_indices, 2]))
    top = fe_indices[max_z - cart[fe_indices, 2] <= z_tolerance]
    if len(top) < 3:
        raise ValueError(f"top-layer detection returned only {len(top)} Fe atoms")
    return top


def pair_candidates(poscar: Poscar, top_indices: np.ndarray) -> list[PairCandidate]:
    result: list[PairCandidate] = []
    frac = poscar.frac
    for first, second in itertools.combinations(top_indices.tolist(), 2):
        delta = minimum_image_delta(frac[second] - frac[first])
        delta[2] = 0.0
        distance = float(np.linalg.norm(delta @ poscar.cell))
        if distance <= 1e-8:
            continue
        midpoint = (frac[first] + 0.5 * delta) % 1.0
        result.append(PairCandidate(distance, midpoint, (first, second)))
    return result


def cluster_pairs(candidates: list[PairCandidate], tolerance: float) -> list[list[PairCandidate]]:
    groups: list[list[PairCandidate]] = []
    for candidate in sorted(candidates, key=lambda item: item.distance):
        if not groups or abs(candidate.distance - np.mean([item.distance for item in groups[-1]])) > tolerance:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    return groups


def center_score(cell: np.ndarray, frac: np.ndarray) -> float:
    delta = np.array([frac[0] - 0.5, frac[1] - 0.5, 0.0])
    return float(np.linalg.norm(delta @ cell))


def choose_pair_representative(cell: np.ndarray, group: list[PairCandidate]) -> PairCandidate:
    return min(group, key=lambda candidate: center_score(cell, candidate.midpoint))


def deduplicate_points(cell: np.ndarray, points: list[np.ndarray], tolerance: float) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for point in points:
        if all(inplane_fractional_distance(cell, point, prior) > tolerance for prior in unique):
            unique.append(point)
    return unique


def triangle_hollow_candidates(
    poscar: Poscar,
    top_indices: np.ndarray,
    short_distance: float,
    long_distance: float,
    pair_tolerance: float,
    midpoint_tolerance: float,
    all_midpoints: list[np.ndarray],
) -> list[np.ndarray]:
    candidates: list[np.ndarray] = []
    frac = poscar.frac
    for first, second, third in itertools.combinations(top_indices.tolist(), 3):
        second_delta = minimum_image_delta(frac[second] - frac[first])
        third_delta = minimum_image_delta(frac[third] - frac[first])
        side_vectors = (second_delta, third_delta, third_delta - second_delta)
        sides = sorted(float(np.linalg.norm(vector @ poscar.cell)) for vector in side_vectors)
        expected = sorted((short_distance, short_distance, long_distance))
        if any(abs(actual - target) > pair_tolerance for actual, target in zip(sides, expected, strict=True)):
            continue
        center = (frac[first] + (second_delta + third_delta) / 3.0) % 1.0
        if any(inplane_fractional_distance(poscar.cell, center, midpoint) <= midpoint_tolerance for midpoint in all_midpoints):
            continue
        candidates.append(center)
    return deduplicate_points(poscar.cell, candidates, midpoint_tolerance)


def generate_sites(
    poscar: Poscar,
    z_tolerance: float | None = None,
    pair_tolerance: float | None = None,
    site_tolerance: float | None = None,
) -> tuple[dict[str, Site], np.ndarray]:
    defaults = fe110_rule_defaults()
    z_tolerance = defaults["z_tolerance"] if z_tolerance is None else z_tolerance
    pair_tolerance = defaults["pair_tolerance"] if pair_tolerance is None else pair_tolerance
    site_tolerance = defaults["site_tolerance"] if site_tolerance is None else site_tolerance
    symbols = expanded_symbols(poscar)
    if any(symbol != "Fe" for symbol in symbols):
        raise ValueError("site generation requires a clean Fe slab")
    top_indices = identify_top_layer(poscar, z_tolerance)
    candidates = pair_candidates(poscar, top_indices)
    groups = [group for group in cluster_pairs(candidates, pair_tolerance) if np.mean([item.distance for item in group]) > 1.0]
    if len(groups) < 2:
        raise ValueError("fewer than two top-layer Fe-Fe distance classes were found")
    short_group, long_group = groups[:2]
    short = choose_pair_representative(poscar.cell, short_group)
    long = choose_pair_representative(poscar.cell, long_group)
    short_distance = float(np.mean([item.distance for item in short_group]))
    long_distance = float(np.mean([item.distance for item in long_group]))
    if abs(short_distance - long_distance) <= pair_tolerance:
        raise ValueError("short- and long-bridge distance classes are not distinct")
    top = min(top_indices.tolist(), key=lambda index: center_score(poscar.cell, poscar.frac[index]))
    midpoints = [candidate.midpoint for candidate in candidates]
    hollow_candidates = triangle_hollow_candidates(
        poscar,
        top_indices,
        short_distance,
        long_distance,
        pair_tolerance,
        site_tolerance,
        midpoints,
    )
    if not hollow_candidates:
        raise ValueError("no true three-coordinate hollow center was found")
    hollow = min(hollow_candidates, key=lambda point: center_score(poscar.cell, point))
    sites = {
        "top": Site("top", poscar.frac[top].copy(), (top,), None),
        "short_bridge": Site("short_bridge", short.midpoint.copy(), short.indices, short.distance),
        "long_bridge": Site("long_bridge", long.midpoint.copy(), long.indices, long.distance),
        "hollow": Site("hollow", hollow.copy(), tuple(), None),
    }
    validate_site_set(poscar, sites, top_indices, short_distance, long_distance, site_tolerance)
    return sites, top_indices


def classify_fe110_anchor_site(
    poscar: Poscar,
    anchor_frac: np.ndarray,
    *,
    reference_poscar: Poscar | None = None,
    z_tolerance: float | None = None,
    pair_tolerance: float | None = None,
    lateral_tolerance: float | None = None,
    hollow_deduplication_tolerance: float | None = None,
) -> tuple[str, float]:
    defaults = fe110_rule_defaults()
    z_tolerance = defaults["z_tolerance"] if z_tolerance is None else z_tolerance
    pair_tolerance = defaults["pair_tolerance"] if pair_tolerance is None else pair_tolerance
    lateral_tolerance = defaults["lateral_tolerance"] if lateral_tolerance is None else lateral_tolerance
    hollow_deduplication_tolerance = (
        defaults["site_tolerance"] if hollow_deduplication_tolerance is None else hollow_deduplication_tolerance
    )
    reference = reference_poscar or poscar
    reference_anchor_frac = (np.asarray(anchor_frac) @ poscar.cell) @ np.linalg.inv(reference.cell)
    distances = fe110_anchor_site_distances(
        reference,
        reference_anchor_frac,
        z_tolerance=z_tolerance,
        pair_tolerance=pair_tolerance,
        hollow_deduplication_tolerance=hollow_deduplication_tolerance,
    )
    name, distance = min(distances.items(), key=lambda item: item[1])
    return (name, distance) if distance <= lateral_tolerance else ("unknown", distance)


def fe110_anchor_site_distances(
    poscar: Poscar,
    anchor_frac: np.ndarray,
    *,
    z_tolerance: float | None = None,
    pair_tolerance: float | None = None,
    hollow_deduplication_tolerance: float | None = None,
) -> dict[str, float]:
    defaults = fe110_rule_defaults()
    z_tolerance = defaults["z_tolerance"] if z_tolerance is None else z_tolerance
    pair_tolerance = defaults["pair_tolerance"] if pair_tolerance is None else pair_tolerance
    hollow_deduplication_tolerance = (
        defaults["site_tolerance"] if hollow_deduplication_tolerance is None else hollow_deduplication_tolerance
    )
    top_indices = identify_top_layer(poscar, z_tolerance)
    candidates = pair_candidates(poscar, top_indices)
    groups = [group for group in cluster_pairs(candidates, pair_tolerance) if np.mean([item.distance for item in group]) > 1.0]
    if len(groups) < 2:
        raise ValueError("fewer than two top-layer Fe-Fe distance classes were found")
    short_distance = float(np.mean([item.distance for item in groups[0]]))
    long_distance = float(np.mean([item.distance for item in groups[1]]))
    top_distance = min(inplane_fractional_distance(poscar.cell, anchor_frac, poscar.frac[index]) for index in top_indices)
    distances = {"top": top_distance}
    for name, target in (("short_bridge", short_distance), ("long_bridge", long_distance)):
        distances[name] = min(
            inplane_fractional_distance(poscar.cell, anchor_frac, candidate.midpoint)
            for candidate in candidates
            if abs(candidate.distance - target) <= pair_tolerance
        )
    hollow_centers = triangle_hollow_candidates(
        poscar,
        top_indices,
        short_distance,
        long_distance,
        pair_tolerance,
        hollow_deduplication_tolerance,
        [candidate.midpoint for candidate in candidates],
    )
    if hollow_centers:
        distances["hollow"] = min(inplane_fractional_distance(poscar.cell, anchor_frac, center) for center in hollow_centers)
    return distances


def validate_site_set(
    poscar: Poscar,
    sites: dict[str, Site],
    top_indices: np.ndarray,
    short_distance: float,
    long_distance: float,
    tolerance: float,
) -> None:
    if set(sites) != set(SITE_NAMES):
        raise ValueError(f"site set must be {SITE_NAMES}")
    for first, second in itertools.combinations(SITE_NAMES, 2):
        if inplane_fractional_distance(poscar.cell, sites[first].frac, sites[second].frac) <= tolerance:
            raise ValueError(f"duplicate sites: {first} and {second}")
    if abs(float(sites["short_bridge"].support_distance) - short_distance) > tolerance:
        raise ValueError("short_bridge does not use the shortest Fe-Fe pair class")
    if abs(float(sites["long_bridge"].support_distance) - long_distance) > tolerance:
        raise ValueError("long_bridge does not use the longer Fe-Fe pair class")
    for candidate in pair_candidates(poscar, top_indices):
        if inplane_fractional_distance(poscar.cell, sites["hollow"].frac, candidate.midpoint) <= tolerance:
            raise ValueError("hollow coincides with an Fe-Fe midpoint")


def load_adsorbates(path: Path) -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("adsorbates"), dict):
        raise ValueError(f"{path}: missing adsorbates mapping")
    return payload["adsorbates"]


def validate_adsorbate(name: str, metadata: dict[str, Any]) -> tuple[list[str], np.ndarray, int | None, float]:
    atom_symbols = list(metadata["atom_symbols"])
    relative = np.asarray(metadata["relative_cartesian_angstrom"], dtype=float)
    anchor_mode = str(metadata.get("anchor_mode", "atom"))
    target = float(metadata["recommended_fe_anchor_distance_angstrom"])
    allowed = [float(value) for value in metadata["allowed_fe_anchor_distance_angstrom"]]
    if relative.shape != (len(atom_symbols), 3):
        raise ValueError(f"{name}: relative coordinate count does not match atom_symbols")
    if anchor_mode == "atom":
        anchor_index = int(metadata["anchor_index"])
        anchor_atom = str(metadata["anchor_atom"])
        if not 0 <= anchor_index < len(atom_symbols) or atom_symbols[anchor_index] != anchor_atom:
            raise ValueError(f"{name}: anchor metadata is inconsistent")
        if np.linalg.norm(relative[anchor_index]) > 1e-10:
            raise ValueError(f"{name}: anchor relative coordinate must be zero")
    elif anchor_mode == "reference_point":
        anchor_index = None
        if metadata.get("anchor_atom") != "molecular_center":
            raise ValueError(f"{name}: reference-point placement requires anchor_atom=molecular_center")
    else:
        raise ValueError(f"{name}: unsupported anchor_mode {anchor_mode}")
    if not allowed[0] <= target <= allowed[1]:
        raise ValueError(f"{name}: recommended Fe-anchor distance is outside its allowed range")
    rule = str(metadata["orientation_rule"])
    non_anchor = relative if anchor_index is None else np.delete(relative, anchor_index, axis=0)
    if rule == "non_anchor_atoms_above" and (not len(non_anchor) or np.any(non_anchor[:, 2] <= 0.0)):
        raise ValueError(f"{name}: orientation rule requires every non-anchor atom above the anchor")
    if rule == "non_anchor_atoms_above_or_coplanar" and (not len(non_anchor) or np.any(non_anchor[:, 2] < -1e-6)):
        raise ValueError(f"{name}: orientation rule forbids atoms below the anchor")
    if rule == "anchor_below_other_atoms" and (not len(non_anchor) or np.any(non_anchor[:, 2] <= 0.0)):
        raise ValueError(f"{name}: anchor atom must be below every other atom")
    if rule == "molecular_axis_parallel" and (anchor_index is not None or len(relative) != 2 or np.max(np.abs(relative[:, 2])) > 1e-5):
        raise ValueError(f"{name}: molecular-axis placement must be a two-atom reference-point anchor parallel to xy")
    if rule == "anchor_only" and len(non_anchor):
        raise ValueError(f"{name}: anchor_only is valid only for atomic adsorbates")
    return atom_symbols, relative, anchor_index, target


def anchor_cartesian_position(poscar: Poscar, site: Site, target_distance: float) -> np.ndarray:
    cart = poscar.frac @ poscar.cell
    surface_z = float(np.max(cart[:, 2]))
    anchor = site.frac @ poscar.cell
    support = [cart[index] for index in site.support_indices] if site.support_indices else list(cart)

    def nearest(distance_z: float) -> float:
        trial = anchor.copy()
        trial[2] = distance_z
        return min(pbc_xy_distance(poscar.cell, trial, atom) for atom in support)

    lower = surface_z
    upper = surface_z + 5.0
    if nearest(lower) > target_distance:
        raise ValueError(f"{site.name}: target distance is shorter than the lateral Fe-anchor separation")
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if nearest(midpoint) < target_distance:
            lower = midpoint
        else:
            upper = midpoint
    anchor[2] = (lower + upper) / 2.0
    return anchor


def grouped_adsorbate_counts(atom_symbols: list[str], species_order: list[str]) -> list[int]:
    expanded = [symbol for symbol in species_order for _ in range(atom_symbols.count(symbol))]
    if expanded != atom_symbols:
        raise ValueError("atom_symbols must be grouped according to species_order")
    return [atom_symbols.count(symbol) for symbol in species_order]


def place_adsorbate(poscar: Poscar, site: Site, name: str, metadata: dict[str, Any]) -> Poscar:
    atom_symbols, relative, anchor_index, target = validate_adsorbate(name, metadata)
    target = float(metadata.get("site_distance_overrides_angstrom", {}).get(site.name, target))
    allowed = [float(value) for value in metadata["allowed_fe_anchor_distance_angstrom"]]
    if not allowed[0] <= target <= allowed[1]:
        raise ValueError(f"{name}/{site.name}: site-specific Fe-anchor distance is outside its allowed range")
    species_order = list(metadata["species_order"])
    adsorbate_counts = grouped_adsorbate_counts(atom_symbols, species_order)
    anchor = anchor_cartesian_position(poscar, site, target)
    adsorbate_cart = anchor + relative
    adsorbate_frac = adsorbate_cart @ np.linalg.inv(poscar.cell)
    adsorbate_frac[:, :2] %= 1.0
    combined = np.vstack((poscar.frac, adsorbate_frac))
    flags = [*poscar.flags, *(("T", "T", "T") for _ in atom_symbols)]
    return Poscar(
        comment=f"Fe110 {name} {site.name}",
        cell=poscar.cell.copy(),
        symbols=[*poscar.symbols, *species_order],
        counts=[*poscar.counts, *adsorbate_counts],
        frac=combined,
        flags=flags,
    )


def write_poscar(path: Path, poscar: Poscar) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [poscar.comment, "1.0"]
    lines.extend(" ".join(f"{value:.16f}" for value in vector) for vector in poscar.cell)
    lines.extend((" ".join(poscar.symbols), " ".join(str(value) for value in poscar.counts), "Selective dynamics", "Direct"))
    for coordinate, flags in zip(poscar.frac, poscar.flags, strict=True):
        lines.append("  " + "  ".join(f"{value:.16f}" for value in coordinate) + "   " + "   ".join(flags))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
