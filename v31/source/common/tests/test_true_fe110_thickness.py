from __future__ import annotations

import math

import numpy as np

from setup_true_fe110_thickness_retest import LATTICE_A, build_slab, layer_indices


def test_true_fe110_builder_has_expected_layers_and_spacing() -> None:
    slab = build_slab(7)
    groups = layer_indices(slab)
    centers = [slab.positions[group, 2].mean() for group in groups]

    assert len(slab) == 63
    assert len(groups) == 7
    assert all(len(group) == 9 for group in groups)
    assert np.allclose(np.diff(centers), LATTICE_A / math.sqrt(2.0), atol=1e-8)


def test_true_fe110_builder_fixes_bottom_two_layers() -> None:
    slab = build_slab(5)
    fixed = {int(index) for constraint in slab.constraints if hasattr(constraint, "get_indices") for index in constraint.get_indices()}
    expected = {index for group in layer_indices(slab)[:2] for index in group}

    assert fixed == expected
