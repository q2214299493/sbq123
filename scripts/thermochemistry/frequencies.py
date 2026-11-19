"""Read VASP vibrational observations, leaving scientific acceptance to the owning review."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from scripts.artifact_io import sha256_file
from scripts.neb_agent.utils_structure import read_poscar
from scripts.ts_validation.analyze_vfa import frequency_header

SETTING = re.compile(r"\b(IBRION|NFREE|POTIM|ISYM|EDIFF|ENCUT|ISMEAR|SIGMA|NIONS)\s*=\s*([^\s;]+)")


def parse_outcar(outcar: Path, poscar: Path):
    structure = read_poscar(poscar)
    flags = structure.flags if structure.selective else [("T", "T", "T")] * structure.atom_count
    if any(len(row) != 3 or set(row) - {"T", "F"} for row in flags):
        raise ValueError("Invalid selective-dynamics flags")
    active = [i for i, row in enumerate(flags) if "T" in row]
    digest = hashlib.sha256()
    modes = []
    settings = {}
    with outcar.open("rb") as source:
        for raw in source:
            digest.update(raw)
            line = raw.decode("ascii", errors="replace")
            settings.update(SETTING.findall(line))
            if re.match(r"^\s*\d+\s+f(?:/i)?\s*=", line):
                mode = frequency_header(line)
                if mode is None:
                    raise ValueError("Unrecognized VASP frequency row")
                modes.append(mode)
    if not modes or [m["mode_index"] for m in modes] != list(range(1, 1 + len(modes))):
        raise ValueError("Missing, repeated or incomplete mode numbering; select one identified Hessian")
    if "NIONS" in settings and int(settings["NIONS"]) != structure.atom_count:
        raise ValueError("POSCAR and OUTCAR atom counts differ")
    expected = sum(row.count("T") for row in flags)
    return {"source_reference": str(outcar), "source_artifact_hash": digest.hexdigest(),
            "frequency_structure_sha256": sha256_file(poscar), "atom_map": active,
            "constraints": ["".join(row) for row in flags], "settings": settings,
            "mode_count": len(modes), "expected_cartesian_modes": expected,
            "cartesian_count_matches": len(modes) == expected,
            "frequencies_cm1": [-m["frequency_cm1"] if m["imaginary"] else m["frequency_cm1"] for m in modes],
            "imaginary_indices_one_based": [m["mode_index"] for m in modes if m["imaginary"]],
            "validation_status": "unreviewed"}


def draft_intake(observation, reaction_id, state, thermal_basis=None):
    """Convert an observation to an upload that can receive a later documented review."""
    value = {"structure_identity": observation["frequency_structure_sha256"], "atom_map": observation["atom_map"],
             "constraints": "Cartesian flags by atom: " + " ".join(observation["constraints"]),
             "method": "VASP " + " ".join(f"{k}={v}" for k, v in sorted(observation["settings"].items())),
             "expected_modes": observation["expected_cartesian_modes"], "thermal_basis": thermal_basis,
             "frequencies_cm1": observation["frequencies_cm1"]}
    provenance = {k: observation[k] for k in ("source_reference", "source_artifact_hash")}
    return {"schema_version": 1, "reaction_id": reaction_id, "records": [{
        "id": f"{state}-spectrum-{provenance['source_artifact_hash']}", "state": state, "kind": "spectrum",
        "mode": "USER_PROVIDED", "value": value, "provenance": provenance,
        "validation": {"validation_status": "unreviewed", "compatibility_status": "unknown",
                       "validated_properties": [], "limitations": []}, "acceptance": {"acceptance_status": "pending"},
    }]}
