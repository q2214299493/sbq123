#!/usr/bin/env python3
"""Build reviewable gas-phase VASP relaxations for H2 and CHx references."""

from __future__ import annotations

import math
from pathlib import Path

from .gas_vasp_common import CENTER, add, build_species, run_builder

SPECIES = {
    "H2": {
        "elements": ("H",),
        "counts": (2,),
        "coords": ((9.63, 10.0, 10.0), (10.37, 10.0, 10.0)),
        "ispin": 1,
        "potcar": "H",
    },
    "CH": {
        "elements": ("C", "H"),
        "counts": (1, 1),
        "coords": (CENTER, (10.0, 10.0, 11.11)),
        "ispin": 2,
        "magmom": "1*1.0 1*0.0",
        "nupdown": 1,
        "potcar": "C_H",
    },
    "CH2": {
        "elements": ("C", "H"),
        "counts": (1, 2),
        "coords": None,
        "ispin": 2,
        "magmom": "1*2.0 2*0.0",
        "nupdown": 2,
        "potcar": "C_H",
    },
    "CH3": {
        "elements": ("C", "H"),
        "counts": (1, 3),
        "coords": None,
        "ispin": 2,
        "magmom": "1*1.0 3*0.0",
        "nupdown": 1,
        "potcar": "C_H",
    },
    "CH4": {
        "elements": ("C", "H"),
        "counts": (1, 4),
        "coords": None,
        "ispin": 1,
        "potcar": "C_H",
    },
}


def geometries() -> None:
    bond = 1.09
    half_angle = math.radians(134.0 / 2.0)
    SPECIES["CH2"]["coords"] = (
        CENTER,
        add(CENTER, (bond * math.sin(half_angle), 0.0, bond * math.cos(half_angle))),
        add(CENTER, (-bond * math.sin(half_angle), 0.0, bond * math.cos(half_angle))),
    )
    SPECIES["CH3"]["coords"] = (
        CENTER,
        *(
            add(
                CENTER,
                (
                    bond * math.cos(math.radians(angle)),
                    bond * math.sin(math.radians(angle)),
                    0.0,
                ),
            )
            for angle in (0.0, 120.0, 240.0)
        ),
    )
    tetrahedral = (
        (1.0, 1.0, 1.0),
        (1.0, -1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
    )
    scale = bond / math.sqrt(3.0)
    SPECIES["CH4"]["coords"] = (
        CENTER,
        *(add(CENTER, tuple(scale * value for value in vector)) for vector in tetrahedral),
    )


def build(output: Path) -> None:
    geometries()
    build_species(output, SPECIES)


def main() -> None:
    run_builder(build)


if __name__ == "__main__":
    main()
