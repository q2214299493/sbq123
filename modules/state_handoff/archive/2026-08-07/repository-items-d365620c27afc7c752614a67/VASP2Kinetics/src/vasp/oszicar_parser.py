"""Read electronic and ionic iteration summaries from a VASP OSZICAR."""

from __future__ import annotations

import logging
import re
from pathlib import Path

LOGGER = logging.getLogger("vasp2kinetics.vasp.oszicar")

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
_ELECTRONIC_PATTERN = re.compile(
    rf"^\s*(?:DAV|RMM(?:-DIIS)?|CG|DMP)\s*:\s*\d+\s+({_NUMBER})",
    re.IGNORECASE,
)
_IONIC_PATTERN = re.compile(r"^\s*\d+\s+(?:F=|T=)", re.IGNORECASE)


def _to_float(value: str) -> float:
    """Convert a VASP numeric token, including Fortran D exponents."""

    return float(value.replace("D", "E").replace("d", "e"))


def _error_result(error: str, status: str) -> dict[str, object]:
    """Create a complete OSZICAR result for an expected parser failure."""

    return {
        "status": status,
        "electronic_steps": None,
        "ionic_steps": None,
        "final_energy": None,
        "error": error,
    }


def parse_oszicar(path: str | Path) -> dict[str, object]:
    """Parse explicit OSZICAR iteration records without inferring missing data."""

    oszicar_path = Path(path)
    if not oszicar_path.is_file():
        LOGGER.warning("OSZICAR is not available: %s", oszicar_path)
        return _error_result("OSZICAR_NOT_FOUND", "NOT_AVAILABLE")

    electronic_steps = 0
    ionic_steps = 0
    final_energy: float | None = None
    has_content = False

    try:
        with oszicar_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    has_content = True

                electronic_match = _ELECTRONIC_PATTERN.match(line)
                if electronic_match is not None:
                    electronic_steps += 1
                    final_energy = _to_float(electronic_match.group(1))

                if _IONIC_PATTERN.match(line) is not None:
                    ionic_steps += 1
    except UnicodeDecodeError:
        LOGGER.error("OSZICAR is not valid UTF-8 text: %s", oszicar_path)
        return _error_result("OSZICAR_FORMAT_ERROR", "ERROR")
    except OSError:
        LOGGER.exception("Unable to read OSZICAR: %s", oszicar_path)
        return _error_result("OSZICAR_READ_ERROR", "ERROR")

    if not has_content:
        LOGGER.error("OSZICAR is empty: %s", oszicar_path)
        return _error_result("OSZICAR_EMPTY", "ERROR")

    if electronic_steps == 0:
        LOGGER.error("No electronic iteration record found in OSZICAR: %s", oszicar_path)
        return _error_result("OSZICAR_ELECTRONIC_STEPS_NOT_FOUND", "ERROR")

    return {
        "status": "AVAILABLE",
        "electronic_steps": electronic_steps,
        "ionic_steps": ionic_steps,
        "final_energy": final_energy,
    }
