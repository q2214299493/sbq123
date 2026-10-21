"""Prepare truthful06 endpoint records and a separate03 coadsorption interpretation."""
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import yaml

from archive.fe110_c2_dedup_20261021.review import analyze, CLEAN, POLICY
from archive.fe110_coads_registry_20261021.collect import BASE, OLD, OUT, ROOT
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, fe110_anchor_site_distances, read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.adsorption.prepare_completion_registration import checked_receipt, compatibility, result_evidence
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.vasp_result_gate import validate_vasp_relaxation
from scripts.workflow_geometry import minimum_image_delta_xy

DB = ROOT / "data/project_registry.sqlite3"
REVIEWER = "Codex adsorption owner review under explicit user registration authority"
CHILD = "fe110_five_c2_adsorption_20261006_03_cfg0_direct_vasp_CH_CO_reclassified_20261021"


def fragments(pose):
    symbols = expanded_symbols(pose)
    indices = list(range(45, len(symbols)))
    edges = connectivity(pose, indices)
    remaining = set(range(len(indices)))
    formulas = []
    while remaining:
        component = {remaining.pop()}
        while True:
            grown = component | {b if a in component else a for a, b in edges if a in component or b in component}
            if grown == component:
                break
            component = grown
        remaining -= component
        counts = Counter(symbols[indices[i]] for i in component)
        formulas.append("".join(s + (str(counts[s]) if counts[s] > 1 else "") for s in ("C", "H", "O") if counts[s]))
    return sorted(formulas)


def geometry(pose, slab):
    symbols = expanded_symbols(pose)
    ads = list(range(45, len(symbols)))
    edges = connectivity(pose, ads)
    contacts, angles = [], []
    for atom in ads:
        distances = np.linalg.norm(minimum_image_delta_xy(pose.frac[:45] - pose.frac[atom]) @ pose.cell, axis=1)
        site, offset = min(fe110_anchor_site_distances(slab, pose.frac[atom]).items(), key=lambda x: x[1])
        contacts.append({"atom_0based": atom, "symbol": symbols[atom], "nearest_Fe_0based": int(distances.argmin()),
                         "nearest_Fe_A": float(distances.min()), "nearest_projection": site, "offset_A": offset})
    for center in range(len(ads)):
        neighbors = [b if a == center else a for a, b in edges if center in (a, b)]
        for first, last in combinations(neighbors, 2):
            vectors = minimum_image_delta_xy(pose.frac[[ads[first], ads[last]]] - pose.frac[ads[center]]) @ pose.cell
            cosine = np.dot(*vectors) / np.prod(np.linalg.norm(vectors, axis=1))
            angles.append({"atoms_0based": [ads[first], ads[center], ads[last]],
                           "angle_degrees": float(np.degrees(np.arccos(np.clip(cosine, -1, 1))))})
    return {"fragments": fragments(pose), "contacts": contacts, "angles": angles}


def audit_original(original):
    old_audit = []
    for row in original["records"]:
        directory, _ = checked_receipt(row)
        pose = read_poscar(directory / "CONTCAR")
        old_audit.append({"name": row["name"], "job_id": row["job_id"], "fragments": fragments(pose),
                          "intended_graph_preserved": row["signature_match"], "duplicate_of": row["duplicate_of"],
                          "final_structure_sha256": sha256_file(directory / "CONTCAR")})
    changed = [r["name"] for r in old_audit if not r["intended_graph_preserved"]]
    if changed != ["03_cfg0_direct_vasp"]:
        raise ValueError("additional changed chemistry requires review:" + str(changed))
    return old_audit, changed


def main():
    if (OUT / "registry_batch.json").exists():
        raise FileExistsError("preserve prepared batch; inspect existing plan/receipt before resuming")
    (OUT / "scientific_reviews").mkdir(exist_ok=True)
    request = load_json_object(OUT / "request.json")
    previous = BASE / "dedup_final_review_20261021_v1"
    if (sha256_file(previous / "review.json") != request["prior_dedup_sha256"]
            or sha256_file(OLD / "final_analysis.json") != request["prior01_05_analysis_sha256"]):
        raise ValueError("previous review changed")
    slab = read_poscar(CLEAN)
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    inputs = load_json_object(previous / "request.json")
    current = {s["record"]["name"]: s for s in inputs["sources"]}
    reviewed06 = {name: analyze(current[name], slab, policy) for name in ("06_A", "06_B", "06_C")}
    original = load_json_object(OLD / "final_analysis.json")
    old_audit, changed = audit_original(original)
    old_record = next(r for r in original["records"] if r["name"] == changed[0])
    old_dir, old_receipt = checked_receipt(old_record)
    validate_vasp_relaxation(old_dir)
    scheduler = load_json_object(OUT / "scheduler.json")
    if scheduler["exit_code"] != 0 or any("Job <" + job + "> is not found" not in scheduler["stderr"] + scheduler["stdout"]
                                          for job in ("9848799", "9848800", "9848801")):
        raise ValueError("review scheduler observation before selecting UNKNOWN")
    rows = {k: [] for k in ("calculations", "job_status_history", "files", "results", "reviews", "calculation_compatibility")}
    changes, provenance, summary = [], {}, []
    now = datetime.now(timezone.utc).isoformat()
    with open_registry(DB) as connection:
        events = connection.execute("SELECT coalesce(max(status_event_id),0) FROM job_status_history").fetchone()[0]
        done03 = connection.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND scheduler_status=? ORDER BY status_event_id DESC LIMIT 1",
                                    ("lsf_9839757", "DONE")).fetchone()
        parent03 = connection.execute("SELECT * FROM calculations WHERE calculation_id=?",
                                       ("fe110_five_c2_adsorption_20261006_03_cfg0_direct_vasp",)).fetchone()
        if done03 is None or parent03["workflow_status"] != "rejected":
            raise ValueError("original03 scheduler/status review changed")
        if connection.execute("SELECT 1 FROM calculations WHERE calculation_id=?", (CHILD,)).fetchone():
            raise ValueError("reclassification already present; inspect receipt, do not duplicate")
        source_defs = []
        for name, row in reviewed06.items():
            job = connection.execute("SELECT * FROM jobs WHERE scheduler_job_id=?", (row["job_id"],)).fetchone()
            cid = job["calculation_id"]
            status = connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (cid,)).fetchone()[0]
            source = load_json_object(Path(row["source"]["path"]))
            receipt = {"remote": {"files": {"POTCAR": {"sha256": source["POTCAR_sha256"]}}}}
            definition = {"name": name, "cid": cid, "job": job["job_record_id"], "row": row,
                "directory": Path(row["directory"]), "receipt": receipt, "formula": "C2HO", "source": source,
                "status": status, "accepted": False, "scheduler": "UNKNOWN",
                "identity": "CO* + C* + H*" if name != "06_C" else "[C]O[CH]*",
                "expected_fragments": ["C", "CO", "H"] if name != "06_C" else ["C2HO"]}
            source_defs.append(definition)
        rows["calculations"].append({"calculation_id": CHILD, "module": "adsorption_workflow",
            "purpose": "reviewed_coadsorption_reclassification_of_existing_calculation_not_new_VASP",
            "scientific_system": "Fe110_5layer_3x3_CH* + CO*", "parent_calculation_id": parent03["calculation_id"],
            "workflow_status": "registered", "created_at": now, "source_record": str(old_dir / "collection.json"),
            "notes": "New interpretation only. Same job9839757/source outputs; no new compute. Original intact-target rejection preserved."})
        source_defs.append({"name": "03_CH_CO", "cid": CHILD, "job": "lsf_9839757", "row": old_record,
            "directory": old_dir, "receipt": old_receipt, "formula": "C2HO", "source": None, "status": "registered",
            "accepted": True, "scheduler": "DONE", "identity": "CH* + CO*", "expected_fragments": ["CH", "CO"]})
        for definition in source_defs:
            name, cid, directory = definition["name"], definition["cid"], definition["directory"]
            row, receipt, accepted = definition["row"], definition["receipt"], definition["accepted"]
            pose, initial = read_poscar(directory / "CONTCAR"), read_poscar(directory / "POSCAR")
            geom = geometry(pose, slab)
            if geom["fragments"] != definition["expected_fragments"]:
                raise ValueError("chemical assignment changed:" + name)
            prefix = cid + "_coads_review_20261021"
            comp = compatibility({"formula": definition["formula"]}, receipt,
                                 {"slab": {"path": str(CLEAN), "sha256": sha256_file(CLEAN)}})
            rows["calculation_compatibility"].append({"calculation_id": cid, "compatibility_fingerprint": sha256_json(comp),
                "compatibility_json": json.dumps(comp, sort_keys=True, separators=(",", ":")), "reviewer": REVIEWER, "reviewed_at": now})
            duplicate = name == "06_C"
            review = {"name": name, "source_job_record_id": definition["job"], "final_species": definition["identity"],
                "initial_species": current[name]["record"]["connectivity"] if name.startswith("06") else old_record["target_graph"],
                "initial_geometry": geometry(initial, slab), "final_geometry": geom,
                "plausibility_status": "RECLASSIFY" if name != "06_C" else "PASS",
                "chemical_event": "intact_adsorption" if name.startswith("06") else "dissociation",
                "initial06_reclassification_happened_before_VASP": name in {"06_A", "06_B"},
                "duplicate_of": "paired_06_C_candidate" if duplicate else None,
                "scientific_acceptance": accepted, "scheduler_status": definition["scheduler"],
                "blockers": ["terminal_scheduler_evidence_missing"] + (["duplicate_cluster_member"] if duplicate else []) if not accepted else [],
                "source_review": str(previous / "review.json") if name.startswith("06") else str(OLD / "final_analysis.json"),
                "source_review_sha256": sha256_file(previous / "review.json") if name.startswith("06") else sha256_file(OLD / "final_analysis.json"),
                "reviewer": REVIEWER, "reviewed_at": now, "source_record": row,
                "source_interpretation_does_not_change_original_rejected_workflow": name == "03_CH_CO"}
            review_path = OUT / "scientific_reviews" / (name + ".json")
            write_json_exclusive(review_path, review)
            file_meta = receipt["remote"]["files"] if accepted else {
                **{f: {"sha256": sha256_file(directory / f), "byte_size": (directory / f).stat().st_size}
                   for f in ("INCAR", "POSCAR", "CONTCAR", "KPOINTS", "OSZICAR")},
                "OUTCAR": {"sha256": definition["source"]["OUTCAR_sha256"], "byte_size": definition["source"]["OUTCAR_bytes"]},
                "POTCAR": {"sha256": definition["source"]["POTCAR_sha256"]}}
            remote = old_receipt["remote"]["directory"] if accepted else current[name]["record"]["remote_dir"]
            for filename, meta in file_meta.items():
                local = None if filename == "POTCAR" or (not accepted and filename == "OUTCAR") else str(directory / filename)
                rows["files"].append({"file_id": prefix + "_" + filename, "calculation_id": cid,
                    "job_record_id": definition["job"], "role": "licensed_input_metadata" if filename == "POTCAR" else "completion_evidence",
                    "filename": filename, "local_path": local, "remote_path": remote + "/" + filename,
                    "storage_mode": "local_and_remote" if local else "remote_only", **meta, "existence_status": "confirmed",
                    "notes": "Hash-bound earlier collection; renewed remote hash read timed out." if not accepted else "Existing original-byte collection reused."})
            for label, path in [("scientific_review", review_path)] + ([] if accepted else [("compact_source", Path(row["source"]["path"]))]):
                rows["files"].append({"file_id": prefix + "_" + label, "calculation_id": cid, "job_record_id": definition["job"],
                    "role": label, "filename": path.name, "local_path": str(path), "storage_mode": "local_only",
                    "sha256": sha256_file(path), "byte_size": path.stat().st_size, "existence_status": "confirmed"})
            verdict = "accept" if accepted else "duplicate" if duplicate else "needs_review"
            reason = "Accept actual CH*+CO* state; preserve original intact-target rejection." if accepted else "Register reviewed endpoint identity/values; scheduler UNKNOWN is not fabricated as DONE."
            rows["reviews"].append({"review_id": prefix + "_review", "calculation_id": cid,
                "review_type": "adsorption_final_chemistry_and_provenance_registration", "decision": verdict,
                "reviewer": REVIEWER, "reviewed_at": now, "evidence": str(review_path) + "#sha256=" + sha256_file(review_path), "reason": reason})
            targets = ["accepted"] if accepted else ["needs_review", "duplicate"] if duplicate else ["needs_review"]
            status = definition["status"]
            for index, target in enumerate(targets):
                changes.append({"status_change_id": prefix + "_status" + str(index), "calculation_id": cid,
                    "expected_workflow_status": status, "new_workflow_status": target, "changed_at": now,
                    "reviewer": REVIEWER, "reason": reason})
                status = target
            if not accepted:
                events += 1
                rows["job_status_history"].append({"status_event_id": events, "job_record_id": definition["job"],
                    "scheduler_status": "UNKNOWN", "scientific_status": "converged_" + verdict, "checked_at": now,
                    "source_command": " ".join(scheduler["command"]), "source_text": scheduler["stdout"] + scheduler["stderr"],
                    "reviewer": REVIEWER, "notes": "Old job not found; normal OUTCAR termination is not scheduler DONE."})
            validation = {"owner": "vasp_relaxation", "directory": str(directory),
                "source_files": {f: file_meta[f]["sha256"] for f in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")}}
            values = [("final_toten", row["final_toten_eV"] if accepted else row["toten_eV"], None, "eV", "OUTCAR"),
                ("final_max_movable_force", row["fmax_movable_eV_A"] if accepted else row["fmax_eV_A"], None, "eV/angstrom", "OUTCAR"),
                ("final_state_identity", None, json.dumps({"final_species": definition["identity"], "fragments": geom["fragments"],
                    "final_site": geom["contacts"], "duplicate_of": review["duplicate_of"]}, ensure_ascii=True), None, "CONTCAR")]
            for kind, number, text, unit, filename in values:
                is_energy = kind == "final_toten"
                result = {"result_id": prefix + "_" + kind, "calculation_id": cid, "result_name": kind,
                    "numeric_value": number, "text_value": text, "unit": unit, "source_file_id": prefix + "_" + filename,
                    "reference_convention": comp["final_energy_convention"] if is_energy else "reviewed_final_geometry_or_movable_force",
                    "source_locator": "final free energy TOTEN" if is_energy else "final CONTCAR/TOTAL-FORCE; Fe0-17 fixed",
                    "extraction_method": "canonical adsorption review and exact hash-bound VASP evidence",
                    "validation_status": "accepted_compatible_final_energy" if accepted and is_energy else "reviewed",
                    "created_at": now, "notes": reason + " No adsorption-energy reference tuple or thermal correction inferred."}
                rows["results"].append(result)
                provenance[result["result_id"]] = result_evidence(result, validation, comp, review_path, REVIEWER, now)
            summary.append({"name": name, "calculation_id": cid, "final_species": definition["identity"],
                            "workflow_status": status, "scheduler": definition["scheduler"], "accepted_energy": accepted})
    write_json_exclusive(OUT / "old01_05_audit.json", {"records": old_audit, "missing_coadsorption_sources": changed,
        "original_analysis_sha256": sha256_file(OLD / "final_analysis.json"), "original_rejected_record_preserved": True})
    write_json_exclusive(OUT / "registry_batch.json", {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_06abc_and_03_coads_reclassification_20261021_v1", "created_at": now,
        "reviewer": REVIEWER, "reason": request["authorizing_user_request"], "rows": rows,
        "workflow_status_changes": changes, "result_provenance": provenance})
    write_json_exclusive(OUT / "preparation_summary.json", {"records": summary, "registry_written": False,
        "source_sha256": sha256_file(Path(__file__)), "new_scientific_jobs": 0})
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
