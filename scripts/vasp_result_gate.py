from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.scientific_validation import finite_number, integer_number


def read_incar_values(path: Path) -> dict[str, str]:
    """Canonical string-valued INCAR reader; conflicting duplicate tags are errors.

    Keep the existing string API (including MAGMOM repetition and logical tokens).
    Bare commentary is allowed by VASP; malformed assignments are never skipped.
    """
    text = path.read_text(encoding="utf-8", errors="strict")
    text = re.sub(r"\\[ \t]*\n", " ", text)
    text = re.sub(r'"[^"]*"|[#!][^\n]*',
                  lambda match: match.group(0) if match.group(0).startswith('"') else "", text)
    values: dict[str, str] = {}
    # Quotes may span lines and contain separators; split only outside quotes.
    statements = re.split(r'[;\n](?=(?:[^"]*"[^"]*")*[^"]*$)', text)
    if text.count('"') % 2:
        raise ValueError("INCAR contains an unterminated quoted value")
    for statement in statements:
        if "=" not in statement:
            continue
        name, value = (part.strip() for part in statement.split("=", 1))
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_/]*", name) or not value:
            raise ValueError("malformed INCAR assignment")
        quoted = value.startswith('"') and value.endswith('"')
        if not quoted and "=" in value:
            raise ValueError("INCAR assignments require a semicolon or newline")
        name = name.upper()
        value = value[1:-1] if quoted else value
        if name in values and values[name].upper() != value.upper():
            raise ValueError(f"conflicting duplicate INCAR tag: {name}")
        if name in {"NELM", "NELMIN", "NSW", "IMAGES", "IBRION", "ISMEAR", "ICHAIN", "IOPT", "ISPIN"}:
            integer_number(value, name, positive=name in {"NELM", "NELMIN", "ISPIN"})
        elif name in {"EDIFF", "EDIFFG", "ENCUT", "SIGMA", "POTIM", "DIMER_DIST", "DIMER_MAXROT"}:
            finite_number(value, name, positive=name == "ENCUT", nonnegative=name in {"EDIFF", "SIGMA"})
        values[name] = value
    return values


def incar_value(path: Path, key: str) -> str:
    values = read_incar_values(path)
    wanted = key.upper()
    if wanted in values:
        return values[wanted]
    raise ValueError(f"INCAR missing {key}")


def final_scf_status(
    oszicar: Path, incar: Path, outcar: Path | None = None, *, include_cycles: bool = False,
) -> dict[str, Any]:
    """Preserve the six-field public summary; opt into explicit cycle details.

    Both views use the same final-state validator. The default remains compatible
    with external force-label schemas that disallow additional fields.
    """
    state = final_scf_state(parse_oszicar(oszicar), read_incar_values(incar),
                            parse_outcar(outcar) if outcar else None)
    if include_cycles:
        return state
    return {key: state[key] for key in (
        "last_electronic_iteration", "last_delta_e_eV", "ediff_eV", "nelm",
        "electronically_converged", "electronic_convergence_source",
    )}


def final_scf_state(parsed: dict, values: dict[str, str], outcar: dict | None = None) -> dict[str, Any]:
    """Interpret already-parsed final cycles, shared by gates and NEB monitoring."""
    if not {"NELM", "EDIFF"} <= values.keys():
        raise ValueError("INCAR missing NELM or EDIFF")
    nelm = integer_number(values["NELM"], "NELM", positive=True)
    ediff = finite_number(values["EDIFF"], "EDIFF", nonnegative=True)
    latest = parsed.get("latest_started_electronic_cycle")
    out = outcar or {}
    final_out = out.get("final_target_step")
    aligned = bool(latest and final_out and latest["cycle"] == final_out["cycle"] and (
        final_out["iteration"] is None or final_out["iteration"] == latest["iteration"]
    ))
    explicit = bool(aligned and out.get("electronic_convergence_reached"))
    complete = bool(latest and not latest["malformed"] and (
        parsed.get("final_target_complete") or explicit
    ))
    if outcar is not None:
        # A complete OSZICAR cycle with both deltas is independent convergence
        # evidence when a compact OUTCAR contains only its normal footer.
        compact_complete = final_out is None and out.get("normal_completion")
        if not compact_complete and (not out.get("exists") or out.get("incomplete") or not aligned):
            complete = False
    iteration = latest["iteration"] if latest else None
    delta_e = latest["delta_e_eV"] if latest else None
    delta_eps = latest["delta_eps_eV"] if latest else None
    numeric = bool(iteration and iteration < nelm and delta_e is not None and delta_eps is not None
                   and ediff > 0 and abs(delta_e) <= ediff and abs(delta_eps) <= ediff)
    converged = bool(complete and iteration and iteration <= nelm and (explicit or numeric))
    incomplete = not complete or (not explicit and (delta_e is None or delta_eps is None))
    return {"last_electronic_iteration": iteration, "last_delta_e_eV": delta_e,
            "last_delta_eps_eV": delta_eps, "ediff_eV": ediff, "nelm": nelm,
            "electronically_converged": converged,
            "electronic_convergence_source": "OUTCAR_EDIFF_TERMINATION" if explicit else "OSZICAR_DELTA_E",
            "latest_started_electronic_cycle": latest,
            "latest_completed_electronic_cycle": parsed.get("latest_completed_electronic_cycle"),
            "final_target_step": latest, "final_target_complete": complete,
            "final_target_explicit_convergence": explicit,
            "incomplete": incomplete,
            "status": "PASS" if converged else "INCOMPLETE" if incomplete else "NOT_CONVERGED"}


def validate_lsf_done_evidence(payload: dict[str, Any]) -> None:
    from scripts.execution_backends import require_vasp_backend

    require_vasp_backend(payload.get("server_alias"), payload.get("scheduler"))
    if payload.get("status") != "DONE" or not payload.get("job_id") or not payload.get("source_command"):
        raise ValueError("scheduler evidence lacks an authoritative DONE record")


def validate_vasp_relaxation(directory: Path) -> dict[str, Any]:
    required = [directory / name for name in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("VASP relaxation files missing or empty: " + ", ".join(missing))
    outcar = parse_outcar(directory / "OUTCAR")
    scf = final_scf_state(parse_oszicar(directory / "OSZICAR"), read_incar_values(directory / "INCAR"), outcar)
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
