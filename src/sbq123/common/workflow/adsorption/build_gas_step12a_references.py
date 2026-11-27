#!/usr/bin/env python3
"""Build missing gas-phase VASP references for Fe(110) Step 12A adsorption energies."""

from __future__ import annotations

from pathlib import Path

from .gas_vasp_common import CENTER, add, build_species, run_builder


SPECIES = {
    "CO": {
        "label": "closed-shell carbon monoxide",
        "elements": ("C", "O"),
        "counts": (1, 1),
        "coords": (CENTER, add(CENTER, (0.0, 0.0, 1.13))),
        "ispin": 1,
        "potcar": "C_O",
    },
    "H": {
        "label": "atomic hydrogen doublet",
        "elements": ("H",),
        "counts": (1,),
        "coords": (CENTER,),
        "ispin": 2,
        "magmom": "1*1.0",
        "nupdown": 1,
        "potcar": "H",
    },
    "O": {
        "label": "atomic oxygen triplet",
        "elements": ("O",),
        "counts": (1,),
        "coords": (CENTER,),
        "ispin": 2,
        "magmom": "1*2.0",
        "nupdown": 2,
        "potcar": "O",
    },
    "OH": {
        "label": "hydroxyl radical doublet",
        "elements": ("O", "H"),
        "counts": (1, 1),
        "coords": (CENTER, add(CENTER, (0.0, 0.0, 0.97))),
        "ispin": 2,
        "magmom": "1*1.0 1*0.0",
        "nupdown": 1,
        "potcar": "O_H",
    },
    "C": {
        "label": "atomic carbon triplet",
        "elements": ("C",),
        "counts": (1,),
        "coords": (CENTER,),
        "ispin": 2,
        "magmom": "1*2.0",
        "nupdown": 2,
        "potcar": "C",
    },
}


def build(output: Path) -> None:
    build_species(output, SPECIES)


def main() -> None:
    run_builder(build)


if __name__ == "__main__":
    main()
