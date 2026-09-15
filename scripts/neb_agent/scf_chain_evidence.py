"""Read-only evidence for the fixed-geometry, collinear three-stage SCF check.

Reuses the canonical electronic parser; no permission or retry decisions here.
The deliberately narrow POSCAR reader supports the reviewed positive-scale
VASP5 inputs, not arbitrary structure conversion.
"""
from __future__ import annotations

import itertools
import math
import re
import struct
from pathlib import Path

from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar, FATAL_PATTERN
from scripts.scientific_validation import finite_number
from scripts.vasp_result_gate import final_scf_state, read_incar_values


def numbers(text: str) -> list[float]:
    return [finite_number(x.replace("D", "E").replace("d", "e"), "VASP value")
            for x in text.split()]


def structure(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        handle.readline()
        scale = numbers(handle.readline())
        if len(scale) != 1 or scale[0] <= 0:
            raise ValueError("SCF chain supports one positive POSCAR scale only")
        cell = [[x * scale[0] for x in numbers(handle.readline())] for _ in range(3)]
        symbols = handle.readline().split()
        counts = [int(x) for x in handle.readline().split()]
        if len(symbols) != len(counts) or not counts or min(counts) <= 0 or any(len(x) != 3 for x in cell):
            raise ValueError("invalid VASP5 POSCAR header")
        mode = handle.readline().strip().lower()
        selective = mode.startswith("s")
        if selective:
            mode = handle.readline().strip().lower()
        if not mode.startswith(("d", "c", "k")):
            raise ValueError("unknown POSCAR coordinate mode")
        coordinates, flags = [], []
        for _ in range(sum(counts)):
            row = handle.readline().split()
            xyz = numbers(" ".join(row[:3]))
            if len(xyz) != 3:
                raise ValueError("incomplete POSCAR coordinates")
            flag = [x.upper() for x in row[3:6]] if selective else ["T", "T", "T"]
            if len(flag) != 3 or any(x not in {"T", "F"} for x in flag):
                raise ValueError("invalid selective dynamics")
            flags.append(flag)
            coordinates.append([sum(xyz[k] * cell[k][j] for k in range(3)) for j in range(3)]
                               if mode.startswith("d") else [x * scale[0] for x in xyz])
    return {"cell": cell, "symbols": symbols, "counts": counts,
            "positions": coordinates, "flags": flags, "header_lines": 8 + int(selective) + sum(counts)}


def geometry_error(reference: dict, actual: dict, tolerance: float) -> float:
    if (len(actual["positions"]) != sum(reference["counts"])
            or len(reference["positions"]) != sum(reference["counts"])):
        raise ValueError("incomplete geometry")
    if any(reference[key] != actual[key] for key in ("symbols", "counts", "flags")):
        raise ValueError("atom order or fixed layers changed")
    cell = reference["cell"]
    if max(abs(a - b) for v, w in zip(cell, actual["cell"]) for a, b in zip(v, w)) > tolerance:
        raise ValueError("cell changed")
    a, b, c = cell
    def cross(v, w):
        return [v[1]*w[2]-v[2]*w[1], v[2]*w[0]-v[0]*w[2], v[0]*w[1]-v[1]*w[0]]
    reciprocal = [cross(b, c), cross(c, a), cross(a, b)]
    det = sum(x*y for x, y in zip(a, reciprocal[0]))
    if abs(det) < 1e-12:
        raise ValueError("singular cell")
    maximum = 0.0
    for v, w in zip(reference["positions"], actual["positions"]):
        delta = [x-y for x, y in zip(w, v)]
        fractional = [sum(x*y for x, y in zip(delta, r))/det for r in reciprocal]
        center = [round(x) for x in fractional]
        distance = min(math.sqrt(sum(
            (delta[j] - sum((center[k]+offset[k])*cell[k][j] for k in range(3)))**2
            for j in range(3))) for offset in itertools.product((-1, 0, 1), repeat=3))
        maximum = max(maximum, distance)
    if maximum > tolerance:
        raise ValueError(f"fixed-geometry drift: {maximum:.8g} A")
    return maximum


def restart_files(directory: Path, expected: dict, reference: dict, tolerance: float) -> None:
    """Structural integrity only; actual restart use must also be proven in C."""
    wave = directory / "WAVECAR"
    with wave.open("rb") as handle:
        header = handle.read(24)
        if len(header) != 24:
            raise ValueError("truncated WAVECAR header")
        record, spin, tag = struct.unpack("<3d", header)
        if record != int(record) or record < 96 or spin != 2 or tag not in (45200, 45210):
            raise ValueError("unsupported/invalid WAVECAR header")
        handle.seek(int(record))
        header = handle.read(96)
        if len(header) != 96:
            raise ValueError("truncated WAVECAR metadata")
        kpoints, bands, encut, *lattice = struct.unpack("<12d", header)
    if (kpoints < 1 or kpoints != int(kpoints) or bands != expected["NBANDS"]
            or abs(encut - expected["ENCUT"]) > 1e-8
            or any(not math.isfinite(x) for x in lattice)
            or max(abs(x-y) for x, y in zip(lattice, sum(reference["cell"], []))) > tolerance
            or wave.stat().st_size < record * (2 + spin*kpoints*(bands+1))):
        raise ValueError("truncated/incompatible WAVECAR")
    charge = directory / "CHGCAR"
    charge_geometry = structure(charge)
    # CHGCAR does not preserve Selective Dynamics; its geometry is checked,
    # while fixed-layer flags remain bound to the immutable POSCAR/CONTCAR.
    charge_geometry["flags"] = reference["flags"]
    geometry_error(reference, charge_geometry, tolerance)
    # Two complete grids are required for this collinear ISPIN=2 branch.
    grids, remaining, dimensions = 0, 0, None
    with charge.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if line_number < charge_geometry["header_lines"]:
                continue
            if remaining:
                values = numbers(line)
                if not values or len(values) > remaining:
                    raise ValueError("malformed CHGCAR grid")
                remaining -= len(values)
                continue
            if re.fullmatch(r"\s*\d+\s+\d+\s+\d+\s*", line):
                dims = tuple(int(x) for x in line.split())
                if min(dims) <= 0 or (dimensions is not None and dims != dimensions):
                    raise ValueError("inconsistent CHGCAR grids")
                dimensions = dims
                remaining = math.prod(dims)
                grids += 1
    if grids != 2 or remaining:
        raise ValueError("missing/truncated spin CHGCAR grids")


def _scan_logs(directory: Path, expected: dict, atom_count: int) -> dict:
    errors = set()
    actual, energy, forces, positions = {}, None, [], []
    read_wave = read_charge = False
    force_rows = None
    # Streaming, capped memory; do not load multi-GB VASP logs.
    for name in ("OUTCAR", "vasp.out"):
        with (directory / name).open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if FATAL_PATTERN.search(line) or re.search(r"not hermitian|non.hermitian|\b(?:nan|inf)\b", line, re.I):
                    errors.add("NUMERICAL_OR_RUNTIME_ERROR")
                read_wave |= bool(re.search(r"WAVECAR.*(?:successfully read|read successfully)|WAVECAR file was read successfully", line, re.I))
                read_charge |= bool(re.search(r"charge.density read from file.*CHGCAR", line, re.I))
                if name != "OUTCAR":
                    continue
                distribution = re.search(r"distr:\s+one band on\s+(?:NCORES_PER_BAND=\s*)?(\d+)\s+cores", line)
                if distribution and "NCORE" in expected:
                    actual["NCORE"] = int(distribution[1])
                for key in expected:
                    # The startup banner's 'NCORE=4' is advice, not the actual
                    # band distribution. Only the 'distr:' line establishes it.
                    match = re.search(r"\b" + key + r"\s*=\s*([-+0-9.Ee]+)", line) if key != "NCORE" else None
                    if match:
                        actual[key] = finite_number(match[1], key)
                match = re.search(r"free\s+energy\s+TOTEN\s*=\s*(\S+)", line)
                if match:
                    energy = finite_number(match[1], "TOTEN")
                if "TOTAL-FORCE (eV/Angst)" in line:
                    force_rows = []
                elif force_rows is not None:
                    parts = line.split()
                    if not parts or set(line.strip()) <= {"-"}:
                        continue
                    row = numbers(line)
                    if len(row) != 6:
                        raise ValueError("invalid TOTAL-FORCE row")
                    force_rows.append(row)
                    if len(force_rows) == atom_count:
                        positions = [r[:3] for r in force_rows]
                        forces = [r[3:] for r in force_rows]
                        force_rows = None
    if force_rows is not None or len(forces) != atom_count or energy is None:
        raise ValueError("incomplete final energy/force block")
    return {"errors": sorted(errors), "actual": actual, "energy": energy, "forces": forces,
            "positions": positions, "read_wave": read_wave, "read_charge": read_charge}


def collect(directory: Path, expected: dict, reference: dict, tolerance: float, *,
            exit_code: int, restarted: bool = False) -> dict:
    out = parse_outcar(directory / "OUTCAR")
    osz = parse_oszicar(directory / "OSZICAR")
    scf = final_scf_state(osz, read_incar_values(directory / "INCAR"), out)
    atom_count = sum(reference["counts"])
    logs = _scan_logs(directory, expected, atom_count)
    errors = list(out.get("fatal_keywords", [])) + logs["errors"]
    actual_geometry = {**reference, "positions": logs["positions"]}
    drift = geometry_error(reference, actual_geometry, tolerance)
    if (directory / "CONTCAR").exists() and (directory / "CONTCAR").stat().st_size:
        geometry_error(reference, structure(directory / "CONTCAR"), tolerance)
    moments = out.get("local_magnetization_last_muB", [])
    totals = out.get("total_magnetization_history_muB", [])
    if len(moments) != atom_count or not totals:
        raise ValueError("incomplete atom-resolved magnetization")
    if restarted and not (logs["read_wave"] and logs["read_charge"]):
        errors.append("RESTART_USE_NOT_PROVEN")
    numeric = bool(scf["electronically_converged"] and scf["last_electronic_iteration"]
                   and scf["last_electronic_iteration"] <= scf["nelm"]
                   and scf["last_delta_e_eV"] is not None and scf["last_delta_eps_eV"] is not None
                   and abs(scf["last_delta_e_eV"]) <= scf["ediff_eV"]
                   and abs(scf["last_delta_eps_eV"]) <= scf["ediff_eV"]
                   and len(osz["electronic_cycles"]) == 1 and osz["ionic_steps"] == 1)
    return {"errors": errors, "exit_code": exit_code, "normal_end": out.get("normal_completion") is True,
            "electronic_pass": numeric, "scf": scf, "runtime_matches": logs["actual"] == expected,
            "actual_runtime": logs["actual"], "geometry_max_drift_A": drift,
            "state": {"energy": logs["energy"], "forces": logs["forces"], "moments": moments, "total_moment": totals[-1]}}
