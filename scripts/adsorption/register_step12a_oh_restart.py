from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.registry_write import apply_registry_batch, plan_registry_batch
from scripts.artifact_io import sha256_file as sha256


ROOT = Path(__file__).resolve().parents[2]
CALC_ROOT = ROOT / "calculations" / "fe110_step12a_gas_references_20260828"
RESTART = CALC_ROOT / "restart" / "OH" / "relax"
PROVENANCE = CALC_ROOT / "provenance"
PREFLIGHT = PROVENANCE / "oh_restart_preflight.json"
DATABASE = ROOT / "data" / "project_registry.sqlite3"
CALCULATION_ID = "fe110_gas_OH_9733113"
ORIGINAL_JOB = "job_fe110_gas_OH_9733113"
RESTART_JOB = "job_fe110_gas_OH_9733121"
CREATED_AT = "2026-08-28T10:29:00Z"
REMOTE = "~/sbq/Fe110/gas/OH/relax_restart_20260828"




def build_batch() -> dict[str, Any]:
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if not preflight["passed"]:
        raise ValueError("OH restart preflight did not pass")
    rows: dict[str, list[dict[str, Any]]] = {
        "jobs": [
            {
                "job_record_id": RESTART_JOB,
                "calculation_id": CALCULATION_ID,
                "scheduler_job_id": "9733121",
                "scheduler": "LSF",
                "server_alias": "sunboquan-codex",
                "queue": "Gkn_normal",
                "remote_directory": REMOTE,
                "submit_script": "job.sh",
                "submitted_at": CREATED_AT,
            }
        ],
        "job_status_history": [
            {
                "job_record_id": ORIGINAL_JOB,
                "scheduler_status": "DONE",
                "scientific_status": "rejected_incomplete_authoritative_output",
                "checked_at": CREATED_AT,
                "source_command": "ssh sunboquan-codex bjobs -l 9733113 plus returned-file audit",
                "source_text": "Scheduler DONE successfully, but authoritative OUTCAR truncated during final ionic step.",
                "reviewer": "Codex",
                "notes": "vasp.out/OSZICAR reached the optimizer stop, but OUTCAR lacks final TOTEN/force/footer; reference energy is not accepted.",
            },
            {
                "job_record_id": RESTART_JOB,
                "scheduler_status": "RUN",
                "scientific_status": "Not assessed",
                "checked_at": CREATED_AT,
                "source_command": "ssh sunboquan-codex bjobs 9733121",
                "source_text": "Job <9733121> RUN in Gkn_normal.",
                "reviewer": "Codex",
                "notes": "Same-method continuation from the final CONTCAR; no INCAR parameter change.",
            },
        ],
        "files": [],
        "reviews": [
            {
                "review_id": "review_fe110_gas_OH_9733113_incomplete_outcar_restart",
                "calculation_id": CALCULATION_ID,
                "review_type": "gas_reference_incomplete_output_recovery",
                "decision": "REJECT_ENERGY_AND_RESTART",
                "reviewer": "Codex",
                "reviewed_at": CREATED_AT,
                "evidence": json.dumps(
                    {
                        "original_job": "9733113",
                        "restart_job": "9733121",
                        "original_scheduler_status": "DONE",
                        "outcar_normal_footer": False,
                        "outcar_final_step_complete": False,
                        "restart_preflight_sha256": sha256(PREFLIGHT),
                        "remote_input_hashes_match": True,
                    },
                    sort_keys=True,
                ),
                "reason": "Scheduler success did not supply an acceptance-eligible final OUTCAR; a same-method continuation from CONTCAR was required.",
            }
        ],
    }
    for filename, role in (
        ("POSCAR", "restart_structure"),
        ("INCAR", "vasp_input"),
        ("KPOINTS", "kpoint_input"),
        ("POTCAR.spec", "potcar_metadata"),
        ("job.sh", "submission_script"),
    ):
        path = RESTART / filename
        stat = path.stat()
        rows["files"].append(
            {
                "file_id": f"file_{CALCULATION_ID}_restart_9733121_{filename.replace('.', '_')}",
                "calculation_id": CALCULATION_ID,
                "job_record_id": RESTART_JOB,
                "role": role,
                "filename": filename,
                "local_path": str(path.resolve()),
                "remote_path": f"{REMOTE}/{filename}",
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
            "file_id": f"file_{CALCULATION_ID}_restart_9733121_POTCAR",
            "calculation_id": CALCULATION_ID,
            "job_record_id": RESTART_JOB,
            "role": "licensed_runtime_input",
            "filename": "POTCAR",
            "remote_path": f"{REMOTE}/POTCAR.link",
            "storage_mode": "external_path_reference",
            "sha256": "52903520fd107a2a9d75ca9368f690537cdc0294bf7c59d8be552e936fdb6147",
            "existence_status": "confirmed",
            "license_or_sensitivity": "licensed_vasp_potential_no_local_copy",
        }
    )
    return {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fe110-step12a-oh-reference-restart-20260828",
        "created_at": CREATED_AT,
        "reviewer": "User-authorized Codex gas-reference workflow",
        "reason": "Record the rejected incomplete OH output and same-method continuation submission.",
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--confirm-sha256")
    args = parser.parse_args()
    batch = build_batch()
    (PROVENANCE / "oh_restart_registry_batch.json").write_text(
        json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if args.command == "plan":
        result = plan_registry_batch(DATABASE, batch)
        output = PROVENANCE / "oh_restart_registry_plan.json"
    else:
        if not args.confirm_sha256:
            raise ValueError("apply requires --confirm-sha256")
        result = apply_registry_batch(DATABASE, batch, confirmed_sha256=args.confirm_sha256)
        output = PROVENANCE / "oh_restart_registry_receipt.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
