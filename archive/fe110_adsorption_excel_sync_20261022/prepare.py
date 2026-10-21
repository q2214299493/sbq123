"""Prepare the bounded nine accepted rows and three nonnumeric pending-view records."""
from datetime import datetime, timezone
from pathlib import Path
import json

from archive.fe110_coads_registry_20261021.prepare import geometry
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/adsorption_table_sync_20261022_v1"
BOOK = ROOT / "outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx"
DB = ROOT / "data/project_registry.sqlite3"
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/final_review_20261012"
RECENT = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/coadsorption_registration_20261021_v1"
REVIEWER = "Codex under user authority to complete database-to-adsorption-table registration"
HEADERS = ["吸附物", "最终位点", "吸附反应", "吸附产物", "任务号", "F能量 (eV)", "E0能量 (eV)", "吸附能 Eads (eV)"]


def main():
    OUT.mkdir(exist_ok=True)
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    records = {r["name"]: r for r in load_json_object(OLD / "final_analysis.json")["records"]}
    accepted, pending = [], []
    now = datetime.now(timezone.utc).isoformat()
    with open_registry(DB) as connection:
        calculations = [dict(r) for r in connection.execute(
            "SELECT * FROM calculations WHERE calculation_id LIKE ? AND workflow_status=? ORDER BY calculation_id",
            ("fe110_five_c2_adsorption_20261006_%", "accepted"))]
        if len(calculations) != 9:
            raise ValueError("expected eight original accepted targets plus one reclassified state; review changed state")
        for index, calculation in enumerate(calculations):
            cid = calculation["calculation_id"]
            energy = connection.execute("SELECT * FROM results WHERE calculation_id=? AND result_name=? AND validation_status=?",
                                        (cid, "final_toten", "accepted_compatible_final_energy")).fetchall()
            if len(energy) != 1 or energy[0]["unit"] != "eV":
                raise ValueError("unique accepted energy required")
            if connection.execute("SELECT 1 FROM excel_promotions WHERE registry_id=?", (cid,)).fetchone():
                raise ValueError("already promoted; inspect prior receipt before resuming:" + cid)
            child = "_CH_CO_reclassified_" in cid
            name = "03_cfg0_direct_vasp" if child else cid.removeprefix("fe110_five_c2_adsorption_20261006_")
            source = records[name]
            directory = Path(source["directory"])
            collection = load_json_object(directory / "collection.json")
            if sha256_file(directory / "CONTCAR") != collection["remote"]["files"]["CONTCAR"]["sha256"]:
                raise ValueError("reviewed geometry changed")
            contacts = geometry(read_poscar(directory / "CONTCAR"), slab)["contacts"]
            sites = "; ".join(f"{r['symbol']}{r['atom_0based']}:{'raised' if r['nearest_Fe_A'] > 2.7 else r['nearest_projection']}"
                              for r in contacts if r["symbol"] != "H")
            identity = "CH*+CO*" if child else source["target_graph"] + "*"
            labels = ["CH+CO" if child else source["formula"], sites,
                      "Fe(110) + " + source["target_graph"] + " → " + identity + "/Fe(110)",
                      identity + "/Fe(110)", source["job_id"], None, "未登记", "缺兼容参考能"]
            columns = [{"header": header, "source": {"type": "result", "result_id": energy[0]["result_id"]}
                        if position == 5 else {"type": "reviewed_metadata", "value": labels[position]}}
                       for position, header in enumerate(HEADERS)]
            promotion_id = f"c2-ads-table-sync-20261022-{index + 1:02d}"
            request = {"schema_version": 1, "promotion_id": promotion_id, "promotion_kind": "adsorption",
                "registry_id": cid, "workbook": {"path": str(BOOK), "worksheet_name": "最终吸附数据",
                    "header_row": 2, "headers": HEADERS}, "columns": columns,
                "review": {"decision": "approve", "reviewer": REVIEWER, "reviewed_at": now},
                "receipt_path": str(OUT / (promotion_id + ".receipt.json")),
                "notes": "User requested complete registration in the visible adsorption table; only accepted final TOTEN is numeric. No E0 or Eads inferred."}
            request_path = OUT / (promotion_id + ".request.json")
            write_json_exclusive(request_path, request)
            accepted.append({"name": name, "calculation_id": cid, "request": str(request_path),
                             "source_job_id": source["job_id"], "accepted_result_id": energy[0]["result_id"],
                             "toten_eV": energy[0]["numeric_value"]})
        for name in ("06_A", "06_B", "06_C"):
            cid = "fe110_c2_06_10_adsorption_20261013_" + name
            calculation = connection.execute("SELECT * FROM calculations WHERE calculation_id=?", (cid,)).fetchone()
            metadata = connection.execute("SELECT text_value FROM results WHERE calculation_id=? AND result_name=?", (cid, "final_state_identity")).fetchone()
            job = connection.execute("SELECT scheduler_job_id FROM jobs WHERE calculation_id=?", (cid,)).fetchone()[0]
            state = json.loads(metadata[0])
            pending.append([name, state["final_species"], str(job),
                "重复来源（保留记录）" if calculation["workflow_status"] == "duplicate" else "已登记，待正式接受",
                "缺LSF终态历史" + ("；与paired_06_C_candidate同态" if name == "06_C" else ""), cid])
    write_json_exclusive(OUT / "sync_manifest.json", {"accepted": accepted, "pending_metadata_rows": pending,
        "pending_values_are_metadata_only": True, "workbook": str(BOOK), "workbook_sha256_before": sha256_file(BOOK),
        "source_sha256": sha256_file(Path(__file__)), "reviewer": REVIEWER, "reviewed_at": now,
        "original_rows": 55, "new_scientific_jobs": 0})
    print("PREPARED", len(accepted), "ACCEPTED_ROWS", len(pending), "PENDING_METADATA_ROWS")


if __name__ == "__main__":
    main()
