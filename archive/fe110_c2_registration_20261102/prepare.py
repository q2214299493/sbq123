"""Prepare one reviewed completion batch; never approve/apply it or submit jobs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from archive.fe110_adsorption_acceptance_20261029.prepare import checked_decision
from scripts.adsorption.prepare_completion_registration import result_evidence
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.vasp_result_gate import validate_lsf_done_evidence

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020/final_review_20261101_v1"
OUT = ROOT / "outputs/fe110_c2_registration_20261102_v1"
DB = ROOT / "data/project_registry.sqlite3"
BOOK = ROOT / "outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx"
QUOTE = "对证据齐全的构型进行正式登记审核， 然后录入吸附表中 然后提交16-19"
REVIEWER = "Codex adsorption owner review under explicit user authority 2026-11-02"
ACCEPT = ["11_B", "12_C", "13_C", "14_B", "14_C", "15_A", "15_B", "15_C"]
DUPLICATES = {"11_A": "11_B", "14_A": "14_B"}
MISSING = ["11_C", "12_A", "12_B", "13_B"]
SITES = {
    "11_B": "C(long_bridge)，CH3朝外",
    "12_C": "C/O双位吸附，均在short_bridge邻域",
    "13_C": "双C吸附：C(OH)近top，CH2近hollow；OH朝外",
    "14_B": "C(long_bridge)，O–CH3朝外",
    "14_C": "C(top)，O–CH3朝外",
    "15_A": "双C吸附，hollow/short_bridge邻域",
    "15_B": "η2-C2H4/top，同配位Fe41",
    "15_C": "双C吸附，short_bridge邻域",
}


def initialize():
    if OUT.exists():
        raise FileExistsError("preserve existing registration attempt and inspect receipts")
    original = load_json_object(SOURCE / "analysis.json")
    final = load_json_object(SOURCE / "final_review.json")
    if final["analysis_sha256"] != sha256_file(SOURCE / "analysis.json"):
        raise ValueError("review source changed")
    if len(original["records"]) != 15 or final["numerical_geometry_pass_count"] != 14:
        raise ValueError("unexpected final audit scope")
    scheduler_receipt = load_json_object(SOURCE / "scheduler/receipt.json")
    raw = SOURCE / "scheduler/stdout.txt"
    if sha256_file(raw) != scheduler_receipt["stdout_sha256"]:
        raise ValueError("raw scheduler evidence changed")
    observed = {}
    for line in raw.read_text().splitlines():
        fields = line.split()
        if len(fields) > 2 and fields[0].isdigit() and fields[2] == "DONE":
            item = {"server_alias": "sunboquan-codex", "scheduler": "LSF", "job_id": fields[0],
                "status": "DONE", "checked_at": scheduler_receipt["checked_at"],
                "source_command": scheduler_receipt["command"], "source_text": line,
                "raw_source": str(raw), "raw_sha256": sha256_file(raw)}
            validate_lsf_done_evidence(item)
            observed[fields[0]] = item
    original["scheduler_evidence"] = observed
    original["prior_analysis_path"] = str(SOURCE / "analysis.json")
    original["prior_analysis_sha256"] = sha256_file(SOURCE / "analysis.json")
    original["comparisons"] = final["comparisons_with_C_exchange"]
    now = datetime.now(timezone.utc).isoformat()
    decisions = {}
    for row in original["records"]:
        name = row["name"]
        if not row["requested_graph_preserved"]:
            raise ValueError("changed final chemistry needs separate review: " + name)
        if name in ACCEPT:
            if row["blockers"] or row["job_id"] not in observed:
                raise ValueError("incomplete accepted source: " + name)
            reason = "Normal termination, SCF/0.02eV/A force, coordinate-force, locked branch and intact chemistry pass; independent within reviewed batch."
            decisions[name] = {"decision": "accept", "reason": reason, "final_site": SITES[name],
                "final_species": row["target_graph"] + "*", "chemical_event": "intact_adsorption", "plausibility_status": "PASS"}
        elif name in DUPLICATES:
            decisions[name] = {"decision": "duplicate", "duplicate_of": DUPLICATES[name],
                "reason": "Reviewed symmetry/H/C-permutation, relaxed Fe environment and energy match an accepted representative; retain source without another accepted row."}
        else:
            if name not in MISSING and name != "13_A":
                raise ValueError("unreviewed source selection")
            reason = "Terminal scheduler evidence unavailable; keep converged scientific evidence separate from UNKNOWN queue state." if name in MISSING else "NSW300 ended with fmax0.06108446eV/A; geometry covered by numerically converged13_B; no rerun, no accepted energy."
            decisions[name] = {"decision": "needs_review", "reason": reason}
    OUT.mkdir()
    shutil.copyfile(BOOK, OUT / "before.xlsx")
    write_json_exclusive(OUT / "analysis.json", original)
    write_json_exclusive(OUT / "decisions.json", {"analysis_sha256": sha256_file(OUT / "analysis.json"),
        "authorizing_user_request": QUOTE, "reviewer": REVIEWER, "reviewed_at": now, "decisions": decisions,
        "15_B_site_review": {"shared_nearest_Fe_0based": 41, "two_C_Fe_distances_A": [2.0723250783794076, 2.0724090963685575],
            "C_midpoint_top_projection_offset_A": 0.004471359085645822,
            "interpretation": "molecular eta2/top motif; individual C projections are off-symmetry, not exact long bridges"}})
    write_json_exclusive(OUT / "request.json", {"user_request": QUOTE, "created_at": now,
        "source_review_sha256": sha256_file(SOURCE / "final_review.json"),
        "workbook": str(BOOK), "workbook_sha256_before": sha256_file(BOOK),
        "accepted_names": ACCEPT, "duplicate_names": DUPLICATES, "scheduler_pending_names": MISSING,
        "new_calculations": 0, "no_reference_energy_inference": True})
    print("PREPARED_SCOPE 8 accepts,2 duplicates,5 pending; original workbook backed up; no registry writes")


def prepare_batch():
    destination = OUT / "registry_batch.json"
    if destination.exists():
        raise FileExistsError(destination)
    analysis = load_json_object(OUT / "analysis.json")
    decision_doc = load_json_object(OUT / "decisions.json")
    if decision_doc["analysis_sha256"] != sha256_file(OUT / "analysis.json"):
        raise ValueError("scientific review binding changed")
    rows = {key: [] for key in ("files", "results", "reviews", "calculation_compatibility", "job_status_history")}
    changes, provenance = [], {}
    directory_reviews = OUT / "scientific_reviews"
    directory_reviews.mkdir(exist_ok=False)
    now = decision_doc["reviewed_at"]
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        event = db.execute("SELECT coalesce(max(status_event_id),0) FROM job_status_history").fetchone()[0]
        for record in analysis["records"]:
            name, cid = record["name"], record["calculation_id"]
            decision = decision_doc["decisions"][name]
            verdict = checked_decision(record, decision, analysis, decision_doc["decisions"])
            calculation = db.execute("SELECT * FROM calculations WHERE calculation_id=?", (cid,)).fetchone()
            job = db.execute("SELECT * FROM jobs WHERE calculation_id=? AND scheduler_job_id=?", (cid, record["job_id"])).fetchone()
            if calculation is None or job is None or db.execute("SELECT 1 FROM results WHERE calculation_id=?", (cid,)).fetchone():
                raise ValueError("unexpected prior result/job state; reconcile before preparing: " + name)
            prefix = cid + "_acceptance_20261102"
            folder = Path(record["directory"])
            receipt = load_json_object(folder / "collection.json")
            if sha256_file(folder / "collection.json") != record["collection_sha256"]:
                raise ValueError("source collection changed")
            for filename, metadata in receipt["remote"]["files"].items():
                if filename != "POTCAR" and sha256_file(folder / filename) != metadata["sha256"]:
                    raise ValueError("scientific source changed: " + name + "/" + filename)
                rows["files"].append({"file_id": prefix + "_" + filename, "calculation_id": cid,
                    "job_record_id": job["job_record_id"], "role": "licensed_input_metadata" if filename == "POTCAR" else "completion_evidence",
                    "filename": filename, "local_path": None if filename == "POTCAR" else str(folder / filename),
                    "remote_path": receipt["remote"]["directory"] + "/" + filename,
                    "storage_mode": "remote_only" if filename == "POTCAR" else "local_and_remote", **metadata, "existence_status": "confirmed"})
            comp = record["compatibility"]
            old = db.execute("SELECT compatibility_json FROM calculation_compatibility WHERE calculation_id=?", (cid,)).fetchone()
            if old is None:
                rows["calculation_compatibility"].append({"calculation_id": cid, "compatibility_fingerprint": sha256_json(comp),
                    "compatibility_json": json.dumps(comp, sort_keys=True, separators=(",", ":")), "reviewer": REVIEWER, "reviewed_at": now})
            elif sha256_json(json.loads(old[0])) != sha256_json(comp):
                raise ValueError("preserve existing compatibility binding")
            review_path = directory_reviews / (name + ".json")
            scheduler = analysis["scheduler_evidence"].get(record["job_id"])
            write_json_exclusive(review_path, {"record": record, "decision": decision, "scheduler": scheduler,
                "reviewer": REVIEWER, "reviewed_at": now, "analysis_sha256": sha256_file(OUT / "analysis.json"),
                "decisions_sha256": sha256_file(OUT / "decisions.json"),
                "scope": "Final electronic surface-state energy only; not Eads, vibrational stability, thermochemistry or global minimum."})
            rows["files"].append({"file_id": prefix + "_scientific_review", "calculation_id": cid,
                "job_record_id": job["job_record_id"], "role": "scientific_review", "filename": review_path.name,
                "local_path": str(review_path), "storage_mode": "local_only", "sha256": sha256_file(review_path),
                "byte_size": review_path.stat().st_size, "existence_status": "confirmed"})
            rows["reviews"].append({"review_id": prefix + "_review", "calculation_id": cid,
                "review_type": "adsorption_completion_chemistry_compatibility_and_duplicate", "decision": verdict,
                "reviewer": REVIEWER, "reviewed_at": now, "evidence": str(review_path) + "#sha256=" + sha256_file(review_path), "reason": decision["reason"]})
            event += 1
            raw_path = SOURCE / "scheduler" / ("stdout.txt" if scheduler else "stderr.txt")
            raw_receipt = load_json_object(SOURCE / "scheduler/receipt.json")
            if sha256_file(raw_path) != raw_receipt["stdout_sha256" if scheduler else "stderr_sha256"]:
                raise ValueError("scheduler source changed")
            rows["job_status_history"].append({"status_event_id": event, "job_record_id": job["job_record_id"],
                "scheduler_status": "DONE" if scheduler else "UNKNOWN",
                "scientific_status": "force_not_converged" if name == "13_A" else "reviewed_" + verdict,
                "checked_at": raw_receipt["checked_at"], "source_command": raw_receipt["command"],
                "source_text": scheduler["source_text"] if scheduler else raw_path.read_text(), "reviewer": REVIEWER,
                "notes": "Original observation time retained; missing queue history never inferred DONE."})
            current = calculation["workflow_status"]
            targets = ["accepted"] if verdict == "accept" else ["needs_review", "duplicate"] if verdict == "duplicate" else ["needs_review"]
            for index, target in enumerate(targets):
                if current != target:
                    changes.append({"status_change_id": prefix + "_status" + str(index), "calculation_id": cid,
                        "expected_workflow_status": current, "new_workflow_status": target,
                        "changed_at": now, "reviewer": REVIEWER, "reason": decision["reason"]})
                    current = target
            validation = {"owner": "vasp_relaxation", "directory": str(folder),
                "source_files": {n: record["source_files"][n] for n in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")},
                "completion_review_sha256": sha256_file(review_path)}
            identity = {"formula": record["formula"], "target_graph": record["target_graph"],
                "intact": record["intact"], "final_site": decision.get("final_site"), "duplicate_of": decision.get("duplicate_of")}
            for kind, number, text, unit in [("final_toten", record["toten_eV"], None, "eV"),
                    ("final_max_movable_force", record["fmax_eV_A"], None, "eV/angstrom"),
                    ("final_state_identity", None, json.dumps(identity, ensure_ascii=True), None)]:
                accepted = verdict == "accept" and kind == "final_toten"
                result = {"result_id": prefix + "_" + kind, "calculation_id": cid, "result_name": kind,
                    "numeric_value": number, "text_value": text, "unit": unit,
                    "source_file_id": prefix + ("_CONTCAR" if kind == "final_state_identity" else "_OUTCAR"),
                    "reference_convention": comp["final_energy_convention"] if kind == "final_toten" else "reviewed_final_structure_or_force",
                    "source_locator": "final complete force/energy table with coordinate correspondence",
                    "extraction_method": "existing canonical VASP/scientific owners; complete output SHA256",
                    "validation_status": "accepted_compatible_final_energy" if accepted else "reviewed",
                    "created_at": now, "notes": decision["reason"] + "; no Eads inferred."}
                rows["results"].append(result)
                provenance[result["result_id"]] = result_evidence(result, validation, comp, review_path, REVIEWER, now)
    write_json_exclusive(destination, {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_c2_11_15_acceptance_20261102_v1", "created_at": now, "reviewer": REVIEWER,
        "reason": QUOTE, "rows": rows, "workflow_status_changes": changes, "result_provenance": provenance})
    print("PREPARED", {k: len(v) for k, v in rows.items()}, "status_changes", len(changes), "accepted_energies", len(ACCEPT))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("initialize", "prepare"))
    args = parser.parse_args()
    {"initialize": initialize, "prepare": prepare_batch}[args.phase]()
