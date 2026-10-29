"""Prepare the explicitly reviewed C2 registry batch; never approve or apply it."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.adsorption.prepare_completion_registration import check_decision, result_evidence
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.registry_connection import open_registry

from .collect import DB, OUT


def checked_decision(record, decision, analysis, decisions):
    scheduler = analysis["scheduler_evidence"].get(record["job_id"])
    duplicate = decision.get("duplicate_of")
    owner_record = {"eligible_for_review": not record["blockers"], "duplicate_of": duplicate}
    verdict = check_decision(owner_record, decision, scheduler)
    if verdict == "duplicate":
        matches = [r for r in analysis["comparisons"]
                   if {r["first"], r["second"]} == {record["name"], duplicate} and r["duplicate"]]
        if len(matches) != 1 or decisions[duplicate]["decision"] != "accept":
            raise ValueError("duplicate requires one reviewed surface match to an accepted representative")
    return verdict


def main():
    destination = OUT / "registry_batch.json"
    if destination.exists():
        raise FileExistsError(destination)
    analysis_path, decisions_path = OUT / "analysis.json", OUT / "decisions.json"
    analysis, decisions = map(load_json_object, (analysis_path, decisions_path))
    if decisions["analysis_sha256"] != sha256_file(analysis_path):
        raise ValueError("scientific decisions do not bind the current analysis")
    names = {r["name"] for r in analysis["records"]}
    if set(decisions["decisions"]) != names:
        raise ValueError("every collected source needs one explicit scientific decision")
    reviewer, reviewed_at = decisions["reviewer"], decisions["reviewed_at"]
    rows = {key: [] for key in ("files", "results", "reviews", "calculation_compatibility", "job_status_history")}
    provenance, changes = {}, []
    review_directory = OUT / "scientific_reviews"
    review_directory.mkdir(exist_ok=False)
    with open_registry(DB) as connection:
        connection.execute("PRAGMA query_only=ON")
        event_id = connection.execute("SELECT coalesce(max(status_event_id),0) FROM job_status_history").fetchone()[0]
        for record in analysis["records"]:
            name, cid = record["name"], record["calculation_id"]
            decision = decisions["decisions"][name]
            verdict = checked_decision(record, decision, analysis, decisions["decisions"])
            calculation = connection.execute("SELECT * FROM calculations WHERE calculation_id=?", (cid,)).fetchone()
            job = connection.execute("SELECT * FROM jobs WHERE calculation_id=? AND scheduler_job_id=?", (cid, record["job_id"])).fetchone()
            if calculation is None or job is None:
                raise ValueError("source is not the registered submitted calculation")
            prefix = cid + "_acceptance_20261029"
            directory = Path(record["directory"])
            receipt = load_json_object(directory / "collection.json")
            if record["collection_sha256"] != sha256_file(directory / "collection.json"):
                raise ValueError("source receipt changed after analysis")
            for filename, metadata in receipt["remote"]["files"].items():
                if filename != "POTCAR" and sha256_file(directory / filename) != metadata["sha256"]:
                    raise ValueError("scientific source changed after analysis: " + filename)
                rows["files"].append({"file_id": prefix + "_" + filename, "calculation_id": cid,
                    "job_record_id": job["job_record_id"], "role": "licensed_input_metadata" if filename == "POTCAR" else "completion_evidence",
                    "filename": filename, "local_path": None if filename == "POTCAR" else str(directory / filename),
                    "remote_path": receipt["remote"]["directory"] + "/" + filename,
                    "storage_mode": "remote_only" if filename == "POTCAR" else "local_and_remote",
                    **metadata, "existence_status": "confirmed"})
            comp = record["compatibility"]
            old_comp = connection.execute("SELECT compatibility_json FROM calculation_compatibility WHERE calculation_id=?", (cid,)).fetchone()
            if old_comp is None:
                rows["calculation_compatibility"].append({"calculation_id": cid,
                    "compatibility_fingerprint": sha256_json(comp),
                    "compatibility_json": json.dumps(comp, sort_keys=True, separators=(",", ":")),
                    "reviewer": reviewer, "reviewed_at": reviewed_at})
            elif sha256_json(json.loads(old_comp[0])) != sha256_json(comp):
                raise ValueError("preserve the original calculation compatibility binding")
            review_path = review_directory / (name + ".json")
            review = {"record": record, "decision": decision, "reviewer": reviewer, "reviewed_at": reviewed_at,
                "analysis_sha256": sha256_file(analysis_path), "decisions_sha256": sha256_file(decisions_path),
                "scope": "Converged final electronic surface-state energy; no Eads, vibration, thermal or global-minimum claim."}
            write_json_exclusive(review_path, review)
            rows["files"].append({"file_id": prefix + "_scientific_review", "calculation_id": cid,
                "job_record_id": job["job_record_id"], "role": "scientific_review", "filename": review_path.name,
                "local_path": str(review_path), "storage_mode": "local_only", "sha256": sha256_file(review_path),
                "byte_size": review_path.stat().st_size, "existence_status": "confirmed"})
            rows["reviews"].append({"review_id": prefix + "_review", "calculation_id": cid,
                "review_type": "adsorption_completion_chemistry_compatibility_and_duplicate", "decision": verdict,
                "reviewer": reviewer, "reviewed_at": reviewed_at,
                "evidence": str(review_path) + "#sha256=" + sha256_file(review_path), "reason": decision["reason"]})
            scheduler = analysis["scheduler_evidence"].get(record["job_id"])
            if scheduler:
                event_id += 1
                rows["job_status_history"].append({"status_event_id": event_id, "job_record_id": job["job_record_id"],
                    "scheduler_status": scheduler["status"], "scientific_status": "converged_" + verdict,
                    "checked_at": scheduler["checked_at"], "source_command": scheduler["source_command"],
                    "source_text": scheduler.get("source_text", scheduler.get("query", {}).get("stdout", "")),
                    "reviewer": reviewer, "notes": "Historical observation time retained; retrieved review is not a new scheduler observation."})
            current = calculation["workflow_status"]
            targets = ["accepted"] if verdict == "accept" else ["needs_review", "duplicate"] if verdict == "duplicate" else ["needs_review"]
            for index, target in enumerate(targets):
                if current == target:
                    continue
                changes.append({"status_change_id": prefix + "_status" + str(index), "calculation_id": cid,
                    "expected_workflow_status": current, "new_workflow_status": target,
                    "changed_at": reviewed_at, "reviewer": reviewer, "reason": decision["reason"]})
                current = target
            validation = {"owner": "vasp_relaxation", "directory": str(directory),
                "source_files": {n: record["source_files"][n] for n in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")},
                "completion_review_sha256": sha256_file(review_path)}
            values = [("final_toten", record["toten_eV"], None, "eV"),
                      ("final_max_movable_force", record["fmax_eV_A"], None, "eV/angstrom"),
                      ("final_state_identity", None, json.dumps({"formula": record["formula"],
                       "target_graph": record["target_graph"], "intact": record["intact"],
                       "duplicate_of": decision.get("duplicate_of")}, ensure_ascii=True), None)]
            for kind, number, text, unit in values:
                accepted = verdict == "accept" and kind == "final_toten"
                result = {"result_id": prefix + "_" + kind, "calculation_id": cid, "result_name": kind,
                    "numeric_value": number, "text_value": text, "unit": unit,
                    "source_file_id": prefix + ("_CONTCAR" if kind == "final_state_identity" else "_OUTCAR"),
                    "reference_convention": comp["final_energy_convention"] if kind == "final_toten" else "reviewed_final_structure_or_force",
                    "source_locator": "final complete OUTCAR force/energy block; exact CONTCAR correspondence",
                    "extraction_method": "canonical VASP convergence/energy/geometry owners with full-output SHA256",
                    "validation_status": "accepted_compatible_final_energy" if accepted else "reviewed",
                    "created_at": reviewed_at, "notes": decision["reason"] + "; no adsorption energy inferred."}
                rows["results"].append(result)
                provenance[result["result_id"]] = result_evidence(result, validation, comp, review_path, reviewer, reviewed_at)
    write_json_exclusive(destination, {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_c2_final_acceptance_20261029_v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer, "reason": decisions["authorizing_user_request"], "rows": rows,
        "workflow_status_changes": changes, "result_provenance": provenance})
    print("PREPARED", len(analysis["records"]), "reviews", len(rows["results"]), "results",
          sum(r["validation_status"].startswith("accepted") for r in rows["results"]), "accepted final energies; database unchanged")


if __name__ == "__main__":
    main()
