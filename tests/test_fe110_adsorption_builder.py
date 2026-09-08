from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    SITE_NAMES,
    classify_fe110_anchor_site,
    generate_sites,
    inplane_fractional_distance,
    load_adsorbates,
    place_adsorbate,
    pbc_xy_distance,
    read_poscar,
)


ROOT = Path(__file__).resolve().parents[1]
SLAB = ROOT / "calculations" / "true_fe110_clean_20260629" / "POSCAR"
METADATA = ROOT / "configs" / "fe110_adsorbates_step12a.yaml"
PILOT_METADATA = ROOT / "configs" / "fe110_adsorbates_h2_chx_pilot.yaml"


def test_site_generator_returns_four_distinct_fe110_sites() -> None:
    slab = read_poscar(SLAB)
    sites, top_indices = generate_sites(slab)

    assert set(sites) == set(SITE_NAMES)
    assert len(top_indices) == 9
    assert abs(float(sites["short_bridge"].support_distance) - 2.448) < 0.05
    assert abs(float(sites["long_bridge"].support_distance) - 2.827) < 0.05
    assert len(sites["top"].support_indices) == 1
    assert sites["short_bridge"].support_indices != sites["long_bridge"].support_indices
    for first, second in itertools.combinations(SITE_NAMES, 2):
        assert inplane_fractional_distance(slab.cell, sites[first].frac, sites[second].frac) > 0.05


def test_hollow_is_not_any_top_layer_pair_midpoint() -> None:
    slab = read_poscar(SLAB)
    sites, top_indices = generate_sites(slab)
    hollow = sites["hollow"].frac

    for first, second in itertools.combinations(top_indices.tolist(), 2):
        delta = slab.frac[second] - slab.frac[first]
        delta[:2] -= np.round(delta[:2])
        midpoint = (slab.frac[first] + 0.5 * delta) % 1.0
        assert inplane_fractional_distance(slab.cell, hollow, midpoint) > 0.05


def test_relaxed_site_classification_keeps_clean_slab_pair_topology() -> None:
    clean = read_poscar(SLAB)
    sites, top_indices = generate_sites(clean)
    distorted_frac = clean.frac.copy()
    distorted_frac[top_indices[::2], 0] += 0.03
    distorted = Poscar(
        clean.comment,
        clean.cell.copy(),
        clean.symbols.copy(),
        clean.counts.copy(),
        distorted_frac,
        clean.flags.copy(),
    )

    site, offset = classify_fe110_anchor_site(
        distorted,
        sites["long_bridge"].frac,
        reference_poscar=clean,
    )

    assert site == "long_bridge"
    assert offset < 1e-6


def test_builder_generates_anchor_based_step12a_structures(tmp_path: Path) -> None:
    slab = read_poscar(SLAB)
    sites, _ = generate_sites(slab)
    adsorbates = load_adsorbates(METADATA)

    for name, metadata in adsorbates.items():
        allowed = metadata["allowed_fe_anchor_distance_angstrom"]
        for site_name in SITE_NAMES:
            structure = place_adsorbate(slab, sites[site_name], name, metadata)
            anchor_index = sum(slab.counts) + int(metadata["anchor_index"])
            classified_site, offset = classify_fe110_anchor_site(structure, structure.frac[anchor_index])
            anchor = structure.frac[anchor_index] @ structure.cell
            slab_cart = structure.frac[: sum(slab.counts)] @ structure.cell
            nearest = min(pbc_xy_distance(structure.cell, anchor, atom) for atom in slab_cart)
            assert allowed[0] <= nearest <= allowed[1]
            assert classified_site == site_name
            assert offset < 1e-6
            assert np.allclose(structure.frac[: sum(slab.counts)], slab.frac)
            assert structure.flags[: sum(slab.counts)] == slab.flags


def test_builder_supports_h2_molecular_center_reference(tmp_path: Path) -> None:
    slab = read_poscar(SLAB)
    sites, _ = generate_sites(slab)
    adsorbates = load_adsorbates(PILOT_METADATA)
    structure = place_adsorbate(slab, sites["top"], "H2", adsorbates["H2"])
    adsorbate = structure.frac[sum(slab.counts) :] @ structure.cell
    center = np.mean(adsorbate, axis=0)
    bond = np.linalg.norm(adsorbate[1] - adsorbate[0])
    classified_site, offset = classify_fe110_anchor_site(structure, center @ np.linalg.inv(structure.cell))

    assert abs(float(bond) - 0.750595) < 1e-5
    assert abs(float(adsorbate[1, 2] - adsorbate[0, 2])) < 1e-5
    assert classified_site == "top"
    assert offset < 1e-6

    ch3 = place_adsorbate(slab, sites["long_bridge"], "CH3", adsorbates["CH3"])
    carbon = ch3.frac[sum(slab.counts)] @ ch3.cell
    slab_cart = ch3.frac[: sum(slab.counts)] @ ch3.cell
    nearest_carbon_fe = min(pbc_xy_distance(ch3.cell, carbon, atom) for atom in slab_cart)
    assert abs(float(nearest_carbon_fe) - 2.3) < 1e-5
