from __future__ import annotations

import re
from pathlib import Path

from scripts.scientific_validation import finite_number, integer_number


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


def _cycle(number: int, ionic_step: int | None = None) -> dict:
    return {"cycle": number, "ionic_step": ionic_step, "iteration": None,
            "delta_e_eV": None, "delta_eps_eV": None, "complete": False,
            "explicit_convergence": False, "malformed": False}


def _cycle_state(cycles: list[dict]) -> dict:
    latest = cycles[-1] if cycles else None
    completed = next((cycle for cycle in reversed(cycles) if cycle["complete"]), None)
    return {"latest_started_electronic_cycle": latest,
            "latest_completed_electronic_cycle": completed,
            "final_target_step": latest,
            "final_target_complete": bool(latest and latest["complete"] and not latest["malformed"]),
            "final_target_explicit_convergence": bool(latest and latest["explicit_convergence"]),
            "incomplete": not latest or not latest["complete"] or latest["malformed"]}


def parse_oszicar(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False, "ionic_steps": 0, "energies": [], "scf_iterations": []}
    energies: list[float] = []
    magnetization: list[float] = []
    scf_per_step: list[int] = []
    cycles: list[dict] = []
    active = None
    current = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if OSZICAR_SCF_PATTERN.match(line):
                fields = line.split()
                if active is None:
                    active = _cycle(len(cycles) + 1)
                    cycles.append(active)
                current += 1
                try:
                    iteration = integer_number(fields[1], "SCF iteration", positive=True)
                    if active["iteration"] is not None and iteration <= active["iteration"]:
                        active = _cycle(len(cycles) + 1)
                        cycles.append(active)
                        current = 1
                    active["iteration"] = iteration
                    active["delta_e_eV"] = finite_number(fields[3], "SCF dE")
                    active["delta_eps_eV"] = finite_number(fields[4], "SCF d eps") if len(fields) >= 5 else None
                except (IndexError, ValueError):
                    active["malformed"] = True
            elif re.search(r"\bF\s*=", line):
                if active is None:
                    active = _cycle(len(cycles) + 1)
                    cycles.append(active)
                try:
                    energy = finite_number(OSZICAR_ENERGY_PATTERN.search(line).group(1), "ionic energy")
                    active["ionic_step"] = integer_number(line.split()[0], "ionic step", positive=True)
                    energies.append(energy)
                    active["complete"] = True
                except (AttributeError, ValueError):
                    active["malformed"] = True
                scf_per_step.append(current)
                current = 0
                active = None
            elif re.match(r"\s*N\s+E\s+dE", line) and active is None:
                active = _cycle(len(cycles) + 1)
                cycles.append(active)
            magnetization.extend(float(m.group(1)) for m in OSZICAR_MAGNETIZATION_PATTERN.finditer(line))
    return {"exists": True, "ionic_steps": len(energies), "energies": energies,
            "scf_iterations": scf_per_step, "current_scf_iterations": current,
            "magnetization_history_muB": magnetization, "electronic_cycles": cycles,
            **_cycle_state(cycles)}


def _advance_outcar_cycle(line: str, cycles: list[dict], active: dict | None, energies: list[float]) -> tuple[dict | None, bool]:
    """Advance one OUTCAR electronic target; report whether an earlier footer is stale."""
    started = False
    iteration = re.search(r"Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)", line)
    if iteration:
        ionic, electronic = map(int, iteration.groups())
        if active is None or electronic == 1 or active["ionic_step"] != ionic:
            active = _cycle(len(cycles) + 1, ionic)
            cycles.append(active)
            started = True
        active["iteration"] = electronic
    elif "Iteration" in line and "(" in line:
        active = _cycle(len(cycles) + 1)
        active["malformed"] = True
        cycles.append(active)
        started = True
    if "aborting loop because EDIFF is reached" in line:
        # VASP prints energy(sigma->0) inside the numbered electronic loop.
        # Its later EDIFF marker belongs to that same target, not a new cycle.
        if active is None or (active["complete"] and active["iteration"] is None):
            active = _cycle(len(cycles) + 1)
            cycles.append(active)
        active["explicit_convergence"] = True
    if "energy(sigma->0)" in line:
        try:
            energies.append(finite_number(OUTCAR_SIGMA0_PATTERN.search(line).group(1), "OUTCAR energy"))
            if active:
                active["complete"] = True
        except (AttributeError, ValueError):
            if active is None:
                active = _cycle(len(cycles) + 1)
                cycles.append(active)
            active["malformed"] = True
    if active and "General timing and accounting informations for this job" in line:
        active["complete"] = True
    return active, started


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
    cycles: list[dict] = []
    active = None
    run_index = 0
    reached_required_accuracy = False
    normal_completion = False
    collecting_local_magnetization = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if re.match(r"\s*vasp\.\d", line):
                run_index += 1
                cycles = []
                active = None
                reached_required_accuracy = normal_completion = False
            active, started = _advance_outcar_cycle(line, cycles, active, sigma0)
            if started:
                reached_required_accuracy = normal_completion = False
            for match in OUTCAR_FORCE_PATTERN.finditer(line):
                atomic.append(float(match.group(1)))
                atomic_rms.append(float(match.group(2)))
            neb.extend(
                float(match.group(1))
                for match in OUTCAR_NEB_FORCE_PATTERN.finditer(line)
            )
            total_magnetization.extend(
                float(match.group(1))
                for match in OUTCAR_MAGNETIZATION_PATTERN.finditer(line)
            )
            fatal_keywords.update(match.group(0) for match in FATAL_PATTERN.finditer(line))
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
        "electronic_convergence_reached": bool(active and active["complete"] and active["explicit_convergence"] and not active["malformed"]),
        "electronic_cycles": cycles,
        "run_index": run_index,
        **_cycle_state(cycles),
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
