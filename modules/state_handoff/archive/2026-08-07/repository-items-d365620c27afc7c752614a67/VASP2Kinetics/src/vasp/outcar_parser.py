"""Read existing scalar results and completion markers from a VASP OUTCAR."""

from __future__ import annotations

import logging
import re
from pathlib import Path

LOGGER = logging.getLogger("vasp2kinetics.vasp.outcar")

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
_TOTEN_PATTERN = re.compile(
    rf"free\s+energy\s+TOTEN\s*=\s*({_NUMBER})",
    re.IGNORECASE,
)
_SCF_ITERATION_PATTERN = re.compile(
    r"\bIteration\s+\d+\s*\(\s*\d+\s*\)",
    re.IGNORECASE,
)
_NORMAL_END_MARKER = "General timing and accounting informations"
_ACCURACY_MARKER = "reached required accuracy"


def _to_float(value: str) -> float:
    """Convert a VASP numeric token, including Fortran D exponents."""

    return float(value.replace("D", "E").replace("d", "e"))


def _error_result(error: str, status: str) -> dict[str, object]:
    """Create a complete OUTCAR result for an expected parser failure."""

    return {
        "status": status,
        "energy_final": None,
        "converged": False,
        "scf_steps": None,
        "error": error,
    }


def parse_outcar(path: str | Path) -> dict[str, object]:
    """Parse the last TOTEN, completion marker, and explicit SCF iterations."""

    outcar_path = Path(path)
    if not outcar_path.is_file():
        LOGGER.warning("OUTCAR is not available: %s", outcar_path)
        return _error_result("OUTCAR_NOT_FOUND", "NOT_AVAILABLE")

    energy_final: float | None = None
    scf_steps = 0
    has_content = False
    has_normal_end = False
    has_accuracy_marker = False

    try:
        with outcar_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    has_content = True

                energy_match = _TOTEN_PATTERN.search(line)
                if energy_match is not None:
                    energy_final = _to_float(energy_match.group(1))

                if _SCF_ITERATION_PATTERN.search(line) is not None:
                    scf_steps += 1

                if _NORMAL_END_MARKER in line:
                    has_normal_end = True
                if _ACCURACY_MARKER in line:
                    has_accuracy_marker = True
    except UnicodeDecodeError:
        LOGGER.error("OUTCAR is not valid UTF-8 text: %s", outcar_path)
        return _error_result("OUTCAR_FORMAT_ERROR", "ERROR")
    except OSError:
        LOGGER.exception("Unable to read OUTCAR: %s", outcar_path)
        return _error_result("OUTCAR_READ_ERROR", "ERROR")

    if not has_content:
        LOGGER.error("OUTCAR is empty: %s", outcar_path)
        return _error_result("OUTCAR_EMPTY", "ERROR")

    converged = has_normal_end or has_accuracy_marker
    result: dict[str, object] = {
        "status": "CONVERGED" if converged else "INCOMPLETE",
        "energy_final": energy_final,
        "converged": converged,
        "scf_steps": scf_steps if scf_steps > 0 else None,
    }

    if energy_final is None:
        result["status"] = "ERROR"
        result["error"] = "OUTCAR_ENERGY_NOT_FOUND"
        LOGGER.error("No TOTEN record found in OUTCAR: %s", outcar_path)
    elif not converged:
        result["error"] = "CALCULATION_NOT_COMPLETED"
        LOGGER.warning("OUTCAR has no accepted completion marker: %s", outcar_path)

    return result
