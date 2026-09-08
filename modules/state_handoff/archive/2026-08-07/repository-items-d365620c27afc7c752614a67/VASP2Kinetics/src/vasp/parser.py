"""Unified entry point for read-only VASP result parsing."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..exceptions import ResultWriteError
from .neb_parser import find_neb_image_directories, parse_neb
from .oszicar_parser import parse_oszicar
from .outcar_parser import parse_outcar

LOGGER = logging.getLogger("vasp2kinetics.vasp")


def _empty_result(path: Path) -> dict[str, object]:
    """Create the stable top-level result shape."""

    return {
        "calculation_id": "unknown",
        "type": "vasp",
        "files": {
            "OUTCAR": False,
            "OSZICAR": False,
        },
        "energy": {
            "final": None,
        },
        "convergence": {
            "status": "unknown",
        },
        "outcar": None,
        "oszicar": None,
        "neb": None,
        "source": {
            "path": str(path),
        },
    }


def parse_vasp_case(path: str | Path) -> dict[str, object]:
    """Parse a single VASP directory or a directory containing NEB images."""

    case_path = Path(path).expanduser().resolve()
    result = _empty_result(case_path)
    if not case_path.is_dir():
        result["error"] = "VASP_CASE_NOT_FOUND"
        LOGGER.error("VASP case directory does not exist: %s", case_path)
        return result

    outcar_path = case_path / "OUTCAR"
    oszicar_path = case_path / "OSZICAR"
    result["files"] = {
        "OUTCAR": outcar_path.is_file(),
        "OSZICAR": oszicar_path.is_file(),
    }

    outcar_result = parse_outcar(outcar_path)
    oszicar_result = parse_oszicar(oszicar_path)
    result["outcar"] = outcar_result
    result["oszicar"] = oszicar_result
    result["energy"] = {"final": outcar_result["energy_final"]}

    if outcar_result["status"] == "CONVERGED":
        result["convergence"] = {"status": "converged"}
    elif outcar_result["status"] == "INCOMPLETE":
        result["convergence"] = {"status": "not_converged"}

    try:
        image_directories = find_neb_image_directories(case_path)
    except OSError:
        result["error"] = "VASP_CASE_READ_ERROR"
        LOGGER.exception("Unable to inspect VASP case directory: %s", case_path)
        return result

    if image_directories:
        neb_result = parse_neb(case_path)
        result["neb"] = neb_result
        neb_error = neb_result.get("error")
        if isinstance(neb_error, str):
            result["error"] = neb_error
    else:
        outcar_error = outcar_result.get("error")
        if isinstance(outcar_error, str):
            result["error"] = outcar_error

    return result


def write_vasp_result(result: dict[str, object], path: str | Path) -> Path:
    """Write a standardized VASP result as UTF-8 JSON."""

    output_path = Path(path).expanduser().resolve()
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ResultWriteError(f"Unable to write VASP result: {output_path}") from exc

    return output_path
