from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.adsmind_lite.audit_remote_fe110_batch import audit_structure, fetch_structures
from scripts.artifact_io import sha256_json
from scripts.execution_backends import load_execution_backends


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "calculations" / "fe110_step12a_registry_backfill_20260828" / "provenance"
ADSORBATES = ("CO", "H", "O", "OH", "H2O", "C")
SITES = ("top", "short_bridge", "long_bridge", "hollow")
SKIP_EXISTING = {("CO", "top")}
FINAL_SPECIES = {"CO": "CO*", "H": "H*", "O": "O*", "OH": "OH*", "H2O": "H2O*", "C": "C*"}
FILE_ROLES = {
    "POSCAR": "input_structure",
    "CONTCAR": "final_structure",
    "INCAR": "input_parameters",
    "KPOINTS": "kpoint_mesh",
    "POTCAR.link": "licensed_pseudopotential_reference",
    "job.sh": "submission_script",
    "OUTCAR": "vasp_output",
    "OSZICAR": "ionic_electronic_history",
    "vasp.out": "scheduler_stdout",
}


REMOTE_AUDIT_SCRIPT = r'''
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

adsorbates = ("CO", "H", "O", "OH", "H2O", "C")
sites = ("top", "short_bridge", "long_bridge", "hollow")
files = ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "POTCAR.link", "job.sh", "OUTCAR", "OSZICAR", "vasp.out")
fatal_markers = ("VERY BAD NEWS", "BRMIX: very serious problems", "ZBRENT: fatal error", "ERROR FEXCF")
toten_re = re.compile(r"free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)\s+eV")

root_arg = sys.argv[1]
root = Path.home() / root_arg[2:] if root_arg.startswith("~/") else Path(root_arg)

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

def metadata(path):
    stat = path.stat()
    return {
        "byte_size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "sha256": sha256(path),
        "is_symlink": path.is_symlink(),
        "resolved_path": str(path.resolve()) if path.is_symlink() else None,
    }

def incar_values(path):
    values = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("!", 1)[0].split("#", 1)[0]
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()
    return values

def movable_indices(path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    counts = [int(value) for value in lines[6].split()]
    count = sum(counts)
    index = 7
    selective = lines[index].lower().startswith("s")
    if selective:
        index += 1
    index += 1
    result = []
    for atom_index, line in enumerate(lines[index:index + count]):
        fields = line.split()
        if not selective or (len(fields) >= 6 and all(flag.upper() == "T" for flag in fields[3:6])):
            result.append(atom_index)
    return result

def parse_oszicar(path, nelm):
    ionic_steps = 0
    current_iteration = None
    current_delta_e = None
    final_iteration = None
    final_delta_e = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            fields = raw.split()
            if fields and fields[0] in {"DAV:", "RMM:", "CGA:"} and len(fields) >= 4:
                try:
                    current_iteration = int(fields[1])
                    current_delta_e = float(fields[3])
                except ValueError:
                    continue
            elif " F=" in raw and current_iteration is not None:
                ionic_steps += 1
                final_iteration = current_iteration
                final_delta_e = current_delta_e
                current_iteration = None
                current_delta_e = None
    return {
        "ionic_steps": ionic_steps,
        "last_electronic_iteration": final_iteration,
        "last_electronic_delta_e_eV": final_delta_e,
        "electronic_iterations_below_nelm": final_iteration is not None and final_iteration < nelm,
    }

def parse_outcar(path, movable):
    last_toten = None
    reached_accuracy = False
    normal_completion = False
    ediff_reached = False
    fatal = []
    collecting = False
    current_forces = []
    last_forces = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            match = toten_re.search(raw)
            if match:
                last_toten = float(match.group(1))
            if "reached required accuracy - stopping structural energy minimisation" in raw:
                reached_accuracy = True
            if "General timing and accounting informations for this job" in raw:
                normal_completion = True
            if "aborting loop because EDIFF is reached" in raw:
                ediff_reached = True
            for marker in fatal_markers:
                if marker in raw and marker not in fatal:
                    fatal.append(marker)
            if "TOTAL-FORCE (eV/Angst)" in raw:
                collecting = True
                current_forces = []
                continue
            if collecting:
                fields = raw.split()
                if len(fields) >= 6:
                    try:
                        current_forces.append(tuple(float(value) for value in fields[-3:]))
                        continue
                    except ValueError:
                        pass
                if current_forces:
                    last_forces = current_forces
                    collecting = False
    if collecting and current_forces:
        last_forces = current_forces
    maximum = None
    maximum_index = None
    for index in movable:
        if index >= len(last_forces):
            continue
        force = last_forces[index]
        norm = math.sqrt(sum(value * value for value in force))
        if maximum is None or norm > maximum:
            maximum = norm
            maximum_index = index
    return {
        "final_toten_eV": last_toten,
        "reached_required_accuracy": reached_accuracy,
        "normal_completion": normal_completion,
        "outcar_ediff_reached": ediff_reached,
        "fatal_markers": fatal,
        "final_max_movable_force_eV_A": maximum,
        "final_max_movable_force_zero_based_index": maximum_index,
    }

records = []
for adsorbate in adsorbates:
    for site in sites:
        directory = root / adsorbate / site
        missing = [name for name in files if not (directory / name).exists()]
        if missing:
            raise SystemExit(f"{adsorbate}/{site}: missing files: {', '.join(missing)}")
        incar = incar_values(directory / "INCAR")
        nelm = int(float(incar["NELM"]))
        ediffg = float(incar["EDIFFG"])
        movable = movable_indices(directory / "POSCAR")
        oszicar = parse_oszicar(directory / "OSZICAR", nelm)
        outcar = parse_outcar(directory / "OUTCAR", movable)
        k_lines = [line.split("!", 1)[0].strip() for line in (directory / "KPOINTS").read_text().splitlines()]
        kmesh = [int(value) for value in k_lines[3].split()[:3]]
        electronic = bool(outcar["outcar_ediff_reached"] or oszicar["electronic_iterations_below_nelm"])
        force_pass = outcar["final_max_movable_force_eV_A"] is not None and outcar["final_max_movable_force_eV_A"] <= abs(ediffg) + 1e-8
        technical = bool(
            electronic
            and outcar["reached_required_accuracy"]
            and outcar["normal_completion"]
            and force_pass
            and not outcar["fatal_markers"]
        )
        records.append({
            "adsorbate": adsorbate,
            "planned_site": site,
            "remote_directory": f"{root_arg.rstrip('/')}/{adsorbate}/{site}",
            "incar": incar,
            "kmesh": kmesh,
            "movable_atom_count": len(movable),
            "electronic_converged": electronic,
            "force_converged": force_pass,
            "technical_acceptance": technical,
            "oszicar": oszicar,
            "outcar": outcar,
            "files": {name: metadata(directory / name) for name in files},
        })
print(json.dumps(records, ensure_ascii=False, separators=(",", ":")))
'''


def parse_args() -> argparse.Namespace:
    backend = load_execution_backends().vasp
    parser = argparse.ArgumentParser(
        description="Build a reviewed Step 12A registry backfill batch from compact remote evidence."
    )
    parser.add_argument("--host", default=backend.server_alias)
    parser.add_argument("--remote-root", default="~/sbq/Fe110/adsorption/step12A")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--created-at")
    return parser.parse_args()


def remote_evidence(host: str, remote_root: str) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, "python3", "-", remote_root],
        input=REMOTE_AUDIT_SCRIPT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or len(payload) != len(ADSORBATES) * len(SITES):
        raise ValueError("remote Step 12A audit returned an incomplete record set")
    return payload


def duplicate_role(adsorbate: str, planned_site: str, final_site: str) -> tuple[str, str]:
    if adsorbate == "CO" and planned_site == "hollow" and final_site == "long_bridge":
        return "step12a_CO_long_bridge", "duplicate_of_step12a_CO_long_bridge"
    if adsorbate == "CO" and planned_site == "long_bridge":
        return "step12a_CO_long_bridge", "representative"
    if adsorbate == "H2O" and final_site == "top":
        return "step12a_H2O_top", "representative" if planned_site == "top" else "duplicate_of_step12a_H2O_top"
    if adsorbate == "C" and planned_site == "hollow" and final_site == "long_bridge":
        return "step12a_C_long_bridge", "duplicate_of_step12a_C_long_bridge"
    if adsorbate == "C" and planned_site == "long_bridge":
        return "step12a_C_long_bridge", "representative"
    return "none", "unique"


def validate_record(record: dict[str, Any], geometry: dict[str, Any]) -> None:
    if not record["technical_acceptance"]:
        raise ValueError(f"{record['adsorbate']}/{record['planned_site']}: technical gate failed")
    incar = record["incar"]
    expected = {"GGA": "PE", "ENCUT": "400", "ISMEAR": "1", "SIGMA": "0.20", "ISPIN": "2"}
    for key, value in expected.items():
        if incar.get(key) != value:
            raise ValueError(f"{record['adsorbate']}/{record['planned_site']}: incompatible {key}")
    if record["kmesh"] != [5, 5, 1]:
        raise ValueError(f"{record['adsorbate']}/{record['planned_site']}: incompatible KPOINTS")
    if geometry["overlap"]:
        raise ValueError(f"{record['adsorbate']}/{record['planned_site']}: geometry overlap")
    adsorbate = record["adsorbate"]
    if adsorbate == "CO" and not 1.0 <= geometry["co_angstrom"] <= 1.4:
        raise ValueError(f"{adsorbate}/{record['planned_site']}: invalid C-O bond")
    if adsorbate == "OH" and not 0.8 <= geometry["oh_angstrom"] <= 1.2:
        raise ValueError(f"{adsorbate}/{record['planned_site']}: invalid O-H bond")
    if adsorbate == "H2O":
        if any(not 0.8 <= value <= 1.2 for value in geometry["oh_angstrom"]):
            raise ValueError(f"{adsorbate}/{record['planned_site']}: invalid O-H bond")
        if not 90.0 <= geometry["hoh_degree"] <= 120.0:
            raise ValueError(f"{adsorbate}/{record['planned_site']}: invalid H-O-H angle")


def result_row(
    calculation_id: str,
    suffix: str,
    name: str,
    created_at: str,
    *,
    numeric: float | int | None = None,
    text: str | None = None,
    unit: str | None = None,
    source_file_id: str | None = None,
    validation_status: str = "verified",
    reference_convention: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "result_id": f"{calculation_id}-{suffix}",
        "calculation_id": calculation_id,
        "result_name": name,
        "validation_status": validation_status,
        "created_at": created_at,
    }
    if numeric is not None:
        row["numeric_value"] = numeric
    if text is not None:
        row["text_value"] = text
    if unit is not None:
        row["unit"] = unit
    if source_file_id is not None:
        row["source_file_id"] = source_file_id
    if reference_convention is not None:
        row["reference_convention"] = reference_convention
    if notes is not None:
        row["notes"] = notes
    return row


def build_batch(records: list[dict[str, Any]], structures: dict[str, str], created_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    reviewer = "User-authorized Codex registry backfill"
    rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "calculations",
            "jobs",
            "job_status_history",
            "files",
            "results",
            "reviews",
            "calculation_compatibility",
        )
    }
    reviewed: list[dict[str, Any]] = []
    for record in records:
        adsorbate = record["adsorbate"]
        site = record["planned_site"]
        poscar_path = f"{adsorbate}/{site}/POSCAR"
        contcar_path = f"{adsorbate}/{site}/CONTCAR"
        geometry = audit_structure(
            structures[contcar_path],
            contcar_path,
            adsorbate,
            site,
            structures[poscar_path],
        )
        validate_record(record, geometry)
        if (adsorbate, site) in SKIP_EXISTING:
            reviewed.append({**record, "geometry": geometry, "registry_action": "existing_record"})
            continue
        slug = adsorbate.lower()
        calculation_id = f"fe110_ads_step12a_{slug}_{site}_historical_20260828"
        job_record_id = f"lsf_step12a_{slug}_{site}_historical"
        duplicate_group, role = duplicate_role(adsorbate, site, geometry["classified_site"])
        is_duplicate = role.startswith("duplicate_of_")
        workflow_status = "recorded_duplicate_relaxation" if is_duplicate else "energy_accepted"
        rows["calculations"].append(
            {
                "calculation_id": calculation_id,
                "module": "adsorption_workflow",
                "purpose": f"Historical Step 12A Fe(110) {adsorbate} adsorption relaxation from {site}",
                "scientific_system": "true_fe110_5layer_5x5x1",
                "workflow_status": workflow_status,
                "created_at": record["files"]["POSCAR"]["modified_at"],
                "source_record": "Remote Step 12A VASP files audited on 2026-08-28",
                "notes": "Scheduler job ID is unavailable from expired LSF history; scheduler state is not inferred.",
            }
        )
        rows["jobs"].append(
            {
                "job_record_id": job_record_id,
                "calculation_id": calculation_id,
                "scheduler": "LSF",
                "server_alias": "sunboquan-codex",
                "remote_directory": record["remote_directory"],
                "submit_script": "job.sh",
                "finished_at": record["files"]["OUTCAR"]["modified_at"],
            }
        )
        rows["job_status_history"].append(
            {
                "job_record_id": job_record_id,
                "scheduler_status": "UNKNOWN",
                "scientific_status": (
                    "electronically_converged_ionically_converged_duplicate_geometry"
                    if is_duplicate
                    else "accepted_compatible_final_energy_reference_tuple_incomplete"
                ),
                "checked_at": created_at,
                "source_command": "python -m scripts.adsorption.backfill_step12a_registry",
                "reviewer": reviewer,
                "notes": "LSF history expired; scientific status comes from final OUTCAR/OSZICAR and geometry audit.",
            }
        )
        for filename, file_metadata in record["files"].items():
            file_id = f"{calculation_id}-{filename.lower().replace('.', '_')}"
            file_row: dict[str, Any] = {
                "file_id": file_id,
                "calculation_id": calculation_id,
                "job_record_id": job_record_id,
                "role": FILE_ROLES[filename],
                "filename": filename,
                "remote_path": f"{record['remote_directory']}/{filename}",
                "storage_mode": "remote_symlink" if file_metadata["is_symlink"] else "remote_only",
                "byte_size": file_metadata["byte_size"],
                "modified_at": file_metadata["modified_at"],
                "sha256": file_metadata["sha256"],
                "existence_status": "confirmed",
            }
            if filename == "POTCAR.link":
                file_row["license_or_sensitivity"] = "licensed_potcar_no_copy"
                file_row["notes"] = "Hash follows the remote symlink target; POTCAR content was not copied."
            rows["files"].append(file_row)
        outcar_id = f"{calculation_id}-outcar"
        geometry_text = (
            f"{FINAL_SPECIES[adsorbate]} final anchor site={geometry['classified_site']}; "
            f"lateral offset={geometry['lateral_offset_angstrom']:.4f} A; "
            f"minimum Fe-adsorbate contact={geometry['minimum_fe_adsorbate_angstrom']:.4f} A"
        )
        energy_status = "duplicate_provenance_only" if is_duplicate else "accepted_compatible_final_energy"
        result_specs = [
            ("final-species", "final_species", None, FINAL_SPECIES[adsorbate], None, "reviewed"),
            ("initial-site", "initial_site_class", None, geometry["initial_site"] if "initial_site" in geometry else site, None, "verified"),
            ("final-site", "final_site", None, geometry["classified_site"], None, "reviewed"),
            ("chemical-event", "chemical_event", None, "site_migration" if geometry["classified_site"] != site else "none", None, "reviewed"),
            ("plausibility", "plausibility_status", None, "PASS", None, "reviewed"),
            ("duplicate-group", "duplicate_group", None, duplicate_group, None, "reviewed"),
            ("duplicate-role", "duplicate_role", None, role, None, "reviewed"),
            ("promotion", "dataset_promotion_status", None, "duplicate" if is_duplicate else "reference_tuple_incomplete", None, "reviewed_gate_result"),
            ("compatibility-gate", "compatibility_gate_status", None, "DUPLICATE" if is_duplicate else "BLOCKED_REFERENCE_TUPLE_INCOMPLETE", None, "reviewed_gate_result"),
            ("electronic", "electronic_convergence", None, "converged", None, "verified"),
            ("ionic", "ionic_convergence", None, "converged", None, "verified"),
            ("normal-completion", "normal_completion", None, "true", None, "verified"),
            ("ionic-steps", "ionic_steps", record["oszicar"]["ionic_steps"], None, "step", "verified"),
            ("final-toten", "final_toten", record["outcar"]["final_toten_eV"], None, "eV", energy_status),
            ("final-max-movable-force", "final_max_movable_force", record["outcar"]["final_max_movable_force_eV_A"], None, "eV/A", "verified"),
            ("geometry-summary", "geometry_summary", None, geometry_text, None, "reviewed"),
            ("encut", "ENCUT_eV", float(record["incar"]["ENCUT"]), None, "eV", "verified"),
            ("ismear", "ISMEAR", float(record["incar"]["ISMEAR"]), None, None, "verified"),
            ("sigma", "SIGMA_eV", float(record["incar"]["SIGMA"]), None, "eV", "verified"),
            ("gga", "GGA", None, record["incar"]["GGA"], None, "verified"),
        ]
        for suffix, name, numeric, text, unit, validation in result_specs:
            rows["results"].append(
                result_row(
                    calculation_id,
                    suffix,
                    name,
                    created_at,
                    numeric=numeric,
                    text=text,
                    unit=unit,
                    source_file_id=outcar_id if name in {"final_toten", "final_max_movable_force", "normal_completion"} else None,
                    validation_status=validation,
                    reference_convention=(
                        "fe110_converged_toten_sigma0p20_v1" if name == "final_toten" else "true_fe110_5layer_5x5x1_step12a"
                    ),
                )
            )
        compatibility = {
            "branch": "true_fe110_5layer_5x5x1",
            "coverage": f"3x3_single_{slug}",
            "encut_ev": 400.0,
            "final_energy_convention": "fe110_converged_toten_sigma0p20_v1",
            "fixed_atom_indices_zero_based": list(range(18)),
            "ismear": 1,
            "kmesh": [5, 5, 1],
            "ldipol": False,
            "magnetic_state": "ispin2_recorded_incar_magmom",
            "material": "fe",
            "potcar_family": "paw_pbe",
            "sigma_ev": 0.2,
            "slab_model": "fe45_bottom18_fixed",
            "surface": "fe110",
            "vacuum_thickness_angstrom": 15.0,
            "xc": "pbe",
        }
        rows["calculation_compatibility"].append(
            {
                "calculation_id": calculation_id,
                "compatibility_fingerprint": sha256_json(compatibility),
                "compatibility_json": json.dumps(compatibility, sort_keys=True, separators=(",", ":")),
                "reviewer": reviewer,
                "reviewed_at": created_at,
            }
        )
        rows["reviews"].append(
            {
                "review_id": f"{calculation_id}-completion-review",
                "calculation_id": calculation_id,
                "review_type": "adsorption_completion_and_geometry",
                "decision": "duplicate" if is_duplicate else "accepted_final_energy_reference_incomplete",
                "reviewer": reviewer,
                "reviewed_at": created_at,
                "evidence": "Remote OUTCAR/OSZICAR/CONTCAR hashes and compact Step 12A audit",
                "reason": (
                    "Technically converged duplicate final site retained as provenance."
                    if is_duplicate
                    else "Normal completion, electronic and ionic convergence, compatible method, and accepted final geometry; adsorption reference tuple remains incomplete."
                ),
            }
        )
        reviewed.append({**record, "geometry": geometry, "registry_action": workflow_status})
    status_changes = [
        {
            "status_change_id": "status-fe110-ch-h-to-ch2-vfa-9710404-energy-accepted-20260828",
            "calculation_id": "fe110_ts_ch_h_to_ch2_vfa_9710404",
            "expected_workflow_status": "ts_accepted_grade_a_no_barrier",
            "new_workflow_status": "energy_accepted",
            "changed_at": created_at,
            "reviewer": reviewer,
            "reason": "Grade-A validation and accepted formal barrier already exist in the registry.",
        },
        {
            "status_change_id": "status-fe110-c-h-to-ch-dimer-9720181-energy-accepted-20260828",
            "calculation_id": "fe110_c_h_to_ch_dimer_9720181",
            "expected_workflow_status": "submitted_pending_dimer",
            "new_workflow_status": "energy_accepted",
            "changed_at": created_at,
            "reviewer": reviewer,
            "reason": "Accepted compatible TS energy, Grade-A validation, and accepted formal barrier already exist in the registry.",
        },
        {
            "status_change_id": "status-fe110-c-h-to-ch-vfa-9721851-energy-accepted-20260828",
            "calculation_id": "fe110_c_h_to_ch_vfa_9721851",
            "expected_workflow_status": "submitted_pending_vfa",
            "new_workflow_status": "energy_accepted",
            "changed_at": created_at,
            "reviewer": reviewer,
            "reason": "Grade-A validation and accepted formal barrier already exist in the registry.",
        },
    ]
    batch = {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fe110-step12a-backfill-and-ts-status-correction-20260828",
        "created_at": created_at,
        "reviewer": reviewer,
        "reason": "User-authorized Step 12A historical backfill and correction of stale accepted-TS workflow projections.",
        "rows": rows,
        "workflow_status_changes": status_changes,
    }
    audit = {
        "schema_version": 1,
        "created_at": created_at,
        "remote_record_count": len(records),
        "new_calculation_count": len(rows["calculations"]),
        "technical_acceptance_count": sum(bool(item["technical_acceptance"]) for item in records),
        "status_change_count": len(status_changes),
        "records": reviewed,
    }
    return batch, audit


def main() -> None:
    args = parse_args()
    created_at = args.created_at or datetime.now(timezone.utc).isoformat()
    records = remote_evidence(args.host, args.remote_root)
    structures = fetch_structures(args.host, args.remote_root)
    batch, audit = build_batch(records, structures, created_at)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "step12a_remote_audit.json"
    batch_path = args.output_dir / "registry_batch.json"
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    batch_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    summary = {
        "audit_path": str(audit_path),
        "batch_path": str(batch_path),
        "remote_records": audit["remote_record_count"],
        "new_calculations": audit["new_calculation_count"],
        "status_changes": audit["status_change_count"],
        "batch_sha256": sha256_json(batch),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
