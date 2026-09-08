#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
from pathlib import Path
from typing import Any

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[1]
CALCULATION_TYPES = (
    "adsorption_GO",
    "adsorption_static",
    "endpoint_GO",
    "pre_NEB",
    "refine_NEB",
    "CI_NEB",
    "local_NEB",
    "DIMER",
    "VFA",
)
DIAGNOSTIC_NAMES = (
    "endpoint_check.json",
    "path_geometry_diagnosis.json",
    "neb_analysis.json",
    "vfa_analysis.json",
    "vasp_error_report.json",
    "replan_decision.json",
)


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def raw_incar_value(path: Path | None, key: str) -> str | None:
    if path is None or not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].split("!", 1)[0]
        if "=" not in clean:
            continue
        name, value = clean.split("=", 1)
        if name.strip().upper() == key.upper():
            return value.strip()
    return None


def write_incar_candidate(incar_class: Any, values: dict[str, Any], path: Path, magmom_text: str | None) -> None:
    incar_class(values).write_file(path)
    if not magmom_text:
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if "=" in line and line.split("=", 1)[0].strip().upper() == "MAGMOM":
            lines[index] = f"MAGMOM = {magmom_text}"
            replaced = True
            break
    if not replaced:
        lines.append(f"MAGMOM = {magmom_text}")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def find_project_root(start: Path) -> Path | None:
    candidates = [start.resolve(), Path.cwd().resolve()]
    for candidate in candidates:
        for parent in (candidate, *candidate.parents):
            if (parent / "AGENTS.md").is_file() and (parent / "docs").is_dir():
                return parent
    return None


def load_project_profiles(workdir: Path) -> tuple[dict[str, Any], Path | None]:
    root = find_project_root(workdir)
    path = root / "configs" / "incar_custodian" / "project_profiles.yaml" if root else None
    if not path or not path.is_file() or root is None:
        return {}, None
    project = read_yaml(path)
    for material in (project.get("materials") or {}).values():
        source_name = material.get("profile_source")
        if not source_name:
            continue
        source_path = root / str(source_name)
        source = read_yaml(source_path)
        stages: dict[str, Any] = {}
        for calculation_type, dotted_path in (material.get("stage_map") or {}).items():
            value: Any = source
            for key in str(dotted_path).split("."):
                value = value[key]
            stages[calculation_type] = dict(value)
        material["calculation_types"] = stages
    return project, path


def require_pymatgen():
    try:
        from pymatgen.io.vasp.inputs import Incar, Poscar
    except ImportError as exc:
        raise SystemExit("pymatgen is required: python -m pip install pymatgen") from exc
    return Incar, Poscar


def load_structure(path: Path | None) -> tuple[list[str], list[int]]:
    if path is None:
        return [], []
    _, Poscar = require_pymatgen()
    poscar = Poscar.from_file(path)
    return list(poscar.site_symbols), [int(value) for value in poscar.natoms]


def detect_surface_family(
    symbols: list[str], requested: str | None, material: str | None, project: dict[str, Any]
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if requested:
        return requested, warnings
    material_record = (project.get("materials") or {}).get(material or "", {})
    if material_record.get("surface_family"):
        return str(material_record["surface_family"]), warnings
    if set(symbols) == {"Fe"}:
        return "metal_fe", warnings
    warnings.append("Composition does not distinguish lattice C/O from adsorbates; surface family remains unknown.")
    return "unknown", warnings


def format_moment(value: Any) -> str:
    numeric = float(value)
    return f"{numeric:.1f}" if numeric.is_integer() else f"{numeric:g}"


def build_magmom(symbols: list[str], counts: list[int], family: str, project: dict[str, Any]) -> tuple[str | None, list[str]]:
    record = (project.get("surface_families") or {}).get(family, {})
    warnings: list[str] = []
    if record.get("requires_user_magmom"):
        return None, [str(record.get("warning", "User MAGMOM pattern required."))]
    defaults = record.get("magmom") or {}
    if not defaults:
        return None, ["No approved MAGMOM profile is available."]
    groups = [f"{count}*{format_moment(defaults.get(symbol, 0.0))}" for symbol, count in zip(symbols, counts)]
    if record.get("warning"):
        warnings.append(str(record["warning"]))
    return " ".join(groups), warnings


def merge_generation_profile(
    calculation_type: str, family: str, material: str | None, images: int | None, project: dict[str, Any]
) -> tuple[dict[str, Any], list[str], bool]:
    profiles = read_yaml(SKILL_ROOT / "references" / "profiles.yaml")
    recommended = dict(profiles.get("global_defaults") or {})
    stage = dict((profiles.get("calculation_types") or {}).get(calculation_type) or {})
    warnings: list[str] = []
    requires_module_review = bool(stage.pop("requires_module_review", False))
    if requires_module_review:
        warnings.append(f"{calculation_type} settings require approval by the owning project module.")
    recommended.update(stage)
    family_record = (project.get("surface_families") or {}).get(family, {})
    for key in ("ISPIN", "ISMEAR", "SIGMA"):
        if key in family_record:
            recommended[key] = family_record[key]
    material_record = (project.get("materials") or {}).get(material or "", {})
    recommended.update(material_record.get("common") or {})
    recommended.update((material_record.get("calculation_types") or {}).get(calculation_type) or {})
    if "NEB" in calculation_type and images is not None:
        recommended["IMAGES"] = images
    return recommended, warnings, requires_module_review


def diagnostic_files(workdir: Path, explicit: list[Path]) -> list[Path]:
    paths = list(explicit)
    for name in DIAGNOSTIC_NAMES:
        candidate = workdir / name
        if candidate.is_file() and candidate not in paths:
            paths.append(candidate)
    return paths


def flatten_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in flatten_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in flatten_strings(child)]
    return [str(value)]


def inspect_blockers(paths: list[Path]) -> tuple[list[str], list[str]]:
    rules = read_yaml(SKILL_ROOT / "references" / "error_rules.yaml")
    failure_types = {value.lower() for value in rules.get("blocking_failure_types", [])}
    tokens = [value.lower() for value in rules.get("blocking_error_tokens", [])]
    blockers: list[str] = []
    warnings: list[str] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"Could not parse diagnostic {path}: {exc}")
            continue
        failure = str(payload.get("failure_type", "")).lower() if isinstance(payload, dict) else ""
        status = str(payload.get("status", "")).upper() if isinstance(payload, dict) else ""
        error_text = "\n".join(flatten_strings(payload.get("errors", []))).lower() if isinstance(payload, dict) else ""
        if failure in failure_types:
            blockers.append(f"{path.name}:failure_type={failure}")
        for token in tokens:
            if token in error_text:
                blockers.append(f"{path.name}:{token}")
        if path.name in {"endpoint_check.json", "path_geometry_diagnosis.json"} and status == "STOP":
            blockers.append(f"{path.name}:status=STOP")
    return sorted(set(blockers)), warnings


def parse_vasp_errors(workdir: Path) -> dict[str, Any]:
    rules = read_yaml(SKILL_ROOT / "references" / "error_rules.yaml")
    text_parts = []
    sources = []
    for name in ("OUTCAR", "OSZICAR", "vasp.out", "stderr", "stdout"):
        path = workdir / name
        if path.is_file():
            text_parts.append(path.read_text(encoding="utf-8", errors="replace"))
            sources.append(str(path))
    text = "\n".join(text_parts)
    findings = []
    for name, pattern in (rules.get("vasp_patterns") or {}).items():
        if re.search(str(pattern), text, re.IGNORECASE):
            findings.append(name)
    return {"sources": sources, "findings": findings, "has_output": bool(sources)}


def expand_magmom_count(value: Any) -> int | None:
    if isinstance(value, (list, tuple)):
        return len(value)
    if not isinstance(value, str):
        return None
    total = 0
    for token in value.split():
        total += int(token.split("*", 1)[0]) if "*" in token else 1
    return total


def validate_incar(
    incar: dict[str, Any], symbols: list[str], counts: list[int], calculation_type: str | None, family: str
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if "Fe" in symbols and int(incar.get("ISPIN", 1)) != 2:
        errors.append("Fe-based calculation must not disable spin polarization.")
    if "MAGMOM" in incar and counts:
        expanded = expand_magmom_count(incar["MAGMOM"])
        if expanded is not None and expanded != sum(counts):
            errors.append(f"MAGMOM expands to {expanded} entries but POSCAR has {sum(counts)} atoms.")
    if family == "iron_oxide":
        warnings.append("Oxide magnetic ordering and DFT+U require an approved project method.")
    if calculation_type in {"pre_NEB", "refine_NEB", "CI_NEB", "local_NEB"}:
        if int(incar.get("IBRION", -999)) != 3:
            errors.append("Project NEB profile requires IBRION=3.")
        if float(incar.get("POTIM", -1)) != 0:
            errors.append("Project NEB profile requires POTIM=0.")
        expected_climb = calculation_type == "CI_NEB"
        if bool(incar.get("LCLIMB", False)) != expected_climb and calculation_type != "local_NEB":
            errors.append(f"{calculation_type} has inconsistent LCLIMB.")
    if calculation_type in {"DIMER", "VFA"}:
        warnings.append("Algorithm-specific settings require review by the owning DIMER or TS-validation module.")
    return {"status": "PASS" if not errors else "STOP", "errors": errors, "warnings": warnings}


def differences(old: dict[str, Any], new: dict[str, Any], reasons: dict[str, str]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            changes[key] = {
                "old": old.get(key),
                "new": new.get(key),
                "reason": reasons.get(key, "Project profile or calculation-type recommendation."),
            }
    return changes


def tune(
    incar: dict[str, Any], failure_type: str | None, calculation_type: str, project_stage: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], str, list[str]]:
    recommended = dict(incar)
    reasons: dict[str, str] = {}
    warnings: list[str] = []
    next_action = "review_current_incar"
    failure = failure_type or "none"
    preferred_algo = project_stage.get("ALGO", "Normal")
    if failure in {"scf_failure", "brmix", "zheev", "subspace", "edddav"}:
        for key, value, reason in (
            ("ALGO", preferred_algo, "Electronic convergence recovery; project override has priority."),
            ("NELM", max(int(incar.get("NELM", 0)), 300), "Allow more electronic iterations."),
            ("EDIFF", 1.0e-5, "Use the project electronic threshold for recovery."),
            ("ISYM", 0, "Avoid symmetry conflicts in surface calculations."),
        ):
            recommended[key] = value
            reasons[key] = reason
        next_action = "restart_after_electronic_review"
    elif failure == "force_slow_decrease":
        target_nsw = max(int(incar.get("NSW", 0)), int(project_stage.get("NSW", 300)))
        recommended["NSW"] = target_nsw
        reasons["NSW"] = "Force is decreasing; extend only the ionic-step budget."
        next_action = "restart_from_CONTCAR"
    elif failure in {"force_plateau", "force_oscillation", "force_plateau_or_oscillation"}:
        recommended["NSW"] = max(int(incar.get("NSW", 0)), 300)
        reasons["NSW"] = "Provide a bounded restart window after geometry review."
        if calculation_type in {"pre_NEB", "refine_NEB", "CI_NEB", "local_NEB"}:
            recommended["LCLIMB"] = False
            reasons["LCLIMB"] = "Smooth the path without climbing while forces plateau or oscillate."
            recommended["MAXMOVE"] = min(float(incar.get("MAXMOVE", 0.1)), 0.1)
            reasons["MAXMOVE"] = "Limit optimizer displacement after a verified plateau/oscillation."
        next_action = "restart_after_path_review"
    elif failure == "too_few_bands":
        if "NBANDS" in incar:
            recommended["NBANDS"] = int(math.ceil(float(incar["NBANDS"]) * 1.15))
            reasons["NBANDS"] = "VASP reported insufficient bands; increase existing NBANDS by 15 percent."
            next_action = "restart_after_nbands_review"
        else:
            warnings.append("VASP reported too few bands, but no explicit NBANDS exists; user confirmation is required.")
    elif failure == "walltime":
        next_action = "restart_from_CONTCAR_without_broad_parameter_changes"
    elif failure != "none":
        warnings.append(f"No automatic rule is approved for failure type: {failure}")
    return recommended, reasons, next_action, warnings


def write_report(path: Path, payload: dict[str, Any]) -> None:
    changes = payload.get("changes", {})
    messages = read_yaml(SKILL_ROOT / "references" / "report_messages.yaml")
    rows = "\n".join(f"| {key} | `{item.get('old')}` | `{item.get('new')}` | {item.get('reason')} |" for key, item in changes.items())
    if not rows:
        rows = f"| none | - | - | {messages['no_change']} |"
    template = (SKILL_ROOT / "references" / "report_template_zh.md").read_text(encoding="utf-8")
    text = template.format(
        status=payload["status"],
        calculation_type=payload.get("calculation_type"),
        material=payload.get("material"),
        surface_family=payload.get("surface_family"),
        failure_type=payload.get("failure_type") or "none",
        fit_message=messages["fit_blocked"] if payload.get("blockers") else messages["fit_reviewable"],
        rows=rows,
        next_action=payload.get("next_action"),
        warnings="; ".join(payload.get("warnings", [])) or "none",
    )
    path.write_text(text, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely diagnose, generate, tune, or validate Fe-based VASP INCAR recommendations.")
    parser.add_argument("--mode", choices=("tune", "generate", "validate", "parse-errors", "custodian-plan"), default="tune")
    parser.add_argument("--workdir", type=Path, default=Path("."))
    parser.add_argument("--incar", type=Path)
    parser.add_argument("--poscar", type=Path)
    parser.add_argument("--calculation-type", choices=CALCULATION_TYPES)
    parser.add_argument("--surface-family", choices=("metal_fe", "iron_carbide", "iron_oxide", "unknown"))
    parser.add_argument("--material")
    parser.add_argument("--images", type=int)
    parser.add_argument("--diagnosis-json", type=Path, action="append", default=[])
    parser.add_argument("--failure-type")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--vasp-command", nargs="+")
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--read-only",
        action="store_true",
        help="Diagnose and print JSON without creating or modifying files.",
    )
    output_mode.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Explicitly persist the recommended INCAR and review artifacts.",
    )
    output_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Backward-compatible alias for --read-only.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def resolve_output_context(args: argparse.Namespace) -> tuple[Path, bool, bool]:
    workdir = args.workdir.resolve()
    write_artifacts = bool(args.write_artifacts)
    read_only = not write_artifacts
    if write_artifacts:
        workdir.mkdir(parents=True, exist_ok=True)
    elif not workdir.is_dir():
        raise SystemExit(f"Read-only workdir does not exist: {workdir}")
    return workdir, write_artifacts, read_only


def handle_diagnostic_mode(
    args: argparse.Namespace,
    workdir: Path,
    write_artifacts: bool,
    read_only: bool,
) -> bool:
    if args.mode == "parse-errors":
        payload = parse_vasp_errors(workdir)
        report_path = workdir / "vasp_error_report.json"
        payload.update(
            {
                "read_only": read_only,
                "artifacts_written": [str(report_path)] if write_artifacts else [],
            }
        )
        if write_artifacts:
            write_json(report_path, payload)
            print(report_path)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return True
    if args.mode != "custodian-plan":
        return False
    plan_path = workdir / "custodian_plan.json"
    payload = {
        "status": "READY_FOR_EXPLICIT_REVIEW" if args.vasp_command else "NEED_USER_CONFIRMATION",
        "custodian_installed": bool(importlib.util.find_spec("custodian")),
        "vasp_command": args.vasp_command,
        "executed": False,
        "warning": "This mode only records a plan. Runtime custodian execution requires a separate explicit request and cluster review.",
        "read_only": read_only,
        "artifacts_written": [str(plan_path)] if write_artifacts else [],
    }
    if write_artifacts:
        write_json(plan_path, payload)
        print(payload["status"])
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return True


def maybe_write_incar_candidate(
    incar_class: Any,
    recommended: dict[str, Any],
    output: Path,
    magmom_text: str | None,
    write_artifacts: bool,
    blockers: list[str],
    mode: str,
) -> bool:
    if not write_artifacts or blockers or mode not in {"generate", "tune"}:
        return False
    if output.exists():
        raise SystemExit(f"Candidate already exists and will not be overwritten: {output}")
    write_incar_candidate(incar_class, recommended, output, magmom_text)
    return True


def main() -> None:
    args = parse_args()
    workdir, write_artifacts, read_only = resolve_output_context(args)
    if handle_diagnostic_mode(args, workdir, write_artifacts, read_only):
        return
    if args.calculation_type is None:
        raise SystemExit("--calculation-type is required")
    if args.mode in {"tune", "validate"} and (args.incar is None or not args.incar.is_file()):
        raise SystemExit("--incar must point to an existing INCAR")
    if args.poscar is not None and not args.poscar.is_file():
        raise SystemExit(f"POSCAR not found: {args.poscar}")

    Incar, _ = require_pymatgen()
    project, project_path = load_project_profiles(workdir)
    symbols, counts = load_structure(args.poscar)
    family, warnings = detect_surface_family(symbols, args.surface_family, args.material, project)
    material_record = (project.get("materials") or {}).get(args.material or "", {})
    project_stage = dict(material_record.get("common") or {})
    project_stage.update((material_record.get("calculation_types") or {}).get(args.calculation_type) or {})
    existing = dict(Incar.from_file(args.incar)) if args.incar else {}
    blockers, diagnostic_warnings = inspect_blockers(diagnostic_files(workdir, args.diagnosis_json))
    warnings.extend(diagnostic_warnings)
    parsed_errors = parse_vasp_errors(workdir)
    failure = args.failure_type or (parsed_errors["findings"][0] if parsed_errors["findings"] else None)
    reasons: dict[str, str] = {}
    next_action = "review"
    magmom_text = raw_incar_value(args.incar, "MAGMOM")

    if blockers:
        recommended = dict(existing)
        status = "STOP_INCAR_TUNING_AND_REBUILD_PATH"
        next_action = "return_to_upstream_scientific_module"
    elif args.mode == "generate":
        recommended, profile_warnings, requires_module_review = merge_generation_profile(
            args.calculation_type, family, args.material, args.images, project
        )
        warnings.extend(profile_warnings)
        magmom, magmom_warnings = build_magmom(symbols, counts, family, project)
        warnings.extend(magmom_warnings)
        if magmom:
            recommended["MAGMOM"] = magmom
            magmom_text = magmom
        status = "INCAR_RECOMMENDED" if family != "unknown" and magmom and not requires_module_review else "NEED_USER_CONFIRMATION"
        next_action = "review_generated_incar"
    elif args.mode == "tune":
        recommended, reasons, next_action, tune_warnings = tune(existing, failure, args.calculation_type, project_stage)
        warnings.extend(tune_warnings)
        status = "INCAR_RECOMMENDED" if recommended != existing else "NO_INCAR_CHANGE_NEEDED"
    else:
        recommended = dict(existing)
        status = "VALIDATION_ONLY"

    validation = validate_incar(recommended, symbols, counts, args.calculation_type, family)
    warnings.extend(validation["warnings"])
    if validation["status"] == "STOP" and not blockers:
        status = "NEED_USER_CONFIRMATION"
    changes = differences(existing, recommended, reasons)
    output = (args.output or workdir / "INCAR.recommended").resolve()
    candidate_written = maybe_write_incar_candidate(
        Incar,
        recommended,
        output,
        magmom_text,
        write_artifacts,
        blockers,
        args.mode,
    )

    change_path = workdir / "incar_change.json"
    validation_path = workdir / "incar_validation.json"
    report_path = workdir / "incar_change_report.md"
    artifacts_written: list[str] = []
    if write_artifacts:
        if candidate_written:
            artifacts_written.append(str(output))
        artifacts_written.extend(
            (str(change_path), str(validation_path), str(report_path))
        )

    payload = {
        "status": status,
        "mode": args.mode,
        "calculation_type": args.calculation_type,
        "surface_family": family,
        "material": args.material or "Needs confirmation",
        "failure_type": failure,
        "source_incar": str(args.incar) if args.incar else None,
        "source_poscar": str(args.poscar) if args.poscar else None,
        "project_profile": str(project_path) if project_path else None,
        "candidate_output": str(output) if not blockers and args.mode in {"generate", "tune"} else None,
        "recommended_incar": str(output) if candidate_written else None,
        "changes": changes,
        "blockers": blockers,
        "warnings": sorted(set(warnings)),
        "next_action": next_action,
        "requires_user_confirmation": bool(
            status != "NO_INCAR_CHANGE_NEEDED" or blockers or validation["errors"] or family in {"unknown", "iron_oxide"}
        ),
        "dry_run": bool(args.dry_run),
        "read_only": read_only,
        "artifacts_written": artifacts_written,
        "vasp_executed": False,
    }
    if write_artifacts:
        write_json(change_path, payload)
        write_json(validation_path, validation)
        write_report(report_path, payload)
    if read_only or args.verbose:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(status)


if __name__ == "__main__":
    main()
