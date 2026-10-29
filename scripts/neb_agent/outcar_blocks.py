"""Streaming POSITION/TOTAL-FORCE observations with one inseparable block binding."""
from __future__ import annotations

import math
from pathlib import Path
import re


def _triplet(fields):
    try:
        values = [float(value) for value in fields]
        return values if len(values) == 3 and all(math.isfinite(v) for v in values) else None
    except ValueError:
        return None


def _row(line):
    fields = line.split()
    if not fields:
        return None
    try:
        float(fields[0])
    except ValueError:
        if set(fields[0]) != {"*"}:
            return None
    return _triplet(fields[:3]), _triplet(fields[3:6])


def _finish(block, closed, reason):
    count = len(block["positions_A"])
    expected = block["expected_atoms"]
    count_complete = count > 0 and (count == expected if expected is not None else closed)
    block.update({"observed_rows": count, "closing_separator": closed, "termination": reason,
                  "coordinate_complete": count_complete and all(row is not None for row in block["positions_A"]),
                  "force_valid": count_complete and all(row is not None for row in block["forces_eV_per_A"])})
    block["complete"] = block["coordinate_complete"] and block["force_valid"]
    return block


def block_metadata(block):
    return {key: value for key, value in block.items() if key not in {"positions_A", "forces_eV_per_A"}}


def read_force_blocks(path: Path, expected_atoms: int | None = None) -> dict:
    """Retain the latest attempted block and last complete finite block separately.

    With no NIONS/caller count, a closing separator is required. A prior complete
    table supplies the count for subsequent tables. Neither selection nor a
    footer is a scientific acceptance decision. Source line numbers are 1-based.
    """
    if expected_atoms is not None and (type(expected_atoms) is not int or expected_atoms < 1):
        raise ValueError("positive expected atom count required")
    selected = latest = active = None
    count = nions = inferred = 0
    energy = energy_line = iteration = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            match = re.search(r"NIONS\s*=\s*(\d+)", line)
            if match:
                nions = int(match[1])
            step = re.search(r"Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)", line)
            if step:
                iteration = {"ionic_label": int(step[1]), "electronic_label": int(step[2])}
            if "free  energy   TOTEN" in line:
                value = _triplet([line.split()[4]] * 3) if len(line.split()) > 4 else None
                if value is not None:
                    energy, energy_line = value[0], number
            if "TOTAL-FORCE (eV/Angst)" in line:
                if active is not None:
                    latest = _finish(active, False, "next_header")
                    selected = latest if latest["complete"] else selected
                count += 1
                active = {"source_path": str(path), "block_index": count, "header_line": number,
                          "row_start_line": None, "row_end_line": None, "expected_atoms": expected_atoms or nions or inferred or None,
                          "count_basis": "caller" if expected_atoms else "NIONS" if nions else "prior_complete_table" if inferred else "closing_separator",
                          "iteration_at_header": iteration, "positions_A": [], "forces_eV_per_A": []}
                continue
            if active is None:
                continue
            row = _row(line)
            if row is not None:
                active["positions_A"].append(row[0])
                active["forces_eV_per_A"].append(row[1])
                active["row_start_line"] = active["row_start_line"] or number
                active["row_end_line"] = number
                continue
            separator = bool(line.strip()) and set(line.strip()) == {"-"}
            if not active["positions_A"] and (separator or not line.strip()):
                continue
            latest = _finish(active, separator, "separator" if separator else "non_row")
            if latest["complete"]:
                selected, inferred = latest, latest["observed_rows"]
            active = None
    if active is not None:
        latest = _finish(active, False, "EOF")
        selected = latest if latest["complete"] else selected
    return {"selected": selected, "latest_attempt": latest, "block_count": count,
            "selected_is_latest_attempt": bool(selected and latest and selected["block_index"] == latest["block_index"]),
            "latest_toten_eV": energy, "latest_toten_line": energy_line,
            "energy_scope": "latest finite TOTEN observation in file; not automatically bound to the selected force block"}
