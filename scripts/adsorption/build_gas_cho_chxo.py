#!/usr/bin/env python3
"""Build reviewable gas-phase VASP relaxations for CHO/CH2O/CH3O/CH4O."""

from __future__ import annotations

import math
from pathlib import Path

from .gas_vasp_common import CENTER, add, build_species, carbonyl_with_hydrogens, run_builder, tetrahedral_methyl_hydrogens


def formyl_coords() -> tuple[tuple[float, float, float], ...]:
    return carbonyl_with_hydrogens(co_bond=1.18, ch_bond=1.10, hydrogen_count=1)


def formaldehyde_coords() -> tuple[tuple[float, float, float], ...]:
    return carbonyl_with_hydrogens(co_bond=1.21, ch_bond=1.10, hydrogen_count=2)


def methoxy_coords() -> tuple[tuple[float, float, float], ...]:
    co = 1.43
    hydrogens = tetrahedral_methyl_hydrogens(1.09)
    return (CENTER, add(CENTER, (0.0, 0.0, -co)), *hydrogens)


def methanol_coords() -> tuple[tuple[float, float, float], ...]:
    co = 1.43
    oh = 0.96
    coh = math.radians(108.5)
    oxygen = add(CENTER, (0.0, 0.0, -co))
    methyl_h = tetrahedral_methyl_hydrogens(1.09)
    hydroxyl_h = add(oxygen, (oh * math.sin(coh), 0.0, oh * math.cos(coh)))
    return (CENTER, oxygen, *methyl_h, hydroxyl_h)


SPECIES = {
    "CHO": {
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 1),
        "coords": formyl_coords,
        "ispin": 2,
        "magmom": "1*1.0 1*0.0 1*0.0",
        "nupdown": 1,
    },
    "CH2O": {
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 2),
        "coords": formaldehyde_coords,
        "ispin": 1,
    },
    "CH3O": {
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 3),
        "coords": methoxy_coords,
        "ispin": 2,
        "magmom": "1*0.0 1*1.0 3*0.0",
        "nupdown": 1,
    },
    "CH4O": {
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 4),
        "coords": methanol_coords,
        "ispin": 1,
    },
}


def build(output: Path) -> None:
    build_species(output, SPECIES)


def main() -> None:
    run_builder(build)


if __name__ == "__main__":
    main()
