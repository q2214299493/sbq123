from __future__ import annotations

import re
from pathlib import Path


FATAL_PATTERN = re.compile(r"BRMIX|ZBRENT|VERY BAD NEWS|EDDDAV|segmentation|forrtl|M_divide|internal error", re.I)
OSZICAR_ENERGY_PATTERN = re.compile(r"\bF=\s*([-+0-9.Ee]+)")
OSZICAR_MAGNETIZATION_PATTERN = re.compile(r"\bmag=\s*([-+0-9.Ee]+)")
OSZICAR_SCF_PATTERN = re.compile(r"\s*(DAV|RMM|CGA):")
OUTCAR_FORCE_PATTERN = re.compile(
    r"FORCES: max atom, RMS\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)"
)
OUTCAR_NEB_FORCE_PATTERN = re.compile(
    r"NEB: forces: par spring, perp REAL, dneb\s+[-+0-9.Ee]+\s+([-+0-9.Ee]+)"
)
OUTCAR_SIGMA0_PATTERN = re.compile(
    r"energy\(sigma->0\)\s*=\s*([-+0-9.Ee]+)"
)
OUTCAR_MAGNETIZATION_PATTERN = re.compile(
    r"number of electron\s+[-+0-9.Ee]+\s+magnetization\s+([-+0-9.Ee]+)"
)
LOCAL_MAGNETIZATION_ROW_PATTERN = re.compile(
    r"\s*(\d+)\s+[-+0-9.Ee]+\s+[-+0-9.Ee]+\s+[-+0-9.Ee]+\s+([-+0-9.Ee]+)\s*$"
)


def parse_oszicar(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False, "ionic_steps": 0, "energies": [], "scf_iterations": []}
    energies: list[float] = []
    magnetization: list[float] = []
    scf_per_step: list[int] = []
    current = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            energies.extend(
                float(match.group(1))
                for match in OSZICAR_ENERGY_PATTERN.finditer(line)
            )
            magnetization.extend(
                float(match.group(1))
                for match in OSZICAR_MAGNETIZATION_PATTERN.finditer(line)
            )
            if OSZICAR_SCF_PATTERN.match(line):
                current += 1
            elif " F=" in line:
                scf_per_step.append(current)
                current = 0
    return {
        "exists": True,
        "ionic_steps": len(energies),
        "energies": energies,
        "scf_iterations": scf_per_step,
        "current_scf_iterations": current,
        "magnetization_history_muB": magnetization,
    }


def parse_outcar(path: Path) -> dict:
    if not path.is_file():
        return {
            "exists": False,
            "atomic_force_history": [],
            "atomic_force_rms_history": [],
            "neb_force_history": [],
        }
    atomic: list[float] = []
    atomic_rms: list[float] = []
    neb: list[float] = []
    sigma0: list[float] = []
    total_magnetization: list[float] = []
    local_magnetization: list[float] = []
    fatal_keywords: set[str] = set()
    electronic_convergence_reached = False
    reached_required_accuracy = False
    normal_completion = False
    collecting_local_magnetization = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for match in OUTCAR_FORCE_PATTERN.finditer(line):
                atomic.append(float(match.group(1)))
                atomic_rms.append(float(match.group(2)))
            neb.extend(
                float(match.group(1))
                for match in OUTCAR_NEB_FORCE_PATTERN.finditer(line)
            )
            sigma0.extend(
                float(match.group(1))
                for match in OUTCAR_SIGMA0_PATTERN.finditer(line)
            )
            total_magnetization.extend(
                float(match.group(1))
                for match in OUTCAR_MAGNETIZATION_PATTERN.finditer(line)
            )
            fatal_keywords.update(match.group(0) for match in FATAL_PATTERN.finditer(line))
            electronic_convergence_reached |= "aborting loop because EDIFF is reached" in line
            reached_required_accuracy |= "reached required accuracy" in line
            normal_completion |= "General timing and accounting informations for this job" in line

            if "magnetization (x)" in line:
                local_magnetization = []
                collecting_local_magnetization = True
                continue
            if collecting_local_magnetization:
                match = LOCAL_MAGNETIZATION_ROW_PATTERN.match(line)
                if match:
                    local_magnetization.append(float(match.group(2)))
                elif local_magnetization:
                    collecting_local_magnetization = False
    return {
        "exists": True,
        "atomic_force_history": atomic,
        "atomic_force_rms_history": atomic_rms,
        "neb_force_history": neb,
        "sigma0_energies": sigma0,
        "electronic_convergence_reached": electronic_convergence_reached,
        "reached_required_accuracy": reached_required_accuracy,
        "normal_completion": normal_completion,
        "total_magnetization_history_muB": total_magnetization,
        "local_magnetization_last_muB": local_magnetization,
        "fatal_keywords": sorted(fatal_keywords),
    }


def classify_force_trend(values: list[float], window: int = 10) -> str:
    recent = values[-window:]
    if len(recent) < 3:
        return "insufficient_data"
    start = sum(recent[: max(1, len(recent) // 3)]) / max(1, len(recent) // 3)
    end = sum(recent[-max(1, len(recent) // 3) :]) / max(1, len(recent) // 3)
    amplitude = max(recent) - min(recent)
    if end < 0.8 * start:
        return "decreasing"
    if amplitude < 0.15 * max(end, 1e-12):
        return "plateau"
    return "oscillating"


def trailing_threshold_count(values: list[int], threshold: int | None) -> int:
    if not threshold:
        return 0
    count = 0
    for value in reversed(values):
        if value < threshold:
            break
        count += 1
    return count
