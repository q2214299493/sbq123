"""Shared gas-phase VASP input rendering for adsorption reference builders."""

from __future__ import annotations

import argparse
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any


CELL = 20.0
CENTER = (10.0, 10.0, 10.0)

KPOINTS = "Gas molecule Gamma-only\n0\nGamma\n1 1 1\n0 0 0\n"

JOB_SCRIPT = """#!/bin/sh
APP_NAME=Gkn_normal
NP=32
NP_PER_NODE=32
RUN="RAW"
CURDIR=$PWD
export OMP_NUM_THREADS=1
source /home_gkx/env/intel/intel2016.sh
VASP=$HOME/soft/vasp.5.4.1/bin/vasp_std
cd "$CURDIR" || exit 10
TARGET=$(readlink -f POTCAR.link)
test -s "$TARGET" || exit 11
ln -sfn "$TARGET" POTCAR
rm -f nodelist
for host in $LSB_HOSTS; do echo "$host" >> nodelist; done
mpirun -np $NP -machinefile nodelist $VASP > vasp.out 2>&1
"""


def add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(x + y for x, y in zip(a, b, strict=True))


def carbonyl_with_hydrogens(co_bond: float, ch_bond: float, hydrogen_count: int) -> tuple[tuple[float, float, float], ...]:
    if hydrogen_count not in (1, 2):
        raise ValueError("carbonyl hydrogen_count must be one or two")
    angle = math.radians(120.0)
    hydrogens = tuple(
        add(CENTER, (sign * ch_bond * math.sin(angle), 0.0, ch_bond * math.cos(angle))) for sign in (1.0, -1.0)[:hydrogen_count]
    )
    return (CENTER, add(CENTER, (0.0, 0.0, co_bond)), *hydrogens)


def tetrahedral_methyl_hydrogens(ch_bond: float) -> tuple[tuple[float, float, float], ...]:
    radius = ch_bond * math.sqrt(8.0 / 9.0)
    z = ch_bond / 3.0
    return tuple(
        add(CENTER, (radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)), z)) for angle in (0.0, 120.0, 240.0)
    )


def render_incar(name: str, model: dict[str, Any]) -> str:
    lines = [
        f"SYSTEM = {name}_gas_PBE_relax",
        "PREC = Accurate",
        "ENCUT = 400",
        "EDIFF = 1E-5",
        "EDIFFG = -0.02",
        "NELM = 200",
        "NELMIN = 4",
        "NSW = 100",
        "IBRION = 2",
        "POTIM = 0.20",
        "ISIF = 2",
        "GGA = PE",
        f"ISPIN = {model['ispin']}",
    ]
    if model["ispin"] == 2:
        lines.extend([f"MAGMOM = {model['magmom']}", f"NUPDOWN = {model['nupdown']}"])
    lines.extend(
        [
            "ISMEAR = 0",
            "SIGMA = 0.05",
            "ALGO = Fast",
            "LREAL = .FALSE.",
            "LASPH = .TRUE.",
            "ISYM = 0",
            "LDIPOL = .TRUE.",
            "IDIPOL = 4",
            "DIPOL = 0.5 0.5 0.5",
            "LCHARG = .FALSE.",
            "LWAVE = .FALSE.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_poscar(name: str, model: dict[str, Any]) -> str:
    label = f"; {model['label']}" if model.get("label") else ""
    lines = [
        f"{name} gas initial geometry{label}",
        "1.0",
        f"{CELL:.8f} 0.0 0.0",
        f"0.0 {CELL:.8f} 0.0",
        f"0.0 0.0 {CELL:.8f}",
        " ".join(model["elements"]),
        " ".join(str(value) for value in model["counts"]),
        "Cartesian",
    ]
    coordinates = model["coords"]() if isinstance(model["coords"], Callable) else model["coords"]
    lines.extend(" ".join(f"{value:.10f}" for value in xyz) for xyz in coordinates)
    return "\n".join(lines) + "\n"


def build_species(output: Path, species: dict[str, dict[str, Any]]) -> None:
    for name, model in species.items():
        folder = output / name / "relax"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "POSCAR").write_text(render_poscar(name, model), encoding="ascii")
        (folder / "INCAR").write_text(render_incar(name, model), encoding="ascii")
        (folder / "KPOINTS").write_text(KPOINTS, encoding="ascii")
        (folder / "job.sh").write_text(JOB_SCRIPT, encoding="ascii", newline="\n")
        potcar = str(model.get("potcar", "_".join(model["elements"])))
        (folder / "POTCAR.spec").write_text(f"{potcar}\n", encoding="ascii")


def run_builder(build: Callable[[Path], None]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
