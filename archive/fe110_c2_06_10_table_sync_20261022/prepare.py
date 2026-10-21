"""Incrementally register07–10 reviewed evidence and prepare all15 metadata rows."""
from datetime import datetime, timezone
import json
from pathlib import Path

import yaml

from archive.fe110_c2_dedup_20261021.review import analyze, CLEAN, DEST, POLICY
from archive.fe110_coads_registry_20261021.prepare import fragments
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.prepare_completion_registration import compatibility, result_evidence
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.registry_connection import open_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/adsorption_table_06_10_sync_20261022_v1"
BOOK = ROOT / "outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx"
DB = ROOT / "data/project_registry.sqlite3"
REVIEWER = "Codex under user authority to complete06–10 registry/table records"
PREFIX = "fe110_c2_06_10_adsorption_20261013_"


def presentation(row, component_formulas):
    identity = row["target_graph"] + "*" if len(component_formulas) == 1 else " + ".join(f + "*" for f in component_formulas)
    if row["name"] == "09_B":
        return identity, "重复来源（关联07_A）", "与07_A同一CH2+CO终态；不增加独立构型"
    if not row["technical_convergence"]:
        return identity, "未收敛，不作稳定态", f"{row['ionic_steps']}步；最大力{row['fmax_eV_A']:.6f} eV/Å；仅留末步快照"
    note = "收敛审核通过；尚未形成正式接受能量记录"
    if row["name"] in {"08_B", "08_C"}:
        note += "；B/C近重复，暂不合并"
    status = "重分类共吸附，待正式接受" if row["eligible_reclassified_review"] else "已收敛，待正式接受"
    return identity, status, note


def add_record(rows, provenance, item, row, now, slab, current_status):
    name = row["name"]
    cid = PREFIX + name
    source = load_json_object(Path(row["source"]["path"]))
    directory = Path(row["directory"])
    final = read_poscar(directory / "CONTCAR")
    components = fragments(final)
    identity, display_status, note = presentation(row, components)
    duplicate = name == "09_B"
    prefix = cid + "_table_completion_20261022"
    review = {"name": name, "record": row, "final_species": identity, "components": components,
        "plausibility_status": "RECLASSIFY" if not row["target_preserved"] else "PASS",
        "chemical_event": "intact_adsorption" if row["submitted_graph_preserved"] else "dissociation",
        "reclassification_before_VASP": not row["target_preserved"] and row["submitted_graph_preserved"],
        "duplicate_of": PREFIX + "07_A" if duplicate else None,
        "display_status": display_status, "reason": note, "scientific_acceptance": False,
        "reviewer": REVIEWER, "reviewed_at": now,
        "prior_review_sha256": sha256_file(DEST / "review.json"),
        "boundary": "No scheduler observation invented; existing historical queue records remain unchanged."}
    review_path = OUT / "scientific_reviews" / (name + ".json")
    write_json_exclusive(review_path, review)
    comp = compatibility({"formula": row["formula"]}, {"remote": {"files": {"POTCAR": {"sha256": source["POTCAR_sha256"]}}}},
                         {"slab": {"path": str(CLEAN), "sha256": sha256_file(CLEAN)}})
    rows["calculation_compatibility"].append({"calculation_id": cid, "compatibility_fingerprint": sha256_json(comp),
        "compatibility_json": json.dumps(comp, sort_keys=True, separators=(",", ":")), "reviewer": REVIEWER, "reviewed_at": now})
    metadata = {f: {"sha256": sha256_file(directory / f), "byte_size": (directory / f).stat().st_size}
                for f in ("INCAR", "POSCAR", "CONTCAR", "KPOINTS", "OSZICAR")}
    metadata.update(OUTCAR={"sha256": source["OUTCAR_sha256"], "byte_size": source["OUTCAR_bytes"]},
                    POTCAR={"sha256": source["POTCAR_sha256"]})
    for filename, meta in metadata.items():
        local = None if filename in {"OUTCAR", "POTCAR"} else str(directory / filename)
        rows["files"].append({"file_id": prefix + "_" + filename, "calculation_id": cid,
            "job_record_id": "lsf_" + row["job_id"], "role": "licensed_input_metadata" if filename == "POTCAR" else "completion_evidence",
            "filename": filename, "local_path": local, "remote_path": item["record"]["remote_dir"] + "/" + filename,
            "storage_mode": "local_and_remote" if local else "remote_only", **meta, "existence_status": "confirmed",
            "notes": "Existing hash-bound closed-result snapshot reused; no renewed remote observation claimed."})
    for label, path in (("scientific_review", review_path), ("compact_source", Path(row["source"]["path"]))):
        rows["files"].append({"file_id": prefix + "_" + label, "calculation_id": cid, "job_record_id": "lsf_" + row["job_id"],
            "role": label, "filename": path.name, "local_path": str(path), "storage_mode": "local_only",
            "sha256": sha256_file(path), "byte_size": path.stat().st_size, "existence_status": "confirmed"})
    rows["reviews"].append({"review_id": prefix + "_review", "calculation_id": cid,
        "review_type": "adsorption_completion_identity_convergence_and_duplicate", "decision": "duplicate" if duplicate else "needs_review",
        "reviewer": REVIEWER, "reviewed_at": now, "evidence": str(review_path) + "#sha256=" + sha256_file(review_path), "reason": note})
    validation = {"owner": "vasp_relaxation", "directory": str(directory),
                  "source_files": {f: metadata[f]["sha256"] for f in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")}}
    values = [("final_toten" if row["technical_convergence"] else "last_toten", row["toten_eV"], None, "eV", "OUTCAR"),
              ("final_max_movable_force", row["fmax_eV_A"], None, "eV/angstrom", "OUTCAR"),
              ("final_state_identity", None, json.dumps({"final_species": identity, "components": components,
                  "converged": row["technical_convergence"], "duplicate_of": review["duplicate_of"]}, ensure_ascii=True), None, "CONTCAR")]
    for kind, number, text, unit, filename in values:
        result = {"result_id": prefix + "_" + kind, "calculation_id": cid, "result_name": kind,
            "numeric_value": number, "text_value": text, "unit": unit, "source_file_id": prefix + "_" + filename,
            "reference_convention": comp["final_energy_convention"] if "toten" in kind else "reviewed_final_geometry_or_movable_force",
            "source_locator": "last complete OUTCAR force/energy block; linked CONTCAR", "extraction_method": "canonical source-bound adsorption completion review",
            "validation_status": "reviewed", "created_at": now, "notes": note + "; not an accepted energy or adsorption-energy derivation."}
        rows["results"].append(result)
        provenance[result["result_id"]] = result_evidence(result, validation, comp, review_path, REVIEWER, now)
    targets = ["needs_review", "duplicate"] if duplicate else ["needs_review"]
    changes = []
    for index, target in enumerate(targets):
        changes.append({"status_change_id": prefix + "_status" + str(index), "calculation_id": cid,
            "expected_workflow_status": current_status, "new_workflow_status": target, "changed_at": now,
            "reviewer": REVIEWER, "reason": note})
        current_status = target
    return changes, [name, identity, row["job_id"], display_status, note, cid]


def main():
    OUT.mkdir(exist_ok=False)
    (OUT / "scientific_reviews").mkdir()
    request = load_json_object(DEST / "request.json")
    prior = load_json_object(DEST / "review.json")
    if sha256_file(CLEAN) != prior["clean_sha256"] or sha256_file(POLICY) != prior["policy_sha256"]:
        raise ValueError("review clean/policy changed")
    items = [item for item in request["sources"] if item["record"]["cohort"] == "original15" and not item["record"]["name"].startswith("06_")]
    if len(items) != 12:
        raise ValueError("exact twelve missing records required")
    slab = read_poscar(CLEAN)
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    rows = {key: [] for key in ("files", "results", "reviews", "calculation_compatibility")}
    changes, provenance, sheet_rows = [], {}, []
    now = datetime.now(timezone.utc).isoformat()
    with open_registry(DB) as connection:
        for item in items:
            name = item["record"]["name"]
            cid = PREFIX + name
            calculation = connection.execute("SELECT * FROM calculations WHERE calculation_id=?", (cid,)).fetchone()
            if calculation is None or calculation["workflow_status"] != "submitted":
                raise ValueError("existing result/status needs reconciliation:" + name)
            if connection.execute("SELECT 1 FROM results WHERE calculation_id=? LIMIT 1", (cid,)).fetchone():
                raise ValueError("preserve existing results; do not duplicate:" + name)
            row = analyze(item, slab, policy)
            updates, display = add_record(rows, provenance, item, row, now, slab, calculation["workflow_status"])
            changes.extend(updates)
            sheet_rows.append(display)
    write_json_exclusive(OUT / "registry_batch.json", {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_07_10_reviewed_results_table_sync_20261022_v1", "created_at": now, "reviewer": REVIEWER,
        "reason": "User requested06–10 together in the adsorption table; register missing07–10 evidence without scientific promotion.",
        "rows": rows, "workflow_status_changes": changes, "result_provenance": provenance})
    write_json_exclusive(OUT / "sheet_manifest.json", {"workbook": str(BOOK), "workbook_sha256_before": sha256_file(BOOK),
        "append_rows": sheet_rows, "expected_existing_names": ["06_A", "06_B", "06_C"],
        "prior_review_sha256": sha256_file(DEST / "review.json"), "source_sha256": sha256_file(Path(__file__)),
        "all15_names": [f"{species:02d}_{letter}" for species in range(6, 11) for letter in "ABC"],
        "numeric_formal_energies_added": 0, "new_scientific_jobs": 0})
    print("PREPARED12 missing reviewed results;15-record table scope;no accepted-energy promotion")


if __name__ == "__main__":
    main()
