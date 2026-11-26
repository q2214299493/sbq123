from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .build_fe110_adsorption import Poscar, anchor_cartesian_position
from .c2_coads_geometry import (
    GEOMETRY,
    all_hollows,
    build_eta2_cco_lifted,
    build_kappa_cco_tilted,
    centered_pair,
    choose_adjacent_long_bridge_o,
    choose_separated_o,
    combine,
    diagonal_c2_cart,
    h_lb_h_c2_cart,
    pair_groups,
    site_from_pair,
)


CANDIDATE_SITE_LABELS = {
    "CplusO_C-lb_O-h_adj": "C*+O*/C@lb+O@h_adj",
    "C2O_kappa-Calpha_lb_tilted": "C₂O*/κ-Cα/lb_tilted",
    "C2O_eta2CalphaCbeta_h-lb-h": "C₂O**/η²(Cα,Cβ)/h-lb-h",
    "C2_eta2CC_h-lb-h": "C₂**/η²(C,C)/h-lb-h",
    "C2plusO_eta2CC_h-lb-h_O-lb_adj": "C₂**/η²(C,C)/h-lb-h+O@lb_adj",
    "CplusO_C-lb_O-lb-adj": "C*+O*/C@lb+O@lb/adj",
    "C2O_eta2CalphaCbeta_C2-2-derived": "C₂O**/η²-CαCβ/C₂-2-derived",
    "C2_eta2CC_C2-2-diagonal": "C₂**/η²-CC/C₂-2-diagonal",
    "C2plusO_C2-1_O-h-adj": "C₂**/C₂-1+O@h/adj",
    "C2plusO_C2-2-diagonal_O-lb-adj": "C₂**/C₂-2-diagonal+O@lb/adj",
    "C2plusO_C2-2-diagonal_O-h-adj": "C₂**/C₂-2-diagonal+O@h/adj",
}


@dataclass(frozen=True)
class CandidateDefinition:
    name: str
    species: str
    structure: Poscar
    carbon_count: int
    intended_bonds: tuple[tuple[int, int, str], ...]
    support_indices: tuple[int, ...]
    oxygen_site: dict[str, Any] | None = None

    @property
    def site_label(self) -> str:
        return CANDIDATE_SITE_LABELS[self.name]


def initial_candidate_definitions(slab: Poscar) -> list[CandidateDefinition]:
    short_group, long_group, top = pair_groups(slab)
    long_pair = centered_pair(slab.cell, long_group)
    long_site = site_from_pair("long_bridge", long_pair)
    hollows = all_hollows(slab, top, short_group, long_group)
    c_long = anchor_cartesian_position(slab, long_site, GEOMETRY["fe_c_angstrom"]).reshape(1, 3)
    c2_h_lb_h = h_lb_h_c2_cart(slab, hollows, long_pair)
    co_hollow, o_for_c, _ = choose_separated_o(slab, hollows, c_long)
    kappa_c2o_cart, kappa_c2o_oxygen = build_kappa_cco_tilted(slab, long_site, long_pair)
    eta2_c2o_oxygen = build_eta2_cco_lifted(slab, c2_h_lb_h)
    c2o_long_bridge, o_for_c2, _ = choose_adjacent_long_bridge_o(slab, long_group, long_pair, c2_h_lb_h)
    return [
        CandidateDefinition(
            "CplusO_C-lb_O-h_adj",
            "C+O",
            combine(slab, "Fe110 CplusO C-lb O-h-adj", c_long, o_for_c),
            1,
            ((0, 1, "C1-O1_separation"),),
            tuple(long_pair.indices),
            {"class": "hollow", "fractional_xy": co_hollow.frac[:2].tolist()},
        ),
        CandidateDefinition(
            "C2O_kappa-Calpha_lb_tilted",
            "C2O",
            combine(slab, "Fe110 C2O kappa-Calpha lb tilted", kappa_c2o_cart, kappa_c2o_oxygen),
            2,
            ((0, 1, "Calpha-Cbeta"), (1, 2, "Cbeta-O1")),
            tuple(long_pair.indices),
        ),
        CandidateDefinition(
            "C2O_eta2CalphaCbeta_h-lb-h",
            "C2O",
            combine(slab, "Fe110 C2O eta2-Calpha-Cbeta h-lb-h O-up", c2_h_lb_h, eta2_c2o_oxygen),
            2,
            ((0, 1, "Calpha-Cbeta"), (1, 2, "Cbeta-O1")),
            tuple(long_pair.indices),
        ),
        CandidateDefinition(
            "C2_eta2CC_h-lb-h",
            "C2",
            combine(slab, "Fe110 C2 eta2-CC h-lb-h", c2_h_lb_h),
            2,
            ((0, 1, "C1-C2"),),
            tuple(long_pair.indices),
        ),
        CandidateDefinition(
            "C2plusO_eta2CC_h-lb-h_O-lb_adj",
            "C2+O",
            combine(slab, "Fe110 C2plusO eta2-CC h-lb-h O-lb-adj", c2_h_lb_h, o_for_c2),
            2,
            ((0, 1, "C1-C2"), (0, 2, "C1-O1_separation"), (1, 2, "C2-O1_separation")),
            tuple(long_pair.indices),
            {"class": "long_bridge", "fractional_xy": c2o_long_bridge.frac[:2].tolist()},
        ),
    ]


def missing_candidate_definitions(slab: Poscar) -> list[CandidateDefinition]:
    short_group, long_group, top = pair_groups(slab)
    short_pair = centered_pair(slab.cell, short_group)
    long_pair = centered_pair(slab.cell, long_group)
    long_site = site_from_pair("long_bridge", long_pair)
    hollows = all_hollows(slab, top, short_group, long_group)
    c_long = anchor_cartesian_position(slab, long_site, GEOMETRY["fe_c_angstrom"]).reshape(1, 3)
    c2_1 = h_lb_h_c2_cart(slab, hollows, long_pair)
    c2_2 = diagonal_c2_cart(slab, hollows, short_pair)
    c_lb_site, o_c_lb, _ = choose_adjacent_long_bridge_o(slab, long_group, long_pair, c_long)
    c2_1_h_site, o_c2_1_h, _ = choose_separated_o(slab, hollows, c2_1, minimum_separation=2.30, maximum_separation=2.80)
    c2_2_lb_site, o_c2_2_lb, _ = choose_adjacent_long_bridge_o(slab, long_group, None, c2_2)
    c2_2_h_site, o_c2_2_h, _ = choose_separated_o(slab, hollows, c2_2, minimum_separation=2.30, maximum_separation=2.80)
    c2o_2_oxygen = build_eta2_cco_lifted(slab, c2_2)
    return [
        CandidateDefinition(
            "CplusO_C-lb_O-lb-adj",
            "C+O",
            combine(slab, "Fe110 CplusO C-lb O-lb-adj", c_long, o_c_lb),
            1,
            ((0, 1, "C1-O1_separation"),),
            tuple(long_pair.indices),
            {"class": "long_bridge", "fractional_xy": c_lb_site.frac[:2].tolist()},
        ),
        CandidateDefinition(
            "C2O_eta2CalphaCbeta_C2-2-derived",
            "C2O",
            combine(slab, "Fe110 C2O eta2-Calpha-Cbeta C2-2-derived O-up", c2_2, c2o_2_oxygen),
            2,
            ((0, 1, "Calpha-Cbeta"), (1, 2, "Cbeta-O1")),
            tuple(short_pair.indices),
        ),
        CandidateDefinition(
            "C2_eta2CC_C2-2-diagonal",
            "C2",
            combine(slab, "Fe110 C2 eta2-CC C2-2-diagonal", c2_2),
            2,
            ((0, 1, "C1-C2"),),
            tuple(short_pair.indices),
        ),
        CandidateDefinition(
            "C2plusO_C2-1_O-h-adj",
            "C2+O",
            combine(slab, "Fe110 C2plusO C2-1 O-h-adj", c2_1, o_c2_1_h),
            2,
            ((0, 1, "C1-C2"), (0, 2, "C1-O1_separation"), (1, 2, "C2-O1_separation")),
            tuple(long_pair.indices),
            {"class": "hollow", "fractional_xy": c2_1_h_site.frac[:2].tolist()},
        ),
        CandidateDefinition(
            "C2plusO_C2-2-diagonal_O-lb-adj",
            "C2+O",
            combine(slab, "Fe110 C2plusO C2-2-diagonal O-lb-adj", c2_2, o_c2_2_lb),
            2,
            ((0, 1, "C1-C2"), (0, 2, "C1-O1_separation"), (1, 2, "C2-O1_separation")),
            tuple(short_pair.indices),
            {"class": "long_bridge", "fractional_xy": c2_2_lb_site.frac[:2].tolist()},
        ),
        CandidateDefinition(
            "C2plusO_C2-2-diagonal_O-h-adj",
            "C2+O",
            combine(slab, "Fe110 C2plusO C2-2-diagonal O-h-adj", c2_2, o_c2_2_h),
            2,
            ((0, 1, "C1-C2"), (0, 2, "C1-O1_separation"), (1, 2, "C2-O1_separation")),
            tuple(short_pair.indices),
            {"class": "hollow", "fractional_xy": c2_2_h_site.frac[:2].tolist()},
        ),
    ]
