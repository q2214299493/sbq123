"""Stage or apply the exact approved pair of Fe(110) barrier registrations."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.adsmind_lite.evidence_lifecycle import review_subject, text_digest
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_mutations import apply_registry_batch, plan_registry_batch
from scripts.registry_transactions import approve_plan
from scripts.ts_strategy_engine.evidence import record_matched_static_barrier
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.matched_static_evidence import matched_static_convention, matched_static_rows
from scripts.ts_strategy_engine.templates import validate_record
from scripts.ts_validation.saddle_energy import CONVENTION

from .refresh import OUTPUT, PREP, REVIEWER, binding


DB = OUTPUT.parents[1] / "data/project_registry.sqlite3"
STATUS = "accepted_compatible_final_energy"
CASES = ("ch_co", "int06_mid")
STAMP = "barrier_energy_review_20261118"


def row_file(record, job, file_id, role):
    path = Path(record["path"])
    if sha256_file(path) != record["sha256"]:
        raise ValueError(f"Reviewed bytes changed: {path}")
    return {"file_id": file_id, "calculation_id": job["calculation_id"], "job_record_id": job["job_record_id"],
        "role": role, "filename": path.name, "local_path": str(path), "storage_mode": "local",
        "byte_size": path.stat().st_size, "sha256": record["sha256"], "existence_status": "confirmed"}


def provenance(row, validation, compatibility, review_path, at):
    body = review_path.read_text(encoding="utf-8")
    digest = text_digest(body)
    location = str(review_path)
    domain = "transition_state_search"
    evidence = {
        "claim": {"id": row["result_id"], "type": "calculated_result",
            "statement": "Existing validated saddle; compatible final OUTCAR TOTEN, no new VASP run.",
            "source_reference": location, "status": "reviewed", "evidence_relationship": "supports",
            "scope": "registry_acceptance", "domain": domain, "compatibility": compatibility,
            "result_sha256": sha256_json(row), "validation_sha256": sha256_json(validation)},
        "source": {"identity": "hash-bound TS reference refresh", "reference": location, "retrieved_at": at,
            "snapshot": {"text": body, "sha256": digest}, "immutable_reference": location + "#sha256=" + digest},
        "content": {"text": body, "start": 0, "end": len(body), "sha256": digest},
        "review": {"reviewer": REVIEWER, "reviewed_at": at, "decision": "accepted", "scope": "registry_acceptance"},
    }
    evidence["review"]["subject_sha256"] = review_subject(evidence)
    evidence["transfer"] = {"review_sha256": sha256_json(evidence["review"]), "domain": domain,
                            "compatibility": compatibility}
    return {"type": "calculated_result", "registry_stage": "accepted_result",
            "evidence": evidence, "scientific_validation": validation}


def learning_record(case, state, packet, file_id):
    contract = state["reaction_contract"]
    is_dimer = case == "ch_co"
    result = {"template_id": "fe110_" + case + "_grade_a_strategy_20261118",
        "reaction_family": contract["reaction_family"], "source_calculation_id": state["source_saddle_calculation_id"],
        "ts_validation_id": state["barrier_claim"]["ts_validation_id"], "barrier_set_id": state["barrier_claim"]["barrier_set_id"],
        "ts_structure_file_id": file_id,
        "fingerprint": build_fingerprint(contract, atom_symbols=packet["source_members"]["initial"]["structure"]["symbols"]),
        "waypoint_strategy": ([{"method": "GPU seed then local full-atom IDPP in the under-resolved C–C formation segment"}]
            if is_dimer else [{"method": "Smooth elevated lateral H migration waypoints between independently relaxed endpoints"}]),
        "interpolation_strategy": "segmented_idpp",
        "neb_settings": {"sequence": ["ordinary_neb"] if is_dimer else ["ordinary_neb", "ci_neb"],
                         "review": "Require continuous periodic atom mapping and a reviewed local maximum"},
        "dimer_usage": {"used": is_dimer, "rule": "Refine the reviewed peak with a local path tangent"}
            if is_dimer else {"used": False, "rule": "Use converged climbing saddle when validated"},
        "convergence_history": {"verification": "Converged saddle with one reviewed target imaginary mode in a local partial Hessian"},
        "failure_cases": [],
        "correction_strategy": "Local path review and refinement selection; revalidate mapping, endpoints and modes for every new system.",
        "outcome": "success", "validation_grade": "A"}
    validate_record(result)
    return result


def add_energy_status(connection, batch, job_id, at, evidence):
    previous = connection.execute("SELECT * FROM job_status_history WHERE job_record_id=? "
        "ORDER BY checked_at DESC,status_event_id DESC LIMIT 1", (job_id,)).fetchone()
    if not previous or previous["scheduler_status"] != "DONE":
        raise ValueError(f"Existing terminal scheduler record required for {job_id}")
    if previous["scientific_status"] != STATUS:
        batch["rows"]["job_status_history"].append({"job_record_id": job_id,
            "scheduler_status": previous["scheduler_status"], "scientific_status": STATUS, "checked_at": at,
            "source_command": previous["source_command"], "source_text": previous["source_text"], "reviewer": REVIEWER,
            "notes": "Scientific review of compatible final energy using retained DONE observation "
                f"{previous['status_event_id']}; not a new scheduler query or change to original target assessment. "
                + str(evidence)})


def verify_member(member):
    for name in ("outcar", "structure", "incar"):
        if sha256_file(Path(member[name]["path"])) != member[name]["sha256"]:
            raise ValueError(f"Stale energy-chain member: {member[name]['path']}")


def stage_case(connection, case, batch, at):
    out = OUTPUT / case
    gate_path = out / "current_gate_decision.json"
    gate = load_json_object(gate_path)
    if "APPROVE_TS_CANDIDATE" not in gate["ALLOWED_ACTIONS"]:
        raise ValueError(f"{case} is not gated for registration")
    packet = load_json_object(PREP / case / "review_packet.json")
    state = gate["EVIDENCE"]["validation"]
    claim = state["barrier_claim"]
    if connection.execute("SELECT 1 FROM ts_barriers WHERE ts_validation_id=?", (claim["ts_validation_id"],)).fetchone():
        raise ValueError("Barrier already registered; reconcile receipt instead of inserting twice")
    cid = state["source_saddle_calculation_id"]
    job = dict(connection.execute("SELECT * FROM jobs WHERE job_record_id=?",
                                  (state["source_job_record_id"],)).fetchone())
    ts = packet["source_members"]["ts"]
    existing = connection.execute("SELECT file_id FROM files WHERE calculation_id=? AND job_record_id=? AND filename='OUTCAR' "
                                  "AND local_path=? AND existence_status='confirmed' AND sha256=?",
                                  (cid, job["job_record_id"], ts["outcar"]["path"], ts["outcar"]["sha256"])).fetchone()
    energy_id = existing[0] if existing else f"{cid}_{STAMP}_OUTCAR"
    structure_id = f"{cid}_{STAMP}_structure"
    if not existing:
        batch["rows"]["files"].append(row_file(ts["outcar"], job, energy_id, "raw_output"))
    batch["rows"]["files"].append(row_file(ts["structure"], job, structure_id, "ts_structure"))
    compatibility = state["reaction_contract"]["compatibility"]
    batch["rows"]["calculation_compatibility"].append({"calculation_id": cid,
        "compatibility_fingerprint": state["compatibility_sha256"], "compatibility_json": json.dumps(compatibility),
        "reviewer": REVIEWER, "reviewed_at": at})
    row = {"result_id": claim["ts_result_id"], "calculation_id": cid, "result_name": "final_toten",
        "numeric_value": ts["final_toten_eV"], "unit": "eV", "reference_convention": CONVENTION,
        "source_file_id": energy_id, "source_locator": "final free energy TOTEN",
        "extraction_method": "Current Grade A TS binding and final OUTCAR parsing",
        "validation_status": STATUS, "created_at": at}
    validation = {"owner": "ts_saddle_final_energy", "gate_decision": str(gate_path),
                  "gate_state_sha256": gate["state_sha256"]}
    review_path = out / "reference_review.json"
    batch["rows"]["results"].append(row)
    batch["result_provenance"][row["result_id"]] = provenance(row, validation, compatibility, review_path, at)
    for side in ("initial", "final"):
        member = packet["source_members"][side]
        verify_member(member)
        add_energy_status(connection, batch, member["registered_energy_file"]["job_record_id"], at,
                          binding(PREP / case / "review_packet.json"))
    add_energy_status(connection, batch, job["job_record_id"], at, binding(review_path))
    return {"gate_decision": str(gate_path), "gate_state_sha256": gate["state_sha256"], "claim": claim,
            "learning_record": learning_record(case, state, packet, structure_id)}


def prepare():
    at = datetime.now(timezone.utc).isoformat()
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "c1_c2_ts_final_energy_20261118", "created_at": at, "reviewer": REVIEWER,
        "reason": "Append compatible source evidence for two explicitly authorized electronic barriers.",
        "rows": {name: [] for name in ("files", "calculation_compatibility", "job_status_history", "results")},
        "result_provenance": {}}
    with open_registry(DB) as connection:
        connection.execute("PRAGMA query_only=ON")
        cases = {case: stage_case(connection, case, batch, at) for case in CASES}
    write_json_exclusive(OUTPUT / "energy_batch.json", batch)
    write_json_exclusive(OUTPUT / "barrier_requests.json", cases)
    plan = plan_registry_batch(DB, batch)
    write_json_exclusive(OUTPUT / "energy_plan.json", plan)
    print({key: plan[key] for key in ("insert_count", "update_count", "plan_sha256", "scope")})


def apply(plan_sha256):
    plan = load_json_object(OUTPUT / "energy_plan.json")
    batch = load_json_object(OUTPUT / "energy_batch.json")
    cases = load_json_object(OUTPUT / "barrier_requests.json")
    if plan_sha256 != plan["plan_sha256"] or set(cases) != set(CASES):
        raise ValueError("Exact reviewed plan and case set required")
    for case in cases:
        packet = load_json_object(PREP / case / "review_packet.json")
        for member in packet["source_members"].values():
            verify_member(member)
    approval = approve_plan(plan, reviewer=REVIEWER, reviewed_at=datetime.now(timezone.utc).isoformat())
    write_json_exclusive(OUTPUT / "energy_approval.json", approval)
    result = apply_registry_batch(DB, batch, confirmed_sha256=plan_sha256, plan=plan, approval=approval)
    write_json_exclusive(OUTPUT / "energy_receipt.json", result)
    for case, entry in cases.items():
        claim = entry["claim"]
        with open_registry(DB) as connection:
            connection.execute("PRAGMA query_only=ON")
            matched_static_convention(matched_static_rows(connection,
                (claim["initial_result_id"], claim["ts_result_id"], claim["final_result_id"])))
        result = record_matched_static_barrier(DB, gate_decision=Path(entry["gate_decision"]),
            gate_state_sha256=entry["gate_state_sha256"], learning_record=entry["learning_record"],
            notes="Electronic barrier only. Compatible final TOTEN; no ZPE, entropy or free-energy corrections.",
            **claim)
        write_json_exclusive(OUTPUT / case / "barrier_registration_receipt.json", result)
        print(case, result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "apply"))
    parser.add_argument("--reviewed-plan-sha256")
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    else:
        apply(args.reviewed_plan_sha256)
