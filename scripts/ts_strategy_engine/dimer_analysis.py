from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.aqcat25_ts_schema import load_document
from scripts.artifact_io import load_json_object, sha256_file, sha256_text
from scripts.neb_agent.utils_report import write_json
from scripts.neb_agent.utils_structure import compatible, read_poscar
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.vasp_result_gate import final_scf_status, incar_value, validate_lsf_done_evidence


def _ediffg(path: Path) -> float | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0]
        if "=" not in clean:
            continue
        key, value = (part.strip() for part in clean.split("=", 1))
        if key.upper() == "EDIFFG":
            try:
                return float(value.split()[0])
            except ValueError:
                return None
    return None


def _positive_incar_float(path: Path, key: str) -> float | None:
    try:
        value = float(incar_value(path, key))
    except (OSError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def parse_dimcar(path: Path) -> list[dict[str, float | int | None]]:
    if not path.is_file():
        return []
    rows: list[dict[str, float | int | None]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 6 or not fields[0].isdigit():
            continue
        values: list[float | None] = []
        for value in fields[1:6]:
            try:
                values.append(float(value))
            except ValueError:
                values.append(None)
        rows.append(
            {
                "step": int(fields[0]),
                "force_eVA": values[0],
                "torque_eVA": values[1],
                "energy_eV": values[2],
                "curvature_eVA2": values[3],
                "angle_deg": values[4],
            }
        )
    return rows


def _dimer_evidence(workdir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    source = workdir / "POSCAR"
    final = workdir / "CONTCAR"
    checks["contract_hashes"] = all(
        len(str(manifest.get(key, ""))) == 64
        for key in (
            "contract_sha256",
            "atom_map_sha256",
            "compatibility_sha256",
            "path_generation_sha256",
        )
    )
    checks["source_structure_hash"] = bool(
        source.is_file()
        and len(str(manifest.get("source_sha256", ""))) == 64
        and sha256_file(source) == manifest.get("source_sha256")
    )
    try:
        source_structure = read_poscar(source)
        final_structure = read_poscar(final)
        checks["final_structure"] = not compatible(source_structure, final_structure)
    except (OSError, ValueError):
        checks["final_structure"] = False
    try:
        checks["dimer_input"] = int(float(incar_value(workdir / "INCAR", "ICHAIN"))) == 2
    except (OSError, ValueError):
        checks["dimer_input"] = False
    try:
        scf = final_scf_status(workdir / "OSZICAR", workdir / "INCAR", workdir / "OUTCAR")
    except (OSError, ValueError):
        scf = {"electronically_converged": False}
    checks["electronic_convergence"] = bool(scf.get("electronically_converged"))
    details["scf"] = scf
    scheduler_path = workdir / "scheduler_evidence.json"
    try:
        scheduler = load_document(
            scheduler_path, expected_kind="scheduler_job_evidence"
        )
        validate_lsf_done_evidence(scheduler)
        query = scheduler["query"]
        stdout = query["stdout"]
        if (
            sha256_text(stdout) != query["stdout_sha256"]
            or str(scheduler["job_id"]) not in stdout
            or "DONE" not in stdout.split()
        ):
            raise ValueError("DIMER scheduler raw evidence is not bound to the DONE job")
        checks["scheduler_done"] = True
        details["scheduler_job_id"] = str(scheduler["job_id"])
        details["scheduler_evidence_sha256"] = sha256_file(scheduler_path)
    except (OSError, ValueError, KeyError):
        checks["scheduler_done"] = False
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "errors": [name for name, passed in checks.items() if not passed],
        **details,
    }


def analyze_dimer(workdir: Path) -> dict[str, Any]:
    rows = parse_dimcar(workdir / "DIMCAR")
    outcar = parse_outcar(workdir / "OUTCAR")
    target = _ediffg(workdir / "INCAR")
    force_target = abs(target) if target is not None and target < 0 else None
    torque_target = _positive_incar_float(workdir / "INCAR", "DFNMin")
    complete_rows = [
        row
        for row in rows
        if all(
            row[key] is not None
            for key in ("force_eVA", "torque_eVA", "energy_eV", "curvature_eVA2")
        )
    ]
    last = complete_rows[-1] if complete_rows else None
    manifest_path = workdir / "dimer_handoff.json"
    mode_review_path = workdir / "mode_review.json"
    manifest = load_json_object(manifest_path) if manifest_path.is_file() else {}
    mode_review = load_json_object(mode_review_path) if mode_review_path.is_file() else {}
    evidence = _dimer_evidence(workdir, manifest)
    contract_bound = bool(evidence["checks"]["contract_hashes"])
    initial_mode_path = workdir / "MODECAR"
    mode_reviewed = bool(
        mode_review.get("status") == "accepted"
        and mode_review.get("reviewer")
        and mode_review.get("reviewed_at")
        and initial_mode_path.is_file()
        and mode_review.get("modecar_sha256") == sha256_file(initial_mode_path)
    )
    negative_curvature = bool(last and last["curvature_eVA2"] is not None and last["curvature_eVA2"] < 0)
    dimer_force_converged = bool(
        last
        and force_target is not None
        and last["force_eVA"] is not None
        and abs(float(last["force_eVA"])) <= force_target
    )
    torque_converged = bool(
        last
        and torque_target is not None
        and last["torque_eVA"] is not None
        and abs(float(last["torque_eVA"])) <= torque_target
    )
    positive_curvature_streak = 0
    for row in reversed(complete_rows):
        curvature = row["curvature_eVA2"]
        if curvature is None or curvature <= 0:
            break
        positive_curvature_streak += 1
    final_atomic_force = (
        float(outcar["atomic_force_history"][-1])
        if outcar.get("atomic_force_history")
        else None
    )
    final_atomic_force_rms = (
        float(outcar["atomic_force_rms_history"][-1])
        if outcar.get("atomic_force_rms_history")
        else None
    )
    vasp_force_converged = bool(
        force_target is not None
        and final_atomic_force is not None
        and final_atomic_force <= force_target
    )
    dimer_soft_gate_passed = bool(dimer_force_converged and torque_converged)
    soft_warnings = []
    if not dimer_force_converged:
        soft_warnings.append("DIMER_FORCE_ABOVE_TARGET")
    if not torque_converged:
        soft_warnings.append("DIMER_TORQUE_ABOVE_DFNMIN")
    search_converged = bool(
        last
        and vasp_force_converged
        and negative_curvature
        and evidence["passed"]
        and mode_reviewed
        and outcar.get("normal_completion")
        and not outcar.get("fatal_keywords")
    )
    final_structure = next(
        (
            str(path)
            for path in (workdir / "CONTCAR", workdir / "CENTCAR")
            if path.is_file() and path.stat().st_size > 0
        ),
        None,
    )
    final_mode = next(
        (str(path) for path in (workdir / "NEWMODECAR", workdir / "MODECAR") if path.is_file() and path.stat().st_size > 0),
        None,
    )
    final_review_path = workdir / "final_mode_review.json"
    final_review = load_json_object(final_review_path) if final_review_path.is_file() else {}
    final_mode_sha256 = sha256_file(Path(final_mode)) if final_mode else None
    final_mode_reviewed = bool(
        final_mode
        and final_review.get("status") == "accepted"
        and final_review.get("reviewer")
        and final_review.get("reviewed_at")
        and final_review.get("modecar_sha256") == final_mode_sha256
    )
    technically_converged = bool(search_converged and final_structure and final_mode and final_mode_reviewed)
    if search_converged and final_mode and not final_review_path.exists():
        write_json(
            final_review_path,
            {
                "status": "needs_review",
                "modecar_file": final_mode,
                "modecar_sha256": final_mode_sha256,
                "reviewer": None,
                "reviewed_at": None,
                "notes": None,
            },
        )
    if not rows and not outcar.get("exists"):
        status = "NO_OUTPUT"
    elif outcar.get("fatal_keywords"):
        status = "FAILED"
    elif technically_converged and dimer_soft_gate_passed:
        status = "TECHNICALLY_CONVERGED_NEEDS_FREQUENCY"
    elif technically_converged:
        status = "TECHNICALLY_CONVERGED_SOFT_REVIEW_REQUIRED"
    elif search_converged:
        status = "TECHNICALLY_CONVERGED_NEEDS_FINAL_MODE_REVIEW"
    elif positive_curvature_streak >= 5:
        status = "POSITIVE_CURVATURE_REVIEW_REQUIRED"
    else:
        status = "RUNNING_OR_INCOMPLETE"
    payload = {
        "status": status,
        "dimcar_rows": rows,
        "complete_dimcar_rows": len(complete_rows),
        "translation_steps": max((int(row["step"]) for row in rows), default=0),
        "force_target_eVA": force_target,
        "torque_target_eVA": torque_target,
        "final_force_eVA": last["force_eVA"] if last else None,
        "final_torque_eVA": last["torque_eVA"] if last else None,
        "final_curvature_eVA2": last["curvature_eVA2"] if last else None,
        # Backward-compatible DIMCAR metric. VASP atomic-force convergence is
        # reported separately and is the hard technical convergence criterion.
        "force_converged": dimer_force_converged,
        "dimer_force_converged": dimer_force_converged,
        "torque_converged": torque_converged,
        "dimer_soft_gate_passed": dimer_soft_gate_passed,
        "dimer_soft_warnings": soft_warnings,
        "final_atomic_force_eVA": final_atomic_force,
        "final_atomic_force_max_eVA": final_atomic_force,
        "final_atomic_force_rms_eVA": final_atomic_force_rms,
        "vasp_force_convergence_source": "OUTCAR:last_complete_FORCES_max_atom",
        "vasp_force_converged": vasp_force_converged,
        "negative_curvature": negative_curvature,
        "contract_bound": contract_bound,
        "evidence_gate": evidence,
        "mode_reviewed": mode_reviewed,
        "final_mode_reviewed": final_mode_reviewed,
        "contract_sha256": manifest.get("contract_sha256"),
        "atom_map_sha256": manifest.get("atom_map_sha256"),
        "compatibility_sha256": manifest.get("compatibility_sha256"),
        "path_generation_sha256": manifest.get("path_generation_sha256"),
        "positive_curvature_streak": positive_curvature_streak,
        "normal_completion": bool(outcar.get("normal_completion")),
        "fatal_keywords": outcar.get("fatal_keywords", []),
        "technically_converged": technically_converged,
        "final_structure": final_structure,
        "final_mode": final_mode,
        "scientifically_valid": False,
        "requires_frequency_and_connectivity_validation": True,
    }
    write_json(workdir / "dimer_analysis.json", payload)
    return payload
