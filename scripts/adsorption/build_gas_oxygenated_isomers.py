#!/usr/bin/env python3
"""Build gas-phase VASP relaxations for oxygenated C1 isomers."""

from __future__ import annotations

import math
from pathlib import Path

from .gas_vasp_common import CENTER, add, build_species, run_builder


def coh_coords() -> tuple[tuple[float, float, float], ...]:
    co = 1.25
    oh = 0.97
    coh = math.radians(110.0)
    oxygen = add(CENTER, (0.0, 0.0, co))
    hydrogen = add(oxygen, (oh * math.sin(coh), 0.0, -oh * math.cos(coh)))
    return (CENTER, oxygen, hydrogen)


def choh_coords() -> tuple[tuple[float, float, float], ...]:
    co = 1.35
    ch = 1.10
    oh = 0.97
    hco = math.radians(120.0)
    coh = math.radians(110.0)
    oxygen = add(CENTER, (0.0, 0.0, co))
    carbon_h = add(CENTER, (ch * math.sin(hco), 0.0, ch * math.cos(hco)))
    hydroxyl_h = add(oxygen, (oh * math.sin(coh), 0.0, -oh * math.cos(coh)))
    return (CENTER, oxygen, carbon_h, hydroxyl_h)


def ch2oh_coords() -> tuple[tuple[float, float, float], ...]:
    co = 1.43
    ch = 1.10
    oh = 0.97
    oxygen = add(CENTER, (0.0, 0.0, co))
    h1 = add(CENTER, (ch * math.sin(math.radians(109.0)), 0.0, -ch * math.cos(math.radians(109.0))))
    h2 = add(
        CENTER,
        (
            -ch * math.sin(math.radians(109.0)) * 0.5,
            ch * math.sin(math.radians(109.0)) * math.sqrt(3.0) / 2.0,
            -ch * math.cos(math.radians(109.0)),
        ),
    )
    hydroxyl_h = add(oxygen, (oh * math.sin(math.radians(108.5)), 0.0, oh * math.cos(math.radians(108.5))))
    return (CENTER, oxygen, h1, h2, hydroxyl_h)


SPECIES = {
    "COH": {
        "label": "hydroxymethylidyne / COH radical",
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 1),
        "coords": coh_coords,
        "ispin": 2,
        "magmom": "1*1.0 1*0.0 1*0.0",
        "nupdown": 1,
    },
    "CHOH": {
        "label": "hydroxymethylene / HCOH",
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 2),
        "coords": choh_coords,
        "ispin": 1,
    },
    "CH2OH": {
        "label": "hydroxymethyl / CH2OH radical",
        "elements": ("C", "O", "H"),
        "counts": (1, 1, 3),
        "coords": ch2oh_coords,
        "ispin": 2,
        "magmom": "1*1.0 1*0.0 3*0.0",
        "nupdown": 1,
    },
}


def build(output: Path) -> None:
    build_species(output, SPECIES)


def main() -> None:
    run_builder(build)


if __name__ == "__main__":
    main()
