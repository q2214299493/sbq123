from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.execution_backends import require_vasp_backend


def read_incar_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("!", 1)[0].split("#", 1)[0]
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip().upper()] = value.strip()
    return values


def incar_value(path: Path, key: str) -> str:
    values = read_incar_values(path)
    wanted = key.upper()
    if wanted in values:
        return values[wanted]
    raise ValueError(f"INCAR missing {key}")


def final_scf_status(oszicar: Path, incar: Path, outcar: Path | None = None) -> dict[str, Any]:
    nelm = int(float(incar_value(incar, "NELM")))
    ediff = float(incar_value(incar, "EDIFF"))
    current: tuple[int, float] | None = None
    completed: tuple[int, float] | None = None
    for raw in oszicar.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = raw.split()
        if fields and fields[0] in {"DAV:", "RMM:", "CGA:"} and len(fields) >= 4:
            try:
                current = int(fields[1]), float(fields[3])
            except ValueError:
                continue
        elif " F=" in raw and current is not None:
            completed = current
            current = None
    latest = completed or current
    if latest is None:
        raise ValueError("OSZICAR has no completed electronic cycle")
    iteration, delta_e = latest
    outcar_converged = bool(
        outcar and parse_outcar(outcar).get("electronic_convergence_reached")
    )
    return {
        "last_electronic_iteration": iteration,
        "last_delta_e_eV": delta_e,
        "ediff_eV": ediff,
        "nelm": nelm,
        "electronically_converged": outcar_converged or (
            abs(delta_e) <= ediff and iteration < nelm
        ),
        "electronic_convergence_source": (
            "OUTCAR_EDIFF_TERMINATION" if outcar_converged else "OSZICAR_DELTA_E"
        ),
    }


def validate_lsf_done_evidence(payload: dict[str, Any]) -> None:
    require_vasp_backend(payload.get("server_alias"), payload.get("scheduler"))
    if payload.get("status") != "DONE" or not payload.get("job_id") or not payload.get("source_command"):
        raise ValueError("scheduler evidence lacks an authoritative DONE record")


def validate_vasp_relaxation(directory: Path) -> dict[str, Any]:
    required = [directory / name for name in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("VASP relaxation files missing or empty: " + ", ".join(missing))
    outcar = parse_outcar(directory / "OUTCAR")
    scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
    errors: list[str] = []
    if not outcar.get("normal_completion"):
        errors.append("normal_completion_missing")
    if outcar.get("fatal_keywords"):
        errors.append("fatal_keywords=" + ",".join(outcar["fatal_keywords"]))
    if not outcar.get("reached_required_accuracy"):
        errors.append("ionic_convergence_missing")
    if not scf["electronically_converged"]:
        errors.append("electronic_convergence_failed")
    if errors:
        raise ValueError("VASP relaxation result gate failed: " + "; ".join(errors))
    return {"normal_completion": True, "ionic_converged": True, **scf}
