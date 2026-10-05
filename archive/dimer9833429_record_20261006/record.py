"""Record a completed search candidate, without accepting a TS or launching jobs."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import shutil
import subprocess

from scripts.artifact_io import load_json_object, sha256_file, write_json, write_json_exclusive
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch, apply_registry_batch
from scripts.registry_transactions import approve_plan

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(__file__).resolve().parent
DB = ROOT / "data/project_registry.sqlite3"
RUN = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004"
SNAPSHOT = Path("C:/Users/86177/AppData/Local/Temp/dimer9833429-status-211c34d123354ea4bb5e8c18a5cd0eab")
REMOTE = "/home_gkn/users/nsgkn_chengdj3/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + RUN.name
CALC = "fe110_is_a_int06_dimer_9833429"
JOB = "job_fe110_is_a_int06_dimer_9833429"
REVIEWER = "Codex under explicit user completion-record request; no TS acceptance"
OUTPUTS = ("OUTCAR", "OSZICAR", "DIMCAR", "CONTCAR", "NEWMODECAR")


def prepare():
    if (RECORD / "registry_batch.json").exists():
        raise FileExistsError("Batch exists; review or resume instead of regenerating")
    remote = subprocess.run(["ssh", "sunboquan-codex", f"cd {REMOTE} && sha256sum " + " ".join(OUTPUTS)],
                            capture_output=True, text=True, check=True, timeout=45)
    hashes = {line.split()[1]: line.split()[0] for line in remote.stdout.splitlines()}
    if set(hashes) != set(OUTPUTS):
        raise ValueError("Incomplete remote output hashes")
    for name in OUTPUTS:
        if sha256_file(SNAPSHOT / name) != hashes[name]:
            raise ValueError("Saved snapshot differs from final remote output: " + name)
        target = RUN / name
        if target.exists():
            if sha256_file(target) != hashes[name]:
                raise ValueError("Do not overwrite an existing different output")
        else:
            shutil.copyfile(SNAPSHOT / name, target)
    write_json(RECORD / "final_output_identity.json", {"server_alias": "sunboquan-codex", "remote_dir": REMOTE,
               "source_command": remote.args, "stdout": remote.stdout, "returncode": remote.returncode, "sha256": hashes})
    scheduler = query_lsf_job("9833429", stage="dimer")
    if scheduler["status"] != "DONE":
        raise ValueError("Scheduler is not DONE")
    write_json(RUN / "scheduler_evidence.json", scheduler)
    analysis = analyze_dimer(RUN)
    if not (analysis["normal_completion"] and analysis["vasp_force_converged"] and analysis["negative_curvature"]
            and analysis["evidence_gate"]["passed"]):
        raise ValueError("Observed search completion does not satisfy the expected hard components")
    stamp = datetime.now(timezone.utc).isoformat()
    inventory = []
    with open_registry(DB) as c:
        for label, initial, final, validation_id in (
            ("INT06_to_MID", "INT06_9748648", "MID9737143", "fe110_int06_mid_ci9796856_vfa9798421_grade_a"),
            ("MID_to_FS", "MID9737143", "FS-A9725471", "fe110_c2ho_oh_dimer9746548_vfa9747902_accepted_20260910")):
            validation = c.execute("SELECT ts_validation_id,source_saddle_calculation_id,grade,kinetic_eligible,imaginary_frequencies_cm1 FROM ts_validations WHERE ts_validation_id=?", (validation_id,)).fetchone()
            if validation is None:
                raise ValueError("Expected registered segment absent")
            barriers = [dict(row) for row in c.execute("SELECT barrier_set_id,forward_barrier_ev,reverse_barrier_ev,reaction_energy_ev,validation_status FROM ts_barriers WHERE ts_validation_id=?", (validation_id,))]
            templates = [dict(row) for row in c.execute("SELECT template_id,outcome,validation_grade FROM ts_strategy_templates WHERE ts_validation_id=?", (validation_id,))]
            inventory.append({"step": label, "initial_state": initial, "final_state": final,
                              "validation": dict(validation), "barriers": barriers, "strategies": templates,
                              "delta_G_eV": None, "thermochemistry_ready": False,
                              "source_authority": "Existing registry acceptance; no historical revalidation performed"})
    inventory.insert(0, {"step": "IS_A_to_INT06", "initial_state": "IS-A9725473", "final_state": "INT06_9748648",
                         "source_job_id": "9833429", "status": analysis["status"], "grade": "Ungraded",
                         "kinetic_eligible": False, "barriers": [], "strategies": [], "delta_G_eV": None})
    write_json(RECORD / "route_inventory.json", {"reaction": "C2HO* + H* -> C2H2O* + *",
               "ordered_states": ["IS-A9725473", "INT06_9748648", "MID9737143", "FS-A9725471"],
               "unit": "eV", "temperature_K": None, "pressure_Pa": None,
               "energy_convention": "fe110_converged_toten_sigma0p20_v1", "steps": inventory,
               "overall_status": "searches_finished_validation_and_registration_incomplete",
               "whole_route_grade_a": False, "kinetics_ready": False,
               "remaining": ["IS-A-to-INT06 final mode and DIMCAR soft residual review", "IS-A-to-INT06 local frequency validation and compatible barrier/strategy registration",
                             "INT06-to-MID compatible barrier and success-strategy registration",
                             "Lower ordinary-NEB peaks01/09 remain diagnostic features, not separately accepted TSs"]})
    notes = ("Search normal/electronic completion, atomic force0.015998 eV/A<0.02, negative curvature-0.63616 eV/A2. "
             "DIMCAR Force0.05255 and Torque0.29241 remain soft warnings. Final mode unreviewed; no frequency, Grade A, formal barrier or kinetics claim. User requested recording only.")
    files = []
    for name in ("INCAR", "KPOINTS", "POSCAR", "MODECAR", "PREVIOUS_POSCAR", "NEXT_POSCAR", "dimer_handoff.json",
                 "mode_review.json", "reaction_contract.normalized.json", *OUTPUTS, "scheduler_evidence.json", "dimer_analysis.json", "final_mode_review.json", "submission_record.json"):
        p = RUN / name
        files.append({"file_id": CALC + "_" + name.replace(".", "_"), "calculation_id": CALC,
                      "job_record_id": JOB, "role": "raw_output" if name in OUTPUTS else "input_or_validation_evidence",
                      "filename": name, "local_path": str(p), "remote_path": REMOTE + "/" + name if name in OUTPUTS else None,
                      "storage_mode": "local_and_remote" if name in OUTPUTS else "local", "byte_size": p.stat().st_size,
                      "sha256": sha256_file(p), "existence_status": "confirmed", "notes": "Candidate provenance only"})
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
             "batch_id": "dimer9833429_completion_candidate_20261006", "created_at": stamp,
             "reviewer": REVIEWER, "reason": "User requested truthful completed-path recording; no scientific acceptance override.",
             "rows": {"calculations": [{"calculation_id": CALC, "module": "transition_state_search",
                       "purpose": "IS-A to INT06 local H migration peak05 Dimer search completion; TS validation pending",
                       "scientific_system": "Fe110 Fe45 C2HO H", "workflow_status": "needs_review", "created_at": stamp,
                       "source_record": str(RUN / "submission_record.json"), "notes": notes}],
                      "jobs": [{"job_record_id": JOB, "calculation_id": CALC, "scheduler_job_id": "9833429",
                                "scheduler": "LSF", "server_alias": "sunboquan-codex", "queue": "Gkn_normal",
                                "remote_directory": REMOTE, "submit_script": str(RUN / "script.lsf")}],
                      "job_status_history": [{"job_record_id": JOB, "scheduler_status": "DONE",
                              "scientific_status": "Search force criterion passed; TS validation pending", "checked_at": scheduler["checked_at"],
                              "source_command": scheduler["source_command"], "source_text": scheduler["query"]["stdout"],
                              "reviewer": REVIEWER, "notes": notes}], "files": files,
                      "reviews": [{"review_id": CALC + "_completion_review_20261006", "calculation_id": CALC,
                                    "review_type": "search_stage_completion_not_ts_acceptance", "decision": "needs_review",
                                    "reviewer": REVIEWER, "reviewed_at": stamp, "evidence": str(RUN / "dimer_analysis.json"), "reason": notes}]}}
    write_json(RECORD / "registry_batch.json", batch)
    plan = plan_registry_batch(DB, batch)
    write_json(RECORD / "registry_plan.json", plan)
    print("Plan", plan["plan_sha256"], "scope", plan["scope"], "insert", plan["insert_count"])
    print("Dimer status", analysis["status"], "registered other segments", [(r["step"], r["validation"]["grade"], len(r["barriers"]), len(r["strategies"])) for r in inventory[1:]])


def apply():
    batch = load_json_object(RECORD / "registry_batch_inventory_complete.json")
    plan = load_json_object(RECORD / "registry_plan_inventory_complete.json")
    approval = approve_plan(plan, reviewer=REVIEWER, reviewed_at=datetime.now(timezone.utc).isoformat())
    write_json(RECORD / "registry_approval.json", approval)
    receipt = apply_registry_batch(DB, batch, confirmed_sha256=plan["plan_sha256"], plan=plan, approval=approval)
    write_json(RECORD / "registry_receipt.json", receipt)
    print("Recorded", receipt)


def complete_inventory():
    """Preserve the first plan; bind missing launcher/pseudopotential provenance."""
    batch = load_json_object(RECORD / "registry_batch.json")
    for name in ("script.lsf", "POTCAR.spec"):
        p = RUN / name
        batch["rows"]["files"].append({"file_id": CALC + "_" + name.replace(".", "_"),
             "calculation_id": CALC, "job_record_id": JOB, "role": "input", "filename": name,
             "local_path": str(p), "storage_mode": "local", "byte_size": p.stat().st_size,
             "sha256": sha256_file(p), "existence_status": "confirmed"})
    receipt = load_json_object(RUN / "submission_record.json")
    batch["rows"]["files"].append({"file_id": CALC + "_POTCAR", "calculation_id": CALC,
         "job_record_id": JOB, "role": "licensed_input", "filename": "POTCAR", "remote_path": REMOTE + "/POTCAR",
         "storage_mode": "remote", "sha256": receipt["potcar_sha256"], "existence_status": "confirmed",
         "license_or_sensitivity": "Licensed VASP pseudopotentials; do not copy into Git",
         "notes": "Hash verified by canonical submission executor; binding preserved in submission_record.json"})
    write_json_exclusive(RECORD / "registry_batch_inventory_complete.json", batch)
    plan = plan_registry_batch(DB, batch)
    write_json_exclusive(RECORD / "registry_plan_inventory_complete.json", plan)
    print("Complete inventory plan", plan["plan_sha256"], "insert", plan["insert_count"], "scope", plan["scope"])


def checkpoint():
    receipt = load_json_object(RECORD / "registry_receipt.json")
    if receipt["batch_id"] != "dimer9833429_completion_candidate_20261006":
        raise ValueError("Unexpected receipt")
    old_id = "task-is-a-int06-dimer9833429-20261004"
    event = load_json_object(ROOT / "modules/state_handoff/events" / (old_id + ".json"))
    stamp = datetime.now(timezone.utc).isoformat()
    event_id = "task-is-a-int06-dimer9833429-recorded-pending-validation-20261006"
    paths = [(RECORD / "user_request.json", "user_authorization"), (RUN / "scheduler_evidence.json", "scheduler"),
             (RUN / "dimer_analysis.json", "module_validation"), (RECORD / "route_inventory.json", "repository_document"),
             (RECORD / "registry_receipt.json", "repository_document")]
    event.update(event_id=event_id, occurred_at=stamp, recorded_at=stamp, supersedes=[old_id],
                 summary="User-requested candidate completion registered: Dimer9833429 DONE and VASP force gate passes; full reaction route remains incompletely validated.")
    event["evidence"] = [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p), "authority": a, "observed_at": stamp} for p, a in paths]
    event["payload"].update(objective="Review Dimer9833429 final mode and soft residuals before IS-A-to-INT06 TS frequency validation.",
         phase="verification", current_evidence=["Dimer9833429 scheduler DONE; remote output hashes match recovered files. Normal termination, final SCF convergence and VASP maximum force0.015998 eV/A pass; last complete curvature-0.63616 eV/A2.",
         "Completed search candidate recorded in project_registry.sqlite3 with workflow needs_review; no Grade-A, final barrier or successful strategy inserted.",
         "DIMCAR Force0.05255/Torque0.29241 remain explicit soft warnings; final_mode_review is needs_review; local frequency not performed. User recording request is not interpreted as residual acceptance.",
         "INT06-to-MID CI9796856/VFA9798421 already has registered Grade A; compatible barrier and successful strategy records not found. MID-to-FS Dimer9746548/VFA9747902 has Grade A, accepted electronic barrier1.28582718 eV and success strategy.",
         "Full route IS-A -> INT06 -> MID -> FS-A is mapped, but validation/registration not complete; minor parent peaks01/09 remain diagnostic features."],
         one_executable_step="Review current final NEWMODECAR and request the exact DIMCAR soft-residual decision before preparing frequency validation; do not submit a new calculation from the recording request.",
         submission_boundary="Record-only user scope; no frequency, continuation, GPU or other expensive submission authorized.",
         authoritative_references=[p.relative_to(ROOT).as_posix() for p, _ in paths])
    write_json_exclusive(ROOT / "modules/state_handoff/events" / (event_id + ".json"), event)
    print("Event", event_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "complete-inventory", "apply", "checkpoint"))
    args = parser.parse_args()
    {"prepare": prepare, "complete-inventory": complete_inventory, "apply": apply, "checkpoint": checkpoint}[args.action]()
