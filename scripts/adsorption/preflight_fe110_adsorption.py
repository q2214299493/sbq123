from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml
from pymatgen.io.vasp.inputs import Incar, Kpoints

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.artifact_io import sha256_file
from scripts.vasp_lsf import render_sunboquan_lsf


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "configs" / "true_fe110_production.yaml"


def _equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return bool(actual) is expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(actual) - float(expected)) <= 1e-10
        except (TypeError, ValueError):
            return False
    return str(actual).lower() == str(expected).lower()


def preflight(workdir: Path, *, profile_path: Path = DEFAULT_PROFILE, cores: int = 32) -> dict[str, Any]:
    required = ["POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "candidate_manifest.json"]
    errors: list[str] = []
    warnings: list[str] = []
    for name in required:
        path = workdir / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"MISSING_OR_EMPTY:{name}")
    if errors:
        return {"kind": "adsorption_relaxation", "passed": False, "errors": errors, "warnings": warnings}

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    stage = profile["routine_production"]
    structure = read_poscar(workdir / "POSCAR")
    allowed_compositions = {
        (("Fe", "C", "H"), (45, 1, 1)),
        (("Fe", "C", "H"), (45, 1, 2)),
        (("Fe", "C", "O", "H"), (45, 2, 1, 2)),
    }
    composition = (tuple(structure.symbols), tuple(structure.counts))
    if composition not in allowed_compositions:
        errors.append("POSCAR_COMPOSITION_OR_ORDER_MISMATCH")
    if any(flag != ("F", "F", "F") for flag in structure.flags[:18]):
        errors.append("BOTTOM_18_FE_NOT_FIXED")
    if any(flag != ("T", "T", "T") for flag in structure.flags[18:]):
        errors.append("UNEXPECTED_CONSTRAINT_ABOVE_BOTTOM_18_FE")

    incar = Incar.from_file(workdir / "INCAR")
    expected_incar = {
        **stage["incar"],
        "GGA": profile["scope"]["incar_gga"],
        "ENCUT": profile["scope"]["encut_eV"],
    }
    for key, expected in expected_incar.items():
        if key not in incar or not _equal(incar[key], expected):
            errors.append(f"INCAR_MISMATCH:{key}")
    magmom = incar.get("MAGMOM", [])
    if len(magmom) != sum(structure.counts) or any(abs(float(value) - 2.2) > 1e-10 for value in magmom[:45]) or any(
        abs(float(value)) > 1e-10 for value in magmom[45:]
    ):
        errors.append("MAGMOM_SPECIES_SEGMENTS_MISMATCH")

    kpoints = Kpoints.from_file(workdir / "KPOINTS")
    mesh = list(kpoints.kpts[0]) if kpoints.kpts else []
    if mesh != list(stage["gamma_mesh"]) or str(kpoints.style).lower().split(".")[-1] != "gamma":
        errors.append("KPOINTS_GAMMA_MESH_MISMATCH")
    expected_spec = " ".join(dict.fromkeys(structure.symbols))
    if (workdir / "POTCAR.spec").read_text(encoding="ascii").strip() != expected_spec:
        errors.append("POTCAR_SPECIES_ORDER_MISMATCH")
    if (workdir / "script.lsf").read_text(encoding="ascii") != render_sunboquan_lsf(cores):
        errors.append("LSF_SCRIPT_NOT_CANONICAL")
    else:
        match = re.search(r"^NP=(\d+)$", (workdir / "script.lsf").read_text(encoding="ascii"), re.MULTILINE)
        if match is None or int(match.group(1)) != cores:
            errors.append("LSF_CORE_COUNT_MISMATCH")

    files = {name: sha256_file(workdir / name) for name in required}
    result = {
        "kind": "adsorption_relaxation",
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "profile_path": str(profile_path),
        "profile_sha256": sha256_file(profile_path),
        "files": files,
        "structure": {
            "symbols": structure.symbols,
            "counts": structure.counts,
            "fixed_zero_based": [index for index, flags in enumerate(structure.flags) if flags == ("F", "F", "F")],
        },
        "incar_stage": "routine_production",
        "gamma_mesh": mesh,
        "cores": cores,
        "potcar_local_policy": "POTCAR contents remain remote; verify exact species order and SHA-256 before submission",
    }
    (workdir / "adsorption_submission_preflight.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight one active-branch Fe(110) adsorption relaxation package.")
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--cores", type=int, default=32)
    args = parser.parse_args()
    result = preflight(args.workdir, profile_path=args.profile, cores=args.cores)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
