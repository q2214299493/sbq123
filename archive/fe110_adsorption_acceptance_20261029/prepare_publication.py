"""Bind three accepted registry energies and truthful nonnumeric pending updates."""
from __future__ import annotations

from pathlib import Path

import yaml

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

from .collect import BASE, BOOK, DB, OUT
from .review import CLEAN, POLICY

HEADERS = ["吸附物", "最终位点", "吸附反应", "吸附产物", "任务号", "F能量 (eV)", "E0能量 (eV)", "吸附能 Eads (eV)"]
ORDER = ["paired_06_C_baseline", "paired_09_C_baseline", "ft512_10_A"]


def main():
    destination = OUT / "publication_manifest.json"
    if destination.exists():
        raise FileExistsError(destination)
    initial = load_json_object(OUT / "sources.json")
    if sha256_file(BOOK) != initial["workbook_sha256_before"]:
        raise ValueError("workbook changed: review the new saved baseline before preparing publication")
    analysis = load_json_object(OUT / "analysis.json")
    decisions = load_json_object(OUT / "decisions.json")
    records = {r["name"]: r for r in analysis["records"]}
    sources = {r["name"]: r for r in initial["records"]}
    reviewer, reviewed_at = decisions["reviewer"], decisions["reviewed_at"]
    accepted = []
    with open_registry(DB) as connection:
        connection.execute("PRAGMA query_only=ON")
        for index, name in enumerate(ORDER):
            record = records[name]
            cid = record["calculation_id"]
            calculation = connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (cid,)).fetchone()
            results = connection.execute("SELECT * FROM results WHERE calculation_id=? AND result_name='final_toten' AND validation_status='accepted_compatible_final_energy'", (cid,)).fetchall()
            if calculation[0] != "accepted" or len(results) != 1 or results[0]["numeric_value"] != record["toten_eV"]:
                raise ValueError("formal accepted registry binding missing")
            if connection.execute("SELECT 1 FROM excel_promotions WHERE registry_id=?", (cid,)).fetchone():
                raise ValueError("already published: inspect its receipt before resuming")
            contacts = record["measurements"]["contacts"]
            sites = "; ".join(f"{c['symbol']}{c['atom_0based']}:{c['nearest_projection']}"
                              for c in contacts if c["symbol"] != "H")
            identity = record["target_graph"] + "*"
            labels = [record["formula"], sites, "Fe(110) + " + record["target_graph"] + " → " + identity + "/Fe(110)",
                      identity + "/Fe(110)", record["job_id"], None, "未登记", "缺兼容参考能"]
            promotion_id = f"c2-final-acceptance-table-20261029-{index + 1:02d}"
            request = {"schema_version": 1, "promotion_id": promotion_id, "promotion_kind": "adsorption", "registry_id": cid,
                "workbook": {"path": str(BOOK), "worksheet_name": "最终吸附数据", "header_row": 2, "headers": HEADERS},
                "columns": [{"header": header, "source": {"type": "result", "result_id": results[0]["result_id"]}
                    if i == 5 else {"type": "reviewed_metadata", "value": labels[i]}} for i, header in enumerate(HEADERS)],
                "review": {"decision": "approve", "reviewer": reviewer, "reviewed_at": reviewed_at},
                "receipt_path": str(OUT / (promotion_id + ".receipt.json")),
                "notes": "Explicitly reviewed final TOTEN only; no E0, Eads, vibrational or global-minimum claim."}
            request_path = OUT / (promotion_id + ".request.json")
            write_json_exclusive(request_path, request)
            accepted.append({"name": name, "calculation_id": cid, "job_id": record["job_id"],
                "result_id": results[0]["result_id"], "toten_eV": record["toten_eV"], "row": 65 + index,
                "request": str(request_path), "promotion_id": promotion_id})
    old_path = BASE / "dedup_final_review_20261021_v1/review.json"
    original = {r["name"]: r for r in load_json_object(old_path)["rows"] if r["cohort"] == "original15"}
    associations = []
    rules = yaml.safe_load(POLICY.read_text())["duplicate_detection"]
    operations = surface_pose_symmetries(read_poscar(CLEAN))
    for old_name, new_name in (("06_C", ORDER[0]), ("09_C", ORDER[1]), ("10_A", ORDER[2])):
        old, new = original[old_name], records[new_name]
        metrics = surface_equivalence(read_poscar(Path(old["directory"]) / "CONTCAR"),
            read_poscar(Path(new["directory"]) / "CONTCAR"), read_poscar(CLEAN), operations)
        delta = abs(old["toten_eV"] - new["toten_eV"])
        if max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= rules["geometry_rmsd_tolerance_angstrom"] and delta <= rules["energy_tolerance_ev"]:
            associations.append({"original": old_name, "accepted_name": new_name, **metrics, "energy_difference_eV": delta})
    associations_by_name = {r["original"]: r for r in associations}
    main_by_name = {r["name"]: r for r in accepted}
    pending_updates = []
    expected_pending = []
    for index, name in enumerate(f"{n:02d}_{letter}" for n in range(6, 11) for letter in "ABC"):
        source = sources[name]
        expected_pending.append([name, source["job_id"], source["calculation_id"]])
        if not original[name]["technical_convergence"]:
            continue
        reason = "缺历史LSF DONE证据；本条尚未正式接受"
        if name in associations_by_name:
            main = main_by_name[associations_by_name[name]["accepted_name"]]
            reason = f"缺原作业LSF终态；同态代表见主表第{main['row']}行"
        elif name in {"08_B", "08_C"}:
            reason += "；B/C近重复，暂不合并"
        elif name == "09_B":
            reason = "与07_A同态；缺历史LSF DONE证据，保留重复关联"
        pending_updates.append({"row": 5 + index, "job_id": source["job_id"], "reason": reason})
    pending_rows = []
    uncollected = sources["paired_06_C_candidate"]
    pending_rows.append(["06_C候选（配对）", "[C]O[CH]*", uncollected["job_id"], "待正式接受",
        "缺历史LSF DONE证据；保留既有结构审核", uncollected["calculation_id"]])
    for name, label in (("paired_09_C_candidate", "09_C候选（配对）"),
                        ("paired_10_A_baseline", "10_A基线（配对）"),
                        ("paired_10_A_candidate", "10_A候选（配对）")):
        record = records[name]
        representative = main_by_name[decisions["decisions"][name]["duplicate_of"]]
        pending_rows.append([label, record["target_graph"] + "*", record["job_id"], "重复来源（已审核）",
            f"同态代表见主表第{representative['row']}行；不增加独立构型", record["calculation_id"]])
    write_json_exclusive(destination, {"workbook": str(BOOK), "workbook_sha256_before": sha256_file(BOOK),
        "accepted": accepted, "expected_pending": expected_pending, "pending_updates": pending_updates,
        "pending_append": pending_rows, "associations": associations, "original_review_sha256": sha256_file(old_path),
        "analysis_sha256": sha256_file(OUT / "analysis.json"), "decisions_sha256": sha256_file(OUT / "decisions.json"),
        "formal_original_rows": 64, "formal_last_row": 67, "pending_original_rows": 19,
        "pending_last_row": 23, "new_scientific_jobs": 0})
    print("PREPARED three accepted-result requests; four nonnumeric pending rows; original identities preserved")


if __name__ == "__main__":
    main()
