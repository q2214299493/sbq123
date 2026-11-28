"""VASP vibrational observations and their structure and source bindings."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from sbq123.common.artifacts.artifact_io import sha256_file
from sbq123.common.workflow.neb_agent.utils_structure import read_poscar
from sbq123.common.validation.scientific_validation import finite_number, validate_finite_tree


FREQUENCY_PATTERN = re.compile(r"^\s*(\d+)\s+f(/i)?\s*=(?:.*\s)?([-+\d.]+(?:[eEdD][-+]?\d+)?)\s+cm-1", re.I)
SETTING = re.compile(r"\b(IBRION|NFREE|POTIM|ISYM|EDIFF|ENCUT|ISMEAR|SIGMA|NIONS)\s*=\s*([^\s;]+)")


def frequency_header(line: str) -> dict[str, Any] | None:
    if "cm-1" in line:
        validate_finite_tree(line.split(), "frequency row")
    match = FREQUENCY_PATTERN.match(line)
    if not match:
        return None
    value = match.group(3).upper().replace("D", "E")
    return {"mode_index": int(match.group(1)), "imaginary": bool(match.group(2)),
            "frequency_cm1": finite_number(value, "frequency cm-1")}


def parse_frequency_outcar(outcar: Path, poscar: Path):
    """Read a spectrum with one-based mode numbers and a zero-based active atom map."""
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
