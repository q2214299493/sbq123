"""Verify committed accepted barrier/template pairs against the reviewed files."""
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.ts_strategy_engine.templates import load_templates
from scripts.ts_strategy_engine.matched_static_evidence import matched_static_convention, matched_static_rows

from .refresh import OUTPUT, PREP, binding
from .register import DB, CONVENTION


def verify():
    requests = load_json_object(OUTPUT / "barrier_requests.json")
    plan = load_json_object(OUTPUT / "energy_plan.json")
    applied = load_json_object(OUTPUT / "energy_receipt.json")
    available = {x["template_id"]: x for x in load_templates(DB)}
    checks = {}
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None
        persisted = db.execute("SELECT plan_sha256 FROM registry_applications WHERE batch_id=?",
                               (applied["batch_id"],)).fetchone()[0]
        assert persisted == plan["plan_sha256"] == applied["plan_sha256"]
        for case, item in requests.items():
            packet = load_json_object(PREP / case / "review_packet.json")
            reference = load_json_object(OUTPUT / case / "reference_review.json")
            receipt_path = OUTPUT / case / "barrier_registration_receipt.json"
            receipt = load_json_object(receipt_path)
            b = dict(db.execute("SELECT * FROM ts_barriers WHERE barrier_set_id=?",
                                (receipt["barrier_set_id"],)).fetchone())
            v = dict(db.execute("SELECT * FROM ts_validations WHERE ts_validation_id=?",
                                (b["ts_validation_id"],)).fetchone())
            assert all(b[k] == x for k, x in item["claim"].items())
            assert v == packet["registered_grade_a_validation"]
            assert b["validation_status"] == "accepted" and b["energy_convention"] == CONVENTION
            assert matched_static_convention(matched_static_rows(db,
                tuple(b[k] for k in ("initial_result_id", "ts_result_id", "final_result_id")))) == (CONVENTION, b["compatibility_fingerprint"])
            assert all(abs(b[k] - receipt[k]) < 1e-12 and abs(b[k] - x) < 1e-12
                       for k, x in packet["draft_electronic_barrier_eV"].items())
            assert all(sha256_file(Path(x["path"])) == x["sha256"] for x in reference["originals"])
            frequency_hash = db.execute("SELECT sha256 FROM files WHERE file_id=?",
                                        (v["frequency_output_file_id"],)).fetchone()[0]
            assert sha256_file(OUTPUT / case / "OUTCAR") == frequency_hash
            for name in ("OUTCAR", "POSCAR"):
                assert sha256_file(OUTPUT / case / name) == sha256_file(Path(packet["original_analysis"]["path"]).parent / name)
            t = available[receipt["template_id"]]
            assert t["evidence_valid"] and t["barrier_set_id"] == b["barrier_set_id"] and t["validation_grade"] == "A"
            checks[case] = {"barrier_set_id": b["barrier_set_id"], "template_id": t["template_id"],
                "receipt": binding(receipt_path), "registered_validation_preserved": True, "original_bytes_preserved": True,
                "current_gate": binding(Path(item["gate_decision"])), "strategy_evidence_valid": True}
    report = {"status": "PASS", "case_checks": checks, "sqlite_quick_check": "ok", "foreign_key_check": "ok",
              "append_only_plan_sha256": persisted, "scientific_jobs_launched": False,
              "free_energy_computed": False, "spreadsheet_modified": False}
    write_json_exclusive(OUTPUT / "registration_verification.json", report)
    return report


if __name__ == "__main__":
    result = verify()
    print(result["status"], {k: v["barrier_set_id"] for k, v in result["case_checks"].items()})
