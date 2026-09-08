from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.artifact_io import sha256_json
from scripts.registry_write import apply_registry_batch, plan_registry_batch
from scripts.artifact_io import sha256_file as sha256


ROOT = Path(__file__).resolve().parents[2]
CALC_ROOT = ROOT / "calculations" / "fe110_step12a_gas_references_20260828"
INPUT_ROOT = CALC_ROOT / "inputs"
PROVENANCE = CALC_ROOT / "provenance"
MANIFEST = PROVENANCE / "submission_manifest.json"
PREFLIGHT = PROVENANCE / "input_preflight.json"
DATABASE = ROOT / "data" / "project_registry.sqlite3"
LOCAL_FILENAMES = ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "job.sh")
FILE_ROLES = {
    "POSCAR": "initial_structure",
    "INCAR": "vasp_input",
    "KPOINTS": "kpoint_input",
    "POTCAR.spec": "potcar_metadata",
    "job.sh": "submission_script",
}




def build_batch() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if not manifest["input_hashes_match"] or not preflight["passed"]:
        raise ValueError("gas-reference input handoff is not fully verified")
    rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "calculations",
            "jobs",
            "job_status_history",
            "files",
            "reviews",
            "calculation_compatibility",
        )
    }
    for job in manifest["jobs"]:
        species = job["species"]
        job_id = job["scheduler_job_id"]
        calculation_id = f"fe110_gas_{species}_{job_id}"
        job_record_id = f"job_fe110_gas_{species}_{job_id}"
        local = INPUT_ROOT / species / "relax"
        rows["calculations"].append(
            {
                "calculation_id": calculation_id,
                "module": "adsorption_workflow",
                "purpose": f"Compatible isolated {species} reference for Fe(110) Step 12A adsorption energies",
                "scientific_system": f"isolated_{species}_20A_gamma",
                "workflow_status": "submitted_pending",
                "created_at": manifest["submitted_at"],
                "source_record": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
                "notes": "Reference energy is not accepted until normal termination, convergence, spin, and geometry review pass.",
            }
        )
        rows["jobs"].append(
            {
                "job_record_id": job_record_id,
                "calculation_id": calculation_id,
                "scheduler_job_id": job_id,
                "scheduler": manifest["scheduler"],
                "server_alias": manifest["server_alias"],
                "queue": manifest["queue"],
                "remote_directory": job["remote_directory"],
                "submit_script": "job.sh",
                "submitted_at": manifest["submitted_at"],
            }
        )
        rows["job_status_history"].append(
            {
                "job_record_id": job_record_id,
                "scheduler_status": "PEND",
                "scientific_status": "Not assessed",
                "checked_at": manifest["submitted_at"],
                "source_command": f"ssh sunboquan-codex bjobs {job_id}",
                "source_text": f"Job <{job_id}> submitted to queue <{manifest['queue']}>.",
                "reviewer": "Codex",
                "notes": "Submission state only; calculation and reference validity are not assessed.",
            }
        )
        for filename in LOCAL_FILENAMES:
            path = local / filename
            stat = path.stat()
            rows["files"].append(
                {
                    "file_id": f"file_{calculation_id}_{filename.replace('.', '_')}",
                    "calculation_id": calculation_id,
                    "job_record_id": job_record_id,
                    "role": FILE_ROLES[filename],
                    "filename": filename,
                    "local_path": str(path.resolve()),
                    "remote_path": f"{job['remote_directory']}/{filename}",
                    "storage_mode": "repository",
                    "byte_size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "sha256": sha256(path),
                    "existence_status": "confirmed",
                    "license_or_sensitivity": "project_internal",
                }
            )
        rows["files"].append(
            {
                "file_id": f"file_{calculation_id}_POTCAR",
                "calculation_id": calculation_id,
                "job_record_id": job_record_id,
                "role": "licensed_runtime_input",
                "filename": "POTCAR",
                "remote_path": f"{job['remote_directory']}/POTCAR.link",
                "storage_mode": "external_path_reference",
                "sha256": job["potcar_sha256"],
                "existence_status": "confirmed",
                "license_or_sensitivity": "licensed_vasp_potential_no_local_copy",
            }
        )
        incar = {
            line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
            for line in (local / "INCAR").read_text(encoding="ascii").splitlines()
            if "=" in line
        }
        compatibility = {
            "code": "VASP 5.4.1",
            "xc": incar["GGA"],
            "encut_eV": float(incar["ENCUT"]),
            "ediff_eV": float(incar["EDIFF"]),
            "ediffg_eV_A": float(incar["EDIFFG"]),
            "ispin": int(incar["ISPIN"]),
            "magmom": incar.get("MAGMOM"),
            "nupdown": int(incar["NUPDOWN"]) if "NUPDOWN" in incar else None,
            "ismear": int(incar["ISMEAR"]),
            "sigma_eV": float(incar["SIGMA"]),
            "cell_A": [20.0, 20.0, 20.0],
            "kmesh": [1, 1, 1],
            "potcar_sha256": job["potcar_sha256"],
            "reference_convention": "fe110_gas_pbe_20A_gamma_species_spin_v1",
        }
        compatibility_json = json.dumps(compatibility, sort_keys=True, separators=(",", ":"))
        rows["calculation_compatibility"].append(
            {
                "calculation_id": calculation_id,
                "compatibility_fingerprint": hashlib.sha256(compatibility_json.encode()).hexdigest(),
                "compatibility_json": compatibility_json,
                "reviewer": "Codex",
                "reviewed_at": manifest["submitted_at"],
            }
        )
        rows["reviews"].append(
            {
                "review_id": f"review_{calculation_id}_input_preflight",
                "calculation_id": calculation_id,
                "review_type": "gas_reference_input_preflight",
                "decision": "PASS",
                "reviewer": "Codex",
                "reviewed_at": manifest["submitted_at"],
                "evidence": json.dumps(
                    {
                        "preflight_sha256": sha256(PREFLIGHT),
                        "manifest_sha256": sha256(MANIFEST),
                        "remote_input_hashes_match": True,
                    },
                    sort_keys=True,
                ),
                "reason": "Locked PBE/PAW-PBE/ENCUT/Gamma/20 A gas-reference method, species spin, POTCAR order, and remote input hashes passed.",
            }
        )
    return {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fe110-step12a-gas-reference-submission-20260828",
        "created_at": manifest["submitted_at"],
        "reviewer": "User-authorized Codex gas-reference workflow",
        "reason": "Register the five missing Step 12A gas-reference submissions and their verified inputs.",
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan or apply the Step 12A gas-reference submission batch.")
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--confirm-sha256")
    args = parser.parse_args()
    batch = build_batch()
    batch_path = PROVENANCE / "registry_submission_batch.json"
    batch_path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.command == "plan":
        result = plan_registry_batch(DATABASE, batch)
        output = PROVENANCE / "registry_submission_plan.json"
    else:
        if not args.confirm_sha256:
            raise ValueError("apply requires --confirm-sha256")
        result = apply_registry_batch(DATABASE, batch, confirmed_sha256=args.confirm_sha256)
        output = PROVENANCE / "registry_submission_receipt.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({**result, "manifest_sha256": sha256_json(batch)}, indent=2))


if __name__ == "__main__":
    main()
