from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.adsorption.build_gas_step12a_references import SPECIES
from scripts.adsorption.gas_vasp_common import CELL


REQUIRED_FILES = ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "job.sh")
COMMON_INCAR = {
    "PREC": "Accurate",
    "ENCUT": "400",
    "EDIFF": "1E-5",
    "EDIFFG": "-0.02",
    "IBRION": "2",
    "ISIF": "2",
    "GGA": "PE",
    "ISMEAR": "0",
    "SIGMA": "0.05",
    "LREAL": ".FALSE.",
    "LASPH": ".TRUE.",
    "ISYM": "0",
    "LDIPOL": ".TRUE.",
    "IDIPOL": "4",
}


def _incar_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="ascii").splitlines():
        line = raw.split("!", 1)[0].split("#", 1)[0]
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()
    return values


def _poscar_contract(path: Path) -> tuple[list[str], list[int], list[list[float]]]:
    lines = [line.strip() for line in path.read_text(encoding="ascii").splitlines()]
    if len(lines) < 9:
        raise ValueError("POSCAR is incomplete")
    scale = float(lines[1])
    cell = [[scale * float(value) for value in lines[index].split()[:3]] for index in (2, 3, 4)]
    return lines[5].split(), [int(value) for value in lines[6].split()], cell


def check_species(root: Path, species: str) -> dict[str, Any]:  # noqa: C901
    if species not in SPECIES:
        raise ValueError(f"unsupported Step 12A gas reference: {species}")
    model = SPECIES[species]
    folder = root / species / "relax"
    failures: list[str] = []
    for filename in REQUIRED_FILES:
        if not (folder / filename).is_file():
            failures.append(f"missing {filename}")
    if (folder / "POTCAR").exists():
        failures.append("licensed POTCAR must not be stored in the local repository")
    if failures:
        return {"species": species, "folder": str(folder), "passed": False, "failures": failures}

    elements, counts, cell = _poscar_contract(folder / "POSCAR")
    if elements != list(model["elements"]):
        failures.append(f"POSCAR elements {elements} != {list(model['elements'])}")
    if counts != list(model["counts"]):
        failures.append(f"POSCAR counts {counts} != {list(model['counts'])}")
    expected_cell = [[CELL, 0.0, 0.0], [0.0, CELL, 0.0], [0.0, 0.0, CELL]]
    if cell != expected_cell:
        failures.append("POSCAR cell is not the locked 20 A cubic gas box")

    incar = _incar_values(folder / "INCAR")
    for key, expected in COMMON_INCAR.items():
        if incar.get(key) != expected:
            failures.append(f"INCAR {key}={incar.get(key)!r}, expected {expected!r}")
    expected_ispin = str(model["ispin"])
    if incar.get("ISPIN") != expected_ispin:
        failures.append(f"INCAR ISPIN={incar.get('ISPIN')!r}, expected {expected_ispin!r}")
    if model["ispin"] == 1:
        if "MAGMOM" in incar or "NUPDOWN" in incar:
            failures.append("closed-shell reference must omit MAGMOM and NUPDOWN")
    else:
        for key in ("MAGMOM", "NUPDOWN"):
            expected = str(model[key.lower()])
            if incar.get(key) != expected:
                failures.append(f"INCAR {key}={incar.get(key)!r}, expected {expected!r}")

    kpoints = [line.strip() for line in (folder / "KPOINTS").read_text(encoding="ascii").splitlines()]
    if len(kpoints) < 5 or kpoints[2].lower() != "gamma" or kpoints[3].split()[:3] != ["1", "1", "1"]:
        failures.append("KPOINTS is not Gamma-only 1x1x1")
    potcar_spec = (folder / "POTCAR.spec").read_text(encoding="ascii").strip()
    if potcar_spec != model["potcar"]:
        failures.append(f"POTCAR.spec={potcar_spec!r}, expected {model['potcar']!r}")
    job = (folder / "job.sh").read_text(encoding="ascii")
    for marker in ("vasp_std", "POTCAR.link", "mpirun"):
        if marker not in job:
            failures.append(f"job.sh is missing {marker}")
    return {"species": species, "folder": str(folder), "passed": not failures, "failures": failures}


def audit(root: Path, species: tuple[str, ...] | None = None) -> dict[str, Any]:
    selected = species or tuple(SPECIES)
    records = [check_species(root, name) for name in selected]
    return {
        "schema_version": 1,
        "document_kind": "step12a_gas_reference_preflight",
        "root": str(root.resolve()),
        "passed": all(record["passed"] for record in records),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight Step 12A gas-reference VASP inputs.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--species", choices=tuple(SPECIES), action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.root, tuple(args.species) if args.species else None)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
