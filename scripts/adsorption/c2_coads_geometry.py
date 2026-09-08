from __future__ import annotations

import math

import numpy as np

from scripts.workflow_geometry import minimum_image_delta_xy, pbc_xy_distance, pbc_xy_vector

from .build_fe110_adsorption import (
    PairCandidate,
    Poscar,
    Site,
    anchor_cartesian_position,
    cluster_pairs,
    fe110_rule_defaults,
    identify_top_layer,
    pair_candidates,
    triangle_hollow_candidates,
)


GEOMETRY = {
    "fe_c_angstrom": 1.90,
    "fe_o_angstrom": 1.95,
    "cco_cc_angstrom": 1.318,
    "cco_co_angstrom": 1.171,
    "separated_co_min_angstrom": 2.70,
    "kappa_cco_tilt_from_surface_normal_degrees": 25.0,
    "eta2_cco_o_lift_from_surface_degrees": 55.0,
    "c2_diagonal_cc_angstrom": 1.38,
}


def pair_groups(slab: Poscar) -> tuple[list[PairCandidate], list[PairCandidate], np.ndarray]:
    tolerance = fe110_rule_defaults()["pair_tolerance"]
    top = identify_top_layer(slab, fe110_rule_defaults()["z_tolerance"])
    groups = [
        group
        for group in cluster_pairs(pair_candidates(slab, top), tolerance)
        if np.mean([item.distance for item in group]) > 1.0
    ]
    if len(groups) < 2:
        raise ValueError("Fe(110) slab does not expose distinct short- and long-bridge pair classes")
    return groups[0], groups[1], top


def centered_pair(cell: np.ndarray, group: list[PairCandidate]) -> PairCandidate:
    return min(group, key=lambda item: float(np.linalg.norm((item.midpoint[:2] - 0.5) @ cell[:2, :2])))


def site_from_pair(name: str, pair: PairCandidate) -> Site:
    return Site(name, pair.midpoint.copy(), pair.indices, pair.distance)


def all_hollows(slab: Poscar, top: np.ndarray, short: list[PairCandidate], long: list[PairCandidate]) -> list[Site]:
    tolerance = fe110_rule_defaults()
    short_distance = float(np.mean([item.distance for item in short]))
    long_distance = float(np.mean([item.distance for item in long]))
    candidates = pair_candidates(slab, top)
    centers = triangle_hollow_candidates(
        slab,
        top,
        short_distance,
        long_distance,
        tolerance["pair_tolerance"],
        tolerance["site_tolerance"],
        [item.midpoint for item in candidates],
    )
    return [Site("hollow", center, tuple(), None) for center in centers]


def h_lb_h_c2_cart(slab: Poscar, hollows: list[Site], long_pair: PairCandidate) -> np.ndarray:
    """Return two Cartesian Å carbon positions in the reviewed hollow–long-bridge–hollow motif."""
    candidates: list[tuple[float, float, Site, Site]] = []
    for index, first in enumerate(hollows):
        for second in hollows[index + 1 :]:
            delta = minimum_image_delta_xy(second.frac - first.frac)
            midpoint = (first.frac + 0.5 * delta) % 1.0
            midpoint_delta = minimum_image_delta_xy(midpoint - long_pair.midpoint)
            candidates.append(
                (
                    float(np.linalg.norm(midpoint_delta @ slab.cell)),
                    float(np.linalg.norm(delta @ slab.cell)),
                    first,
                    second,
                )
            )
    midpoint_distance, _, first, second = min(candidates, key=lambda item: (item[0], item[1]))
    if midpoint_distance > fe110_rule_defaults()["site_tolerance"]:
        raise ValueError("no h-lb-h hollow pair straddles the selected long bridge")
    return np.vstack(
        (
            anchor_cartesian_position(slab, first, GEOMETRY["fe_c_angstrom"]),
            anchor_cartesian_position(slab, second, GEOMETRY["fe_c_angstrom"]),
        )
    )


def diagonal_c2_cart(slab: Poscar, hollows: list[Site], short_pair: PairCandidate) -> np.ndarray:
    """Return the reviewed diagonal C₂ Cartesian Å coordinates under slab x/y PBC."""
    candidates: list[tuple[float, float, Site, Site, np.ndarray]] = []
    for index, first in enumerate(hollows):
        for second in hollows[index + 1 :]:
            delta = minimum_image_delta_xy(second.frac - first.frac)
            midpoint = (first.frac + 0.5 * delta) % 1.0
            midpoint_delta = minimum_image_delta_xy(midpoint - short_pair.midpoint)
            lateral = delta @ slab.cell
            lateral[2] = 0.0
            candidates.append(
                (float(np.linalg.norm(midpoint_delta @ slab.cell)), float(np.linalg.norm(lateral)), first, second, midpoint)
            )
    midpoint_distance, _, first, second, midpoint = min(candidates, key=lambda item: (item[0], item[1]))
    if midpoint_distance > fe110_rule_defaults()["site_tolerance"]:
        raise ValueError("no hollow pair straddles the selected short bridge")
    axis = pbc_xy_vector(slab.cell, second.frac @ slab.cell, first.frac @ slab.cell)
    axis[2] = 0.0
    axis /= np.linalg.norm(axis)
    midpoint_cart = midpoint @ slab.cell
    half_vector = 0.5 * GEOMETRY["c2_diagonal_cc_angstrom"] * axis
    positions = []
    for xy_cart in (midpoint_cart - half_vector, midpoint_cart + half_vector):
        frac = xy_cart @ np.linalg.inv(slab.cell)
        frac[:2] %= 1.0
        positions.append(anchor_cartesian_position(slab, Site("diagonal_hollow", frac, tuple(), None), GEOMETRY["fe_c_angstrom"]))
    return np.vstack(positions)


def inplane_axis(cell: np.ndarray, first: np.ndarray, second: np.ndarray) -> np.ndarray:
    axis = pbc_xy_vector(cell, second, first)
    axis[2] = 0.0
    return axis / np.linalg.norm(axis)


def build_kappa_cco_tilted(slab: Poscar, long_site: Site, long_pair: PairCandidate) -> tuple[np.ndarray, np.ndarray]:
    alpha = anchor_cartesian_position(slab, long_site, GEOMETRY["fe_c_angstrom"])
    slab_cart = slab.frac @ slab.cell
    lateral = inplane_axis(slab.cell, slab_cart[long_pair.indices[0]], slab_cart[long_pair.indices[1]])
    angle = math.radians(GEOMETRY["kappa_cco_tilt_from_surface_normal_degrees"])
    direction = lateral * math.sin(angle) + np.array([0.0, 0.0, math.cos(angle)])
    beta = alpha + GEOMETRY["cco_cc_angstrom"] * direction
    oxygen = beta + GEOMETRY["cco_co_angstrom"] * direction
    return np.vstack((alpha, beta)), oxygen


def build_eta2_cco_lifted(slab: Poscar, carbon_cart: np.ndarray) -> np.ndarray:
    outward = inplane_axis(slab.cell, carbon_cart[0], carbon_cart[1])
    angle = math.radians(GEOMETRY["eta2_cco_o_lift_from_surface_degrees"])
    direction = outward * math.cos(angle) + np.array([0.0, 0.0, math.sin(angle)])
    return carbon_cart[1] + GEOMETRY["cco_co_angstrom"] * direction


def choose_separated_o(
    slab: Poscar,
    hollows: list[Site],
    carbon_cart: np.ndarray,
    minimum_separation: float | None = None,
    maximum_separation: float | None = None,
) -> tuple[Site, np.ndarray, float]:
    """Choose a hollow O site whose Cartesian C–O separation satisfies Å bounds."""
    lower_bound = GEOMETRY["separated_co_min_angstrom"] if minimum_separation is None else minimum_separation
    choices: list[tuple[float, Site, np.ndarray]] = []
    for site in hollows:
        oxygen = anchor_cartesian_position(slab, site, GEOMETRY["fe_o_angstrom"])
        separation = min(pbc_xy_distance(slab.cell, oxygen, carbon) for carbon in carbon_cart)
        if separation >= lower_bound and (maximum_separation is None or separation <= maximum_separation):
            choices.append((separation, site, oxygen))
    if not choices:
        raise ValueError("no hollow site satisfies the separated C-O distance gate")
    separation, site, oxygen = min(choices, key=lambda item: item[0])
    return site, oxygen, separation


def choose_adjacent_long_bridge_o(
    slab: Poscar,
    long_pairs: list[PairCandidate],
    occupied: PairCandidate | None,
    carbon_cart: np.ndarray,
) -> tuple[Site, np.ndarray, float]:
    """Choose an unoccupied long-bridge O site using Cartesian Å C–O distances."""
    choices: list[tuple[float, Site, np.ndarray]] = []
    for pair in long_pairs:
        if occupied is not None:
            midpoint_delta = minimum_image_delta_xy(pair.midpoint - occupied.midpoint)
            if np.linalg.norm(midpoint_delta @ slab.cell) <= fe110_rule_defaults()["site_tolerance"]:
                continue
        site = site_from_pair("long_bridge", pair)
        oxygen = anchor_cartesian_position(slab, site, GEOMETRY["fe_o_angstrom"])
        separation = min(pbc_xy_distance(slab.cell, oxygen, carbon) for carbon in carbon_cart)
        if separation >= GEOMETRY["separated_co_min_angstrom"]:
            choices.append((separation, site, oxygen))
    if not choices:
        raise ValueError("no adjacent unoccupied long bridge satisfies the separated C-O distance gate")
    separation, site, oxygen = min(choices, key=lambda item: item[0])
    return site, oxygen, separation


def combine(slab: Poscar, comment: str, carbon_cart: np.ndarray, oxygen_cart: np.ndarray | None = None) -> Poscar:
    """Append Cartesian Å adsorbate coordinates while preserving slab atom order and flags."""
    adsorbate_cart = carbon_cart if oxygen_cart is None else np.vstack((carbon_cart, oxygen_cart))
    adsorbate_frac = adsorbate_cart @ np.linalg.inv(slab.cell)
    adsorbate_frac[:, :2] %= 1.0
    symbols = [*slab.symbols, "C"]
    counts = [*slab.counts, len(carbon_cart)]
    if oxygen_cart is not None:
        symbols.append("O")
        counts.append(1)
    return Poscar(
        comment=comment,
        cell=slab.cell.copy(),
        symbols=symbols,
        counts=counts,
        frac=np.vstack((slab.frac, adsorbate_frac)),
        flags=[*slab.flags, *(("T", "T", "T") for _ in range(len(adsorbate_cart)))],
    )
