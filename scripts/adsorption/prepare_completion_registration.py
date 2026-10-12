"""Prepare (never apply) an append-only batch from explicitly reviewed adsorption evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.adsmind_lite.evidence_lifecycle import review_subject, text_digest
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_atomic
from scripts.registry_connection import open_registry


def result_evidence(row, validation, compatibility, review_path, reviewer, reviewed_at):
    text = review_path.read_text(encoding="utf-8")
    reference = str(review_path.resolve())
    evidence = {
        "claim": {"id": row["result_id"], "type": "calculated_result", "statement":
                  f"Reviewed VASP {row['result_name']} for {row['calculation_id']}; no prediction or adsorption-energy inference.",
                  "source_reference": reference, "status": "reviewed", "evidence_relationship": "supports",
                  "scope": "registry_acceptance", "domain": "adsorption_workflow", "compatibility": compatibility,
                  "result_sha256": sha256_json(row), "validation_sha256": sha256_json(validation)},
        "source": {"identity": "hash-bound adsorption completion review of collected VASP outputs",
                   "reference": reference, "retrieved_at": reviewed_at,
                   "snapshot": {"text": text, "sha256": text_digest(text)},
                   "immutable_reference": reference + "#sha256=" + text_digest(text)},
        "content": {"text": text, "start": 0, "end": len(text), "sha256": text_digest(text)},
        "review": {"reviewer": reviewer, "reviewed_at": reviewed_at, "decision": "accepted",
                   "scope": "registry_acceptance"},
    }
    evidence["review"]["subject_sha256"] = review_subject(evidence)
    evidence["transfer"] = {"review_sha256": sha256_json(evidence["review"]), "domain": "adsorption_workflow",
                            "compatibility": compatibility}
    return {"type": "calculated_result", "registry_stage": "accepted_result" if row["validation_status"].startswith("accepted") else "candidate",
            "evidence": evidence, "scientific_validation": validation}


def compatibility(record, receipt, analysis):
    clean = analysis["slab"]
    from .build_fe110_adsorption import read_poscar
    slab = read_poscar(Path(clean["path"]))
    cart = slab.frac @ slab.cell
    return {"branch": "true_fe110_5layer_5x5x1", "material": "fe", "surface": "fe110",
            "xc": "pbe", "potcar_family": "paw_pbe", "encut_ev": 400.0, "kmesh": [5, 5, 1],
            "potcar_bundle_sha256": receipt["remote"]["files"]["POTCAR"]["sha256"],
            "slab_model": "fe45_bottom18_fixed", "clean_slab_sha256": clean["sha256"],
            "cell_angstrom": slab.cell.tolist(), "slab_layers": 5,
            "fixed_atom_indices_zero_based": list(range(18)), "ldipol": False,
            "vacuum_thickness_angstrom": float(slab.cell[2, 2] - (cart[:, 2].max() - cart[:, 2].min())),
            "coverage": "3x3_one_" + record["formula"], "magnetic_state": "ispin2_Fe2p2_adsorbate0_seed",
            "ismear": 1, "sigma_ev": .2, "ediff_ev": 1e-5, "force_threshold_ev_per_A": .02,
            "final_energy_convention": "fe110_converged_toten_sigma0p20_v1"}


def check_decision(record, decision, scheduler=None):
    verdict = decision["decision"]
    if verdict not in {"accept", "duplicate", "reject", "needs_review"}:
        raise ValueError("unsupported scientific decision")
    if verdict == "accept" and (not record["eligible_for_review"] or record["duplicate_of"]):
        raise ValueError("cannot accept a blocked or duplicate calculation")
    if verdict == "duplicate" and not record["duplicate_of"]:
        raise ValueError("duplicate decision lacks a surface-aware match")
    if verdict == "accept" and (not scheduler or scheduler["status"] != "DONE"):
        raise ValueError("active production policy requires recorded scheduler DONE review")
    return verdict


def checked_receipt(record):
    directory = Path(record["directory"])
    receipt = load_json_object(directory / "collection.json")
    if sha256_file(directory / "collection.json") != record["collection_sha256"]:
        raise ValueError("collection receipt changed after analysis")
    for filename, meta in receipt["remote"]["files"].items():
        if filename != "POTCAR" and sha256_file(directory / filename) != meta["sha256"]:
            raise ValueError("scientific source changed")
    if not all(record["compatibility_checks"].values()):
        raise ValueError("incompatible branch requires a separate truthful registration batch")
    return directory, receipt


def prepare(analysis_path, decisions_path, database, output):
    if output.exists():
        raise FileExistsError(output)
    analysis = load_json_object(analysis_path)
    decisions = load_json_object(decisions_path)
    if decisions["analysis_sha256"] != sha256_file(analysis_path):
        raise ValueError("scientific decisions are stale")
    for source in decisions.get("source_files", []):
        if sha256_file(Path(source["path"])) != source["sha256"]:
            raise ValueError("review source changed")
    records = analysis["records"]
    if set(decisions["decisions"]) != {r["name"] for r in records}:
        raise ValueError("each analyzed calculation needs an explicit review")
    reviewer, now = decisions["reviewer"], decisions["reviewed_at"]
    rows = {key: [] for key in ("files", "results", "reviews", "calculation_compatibility", "job_status_history")}
    changes, provenance = [], {}
    with open_registry(database) as connection:
        max_event = connection.execute("SELECT coalesce(max(status_event_id),0) FROM job_status_history").fetchone()[0]
        for index, record in enumerate(records):
            name = record["name"]
            decision = decisions["decisions"][name]
            verdict = check_decision(record, decision, decisions["scheduler"][record["job_id"]])
            directory, receipt = checked_receipt(record)
            calc = connection.execute("SELECT calculation_id,workflow_status FROM calculations WHERE calculation_id=?",
                                      ("fe110_five_c2_adsorption_20261006_" + name,)).fetchone()
            if calc is None:
                raise ValueError("missing original calculation registration")
            cid, status = calc["calculation_id"], calc["workflow_status"]
            job = "lsf_" + record["job_id"]
            prefix = cid + "_completion_20261012"
            for filename, meta in receipt["remote"]["files"].items():
                is_potcar = filename == "POTCAR"
                rows["files"].append({"file_id": prefix + "_" + filename, "calculation_id": cid,
                    "job_record_id": job, "role": "licensed_input_metadata" if is_potcar else "completion_evidence",
                    "filename": filename, "local_path": None if is_potcar else str(directory / filename),
                    "remote_path": receipt["remote"]["directory"] + "/" + filename,
                    "storage_mode": "remote_only" if is_potcar else "local_and_remote", **meta,
                    "existence_status": "confirmed", "license_or_sensitivity": "licensed_POTCAR_content_not_copied" if is_potcar else None})
            comp = compatibility(record, receipt, analysis)
            rows["calculation_compatibility"].append({"calculation_id": cid, "compatibility_fingerprint": sha256_json(comp),
                    "compatibility_json": json.dumps(comp, sort_keys=True, separators=(",", ":")), "reviewer": reviewer, "reviewed_at": now})
            review_path = output.parent / "scientific_reviews" / (name + ".json")
            review = {"record": record, "decision": decision, "reviewer": reviewer, "reviewed_at": now,
                      "analysis_sha256": sha256_file(analysis_path), "decisions_sha256": sha256_file(decisions_path)}
            if review_path.exists():
                if load_json_object(review_path) != review:
                    raise ValueError("preserve existing scientific review; use a new version")
            else:
                write_json_atomic(review_path, review, ensure_ascii=True)
            rows["files"].append({"file_id": prefix + "_scientific_review", "calculation_id": cid,
                "job_record_id": job, "role": "scientific_review", "filename": review_path.name,
                "local_path": str(review_path.resolve()), "storage_mode": "local_only", "byte_size": review_path.stat().st_size,
                "sha256": sha256_file(review_path), "existence_status": "confirmed"})
            rows["reviews"].append({"review_id": prefix + "_review", "calculation_id": cid,
                "review_type": "adsorption_completion_chemistry_compatibility_and_duplicate",
                "decision": verdict, "reviewer": reviewer, "reviewed_at": now,
                "evidence": str(review_path.resolve()) + "#sha256=" + sha256_file(review_path), "reason": decision["reason"]})
            scheduler = decisions["scheduler"][record["job_id"]]
            rows["job_status_history"].append({"status_event_id": max_event + index + 1,
                "job_record_id": job, "scheduler_status": scheduler["status"],
                "scientific_status": "converged_" + verdict, "checked_at": now,
                "source_command": scheduler["source_command"], "source_text": scheduler["source_text"],
                "reviewer": reviewer, "notes": scheduler["notes"]})
            targets = {"accept": ["accepted"], "duplicate": ["done", "duplicate"],
                       "reject": ["needs_review", "rejected"], "needs_review": ["needs_review"]}[verdict]
            for step, target in enumerate(targets):
                if status == target:
                    continue
                changes.append({"status_change_id": prefix + "_status_" + str(step), "calculation_id": cid,
                    "expected_workflow_status": status, "new_workflow_status": target,
                    "changed_at": now, "reviewer": reviewer, "reason": decision["reason"]})
                status = target
            if verdict != "accept":
                continue
            validation = {"owner": "vasp_relaxation", "directory": str(directory),
                          "source_files": {f: receipt["remote"]["files"][f]["sha256"] for f in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")},
                          "completion_review_sha256": sha256_file(review_path)}
            for kind, value, unit, accepted in [("final_toten", record["final_toten_eV"], "eV", True),
                                                ("final_max_movable_force", record["fmax_movable_eV_A"], "eV/angstrom", False)]:
                result = {"result_id": prefix + "_" + kind, "calculation_id": cid, "result_name": kind,
                    "numeric_value": value, "unit": unit, "source_file_id": prefix + "_OUTCAR",
                    "reference_convention": comp["final_energy_convention"] if accepted else "movable_atoms_vector_norm",
                    "source_locator": "final free energy TOTEN" if accepted else "final TOTAL-FORCE block; Fe0-17 excluded",
                    "extraction_method": "scripts.aqcat25_calibration.parse_final_outcar with reviewed VASP relaxation evidence",
                    "validation_status": "accepted_compatible_final_energy" if accepted else "reviewed",
                    "created_at": now, "notes": "Adsorption reference tuple and thermal corrections not inferred."}
                rows["results"].append(result)
                provenance[result["result_id"]] = result_evidence(result, validation, comp, review_path, reviewer, now)
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
             "batch_id": decisions.get("batch_id", "fe110_five_c2_completion_review_20261012"), "created_at": now,
             "reviewer": reviewer, "reason": decisions["authorizing_user_request"], "rows": rows,
             "workflow_status_changes": changes, "result_provenance": provenance}
    write_json_atomic(output, batch, ensure_ascii=True)
    return {"calculations_reviewed": len(records), "accepted_final_energies": sum(r["decision"] == "accept" for r in decisions["decisions"].values()),
            "results": len(rows["results"]), "registry_written": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.analysis, args.decisions, args.db, args.output)))


if __name__ == "__main__":
    main()
