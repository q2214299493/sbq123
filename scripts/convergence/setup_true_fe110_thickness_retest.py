#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
from ase.build import bcc110, bulk
from ase.constraints import FixAtoms
from ase.io import read, write


LATTICE_A = 2.8665
LAYERS = (4, 5, 6, 7, 8)
VACUUM_A = 15.0
RELAX_MESH = (5, 5, 1)
STATIC_MESH = (7, 7, 1)
EV_A2_TO_J_M2 = 16.02176634


def incar_relax(natoms: int) -> str:
    return f"""SYSTEM = true_bcc_Fe110_3x3_relax
PREC = Accurate
ENCUT = 400
EDIFF = 1E-6
EDIFFG = -0.02
NELMIN = 5
NSW = 300
IBRION = 2
POTIM = 0.20
ISIF = 2
GGA = PE
ISPIN = 2
MAGMOM = {natoms}*2.2
ISMEAR = 1
SIGMA = 0.20
ALGO = Fast
LREAL = .FALSE.
LASPH = .TRUE.
NPAR = 2
LCHARG = .FALSE.
LWAVE = .FALSE.
"""


def incar_static(natoms: int) -> str:
    return f"""SYSTEM = true_bcc_Fe110_3x3_static
PREC = Accurate
ENCUT = 400
EDIFF = 1E-6
NELMIN = 5
NSW = 0
IBRION = -1
ISIF = 2
GGA = PE
ISPIN = 2
MAGMOM = {natoms}*2.2
ISMEAR = 1
SIGMA = 0.10
ALGO = Fast
LREAL = .FALSE.
LASPH = .TRUE.
NPAR = 2
LCHARG = .FALSE.
LWAVE = .FALSE.
"""


def write_kpoints(path: Path, mesh: tuple[int, int, int]) -> None:
    path.write_text(f"Gamma mesh\n0\nGamma\n{mesh[0]} {mesh[1]} {mesh[2]}\n0 0 0\n", encoding="ascii")


def layer_indices(atoms) -> list[list[int]]:
    order = np.argsort(atoms.positions[:, 2])
    groups: list[list[int]] = []
    for index in order:
        if not groups or abs(atoms.positions[index, 2] - atoms.positions[groups[-1][0], 2]) > 1e-5:
            groups.append([int(index)])
        else:
            groups[-1].append(int(index))
    return groups


def build_slab(nlayers: int):
    atoms = bcc110(
        "Fe",
        size=(3, 3, nlayers),
        a=LATTICE_A,
        vacuum=VACUUM_A / 2.0,
        orthogonal=False,
        periodic=True,
    )
    groups = layer_indices(atoms)
    fixed = [index for group in groups[:2] for index in group]
    atoms.set_constraint(FixAtoms(indices=fixed))
    return atoms


def chain_lsf() -> str:
    return """#!/bin/sh
APP_NAME=Gkn_normal
NP=32
NP_PER_NODE=32
RUN="RAW"
ROOT=$PWD

export OMP_NUM_THREADS=1
source /home_gkx/env/intel/intel2016.sh
VASP=$HOME/soft/vasp.5.4.1/bin/vasp_std

rm -f "$ROOT/nodelist"
for host in $LSB_HOSTS
do
    echo "$host" >> "$ROOT/nodelist"
done

cd "$ROOT/relax" || exit 10
mpirun -np $NP -machinefile "$ROOT/nodelist" $VASP > vasp.out 2>&1
if ! grep -q "reached required accuracy" OUTCAR
then
    echo "Relaxation did not reach required accuracy; static stage skipped." >> vasp.out
    exit 20
fi

cp CONTCAR "$ROOT/static/POSCAR"
cd "$ROOT/static" || exit 30
mpirun -np $NP -machinefile "$ROOT/nodelist" $VASP > vasp.out 2>&1
if ! grep -q "General timing and accounting informations for this job" OUTCAR
then
    exit 40
fi
"""


def static_lsf() -> str:
    return """#!/bin/sh
APP_NAME=Gkn_normal
NP=32
NP_PER_NODE=32
RUN="RAW"
ROOT=$PWD

export OMP_NUM_THREADS=1
source /home_gkx/env/intel/intel2016.sh
VASP=$HOME/soft/vasp.5.4.1/bin/vasp_std

rm -f "$ROOT/nodelist"
for host in $LSB_HOSTS
do
    echo "$host" >> "$ROOT/nodelist"
done
mpirun -np $NP -machinefile "$ROOT/nodelist" $VASP > vasp.out 2>&1
"""


def setup(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for nlayers in LAYERS:
        atoms = build_slab(nlayers)
        job = output / f"layers_{nlayers}"
        relax = job / "relax"
        static = job / "static"
        relax.mkdir(parents=True, exist_ok=True)
        static.mkdir(parents=True, exist_ok=True)
        write(relax / "POSCAR", atoms, format="vasp", direct=True, vasp5=True, sort=False)
        write(static / "POSCAR", atoms, format="vasp", direct=True, vasp5=True, sort=False)
        (relax / "INCAR").write_text(incar_relax(len(atoms)), encoding="ascii")
        (static / "INCAR").write_text(incar_static(len(atoms)), encoding="ascii")
        write_kpoints(relax / "KPOINTS", RELAX_MESH)
        write_kpoints(static / "KPOINTS", STATIC_MESH)
        (job / "run_chain.lsf").write_text(chain_lsf(), encoding="ascii", newline="\n")

    bulk_job = output / "bulk_reference"
    bulk_job.mkdir(parents=True, exist_ok=True)
    bulk_atoms = bulk("Fe", "bcc", a=LATTICE_A, cubic=True)
    write(bulk_job / "POSCAR", bulk_atoms, format="vasp", direct=True, vasp5=True, sort=False)
    (bulk_job / "INCAR").write_text(incar_static(len(bulk_atoms)), encoding="ascii")
    write_kpoints(bulk_job / "KPOINTS", (21, 21, 21))
    (bulk_job / "run.lsf").write_text(static_lsf(), encoding="ascii", newline="\n")

    metadata = {
        "system": "true bcc alpha-Fe(110), clean 3x3 primitive surface cell",
        "lattice_parameter_A": LATTICE_A,
        "layers": list(LAYERS),
        "vacuum_A": VACUUM_A,
        "fixed_bottom_layers": 2,
        "relax_mesh": list(RELAX_MESH),
        "static_mesh": list(STATIC_MESH),
        "encut_eV": 400,
        "purpose": "Replace the invalid static thickness series and verify true Fe(110) slab-thickness convergence.",
        "comparison": "relaxed geometry, static surface excess energy, and interlayer relaxation",
    }
    (output / "campaign.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    validate(output)


def validate(output: Path) -> None:
    expected_spacing = LATTICE_A / math.sqrt(2.0)
    for nlayers in LAYERS:
        atoms = read(output / f"layers_{nlayers}" / "relax" / "POSCAR")
        groups = layer_indices(atoms)
        if len(atoms) != 9 * nlayers or len(groups) != nlayers or any(len(group) != 9 for group in groups):
            raise ValueError(f"layers_{nlayers}: expected {nlayers} groups of 9 Fe atoms")
        spacing = np.diff([atoms.positions[group, 2].mean() for group in groups])
        if not np.allclose(spacing, expected_spacing, atol=1e-5):
            raise ValueError(f"layers_{nlayers}: spacing is not bcc Fe(110)")
        fixed_indices = {
            int(index) for constraint in atoms.constraints if hasattr(constraint, "get_indices") for index in constraint.get_indices()
        }
        fixed = len(fixed_indices)
        if fixed != 18:
            raise ValueError(f"layers_{nlayers}: expected 18 fixed atoms, found {fixed}")
    print(f"Validated true Fe(110) input campaign: {output}")


def last_toten(path: Path) -> float | None:
    if not path.exists():
        return None
    values = re.findall(r"free\\s+energy\\s+TOTEN\\s+=\\s+([-+0-9.Ee]+)", path.read_text(errors="ignore"))
    return float(values[-1]) if values else None


def summarize(output: Path) -> None:
    bulk_energy = last_toten(output / "bulk_reference" / "OUTCAR")
    if bulk_energy is None:
        raise RuntimeError("bulk_reference/OUTCAR has no TOTEN")
    bulk_per_atom = bulk_energy / 2.0
    rows = []
    for nlayers in LAYERS:
        outcar = output / f"layers_{nlayers}" / "static" / "OUTCAR"
        energy = last_toten(outcar)
        atoms = read(output / f"layers_{nlayers}" / "static" / "POSCAR")
        area = float(np.linalg.norm(np.cross(atoms.cell[0], atoms.cell[1])))
        gamma = None if energy is None else (energy - len(atoms) * bulk_per_atom) / (2.0 * area) * EV_A2_TO_J_M2
        rows.append({"layers": nlayers, "natoms": len(atoms), "static_toten_eV": energy, "surface_excess_J_m2": gamma})
    (output / "thickness_summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(output / "thickness_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.setup:
        setup(args.output)
    if args.validate:
        validate(args.output)
    if args.summary:
        summarize(args.output)


if __name__ == "__main__":
    main()
