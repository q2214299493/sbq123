"""BUCT2 replica provenance only; canonical registry planning/apply remain separate."""
import argparse
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from .arbitrate import bindings, observe
from .deploy import OUT, REMOTE, ROOT
from .prepare import PACKAGE

CID = "fe110_c2_supplement_buct2_gpu_20261106_v1"
JID = "job_" + CID
DB = ROOT / "data/project_registry.sqlite3"


def prepare():
    saved = load_json_object(OUT / "submission_receipt.json")
    request = load_json_object(PACKAGE / "request.json")
    if saved["exit_code"] != 0 or saved["request_sha256"] != sha256_file(PACKAGE / "request.json"):
        raise ValueError("successful exact native submission required")
    snapshot = observe("buct2_gpu", bindings()["buct2_gpu"])
    write_json_exclusive(OUT / "registration_native_observation.json", snapshot)
    state = {"PENDING": "SUBMITTED", "RUNNING": "RUNNING"}.get(snapshot["state"])
    if state is None:
        raise ValueError("replica already terminal;review native terminal state before registration")
    now = datetime.now(timezone.utc).isoformat()
    rows = {"calculations": [{"calculation_id": CID, "parent_calculation_id": "fe110_c2_supplement_gpu_20261106_v1",
        "module": "adsorption_workflow", "purpose": "Same12 accepted seeds/checkpoint/budget onBUCT2;first-ready redundant replica",
        "scientific_system": "true_Fe110_Fe45_C2_site_supplement_05_06_07_09_11_12_13_14_18",
        "workflow_status": state.lower(), "created_at": saved["submitted_at"], "source_record": str(PACKAGE / "request.json"),
        "notes": "User authorized alternate GPU and keep-first;BUCT2 requires permit after peer terminal;no training,promotion,CPU fallback,VASP or accepted energy."}],
        "jobs": [{"job_record_id": JID, "calculation_id": CID, "scheduler_job_id": saved["job_id"], "scheduler": "Slurm",
            "server_alias": "BUCT2", "queue": "gpu", "remote_directory": REMOTE, "submit_script": "run.sbatch",
            "submitted_at": saved["submitted_at"]}],
        "job_status_history": [{"job_record_id": JID, "scheduler_status": state, "scientific_status": "Not assessed;GPU prediction only;site/connectivity review pending",
            "checked_at": snapshot["checked_at"], "source_command": "scontrol show job -o " + saved["job_id"],
            "source_text": snapshot["scheduler_raw"], "reviewer": "Codex",
            "notes": "Native PENDING normalized to registry SUBMITTED only;not force convergence or scientific acceptance."}], "files": []}
    paths = sorted(p for p in PACKAGE.rglob("*") if p.is_file())
    paths += [OUT / name for name in ("preparation_receipt_v3.json", "runtime_manifest.json", "parts_manifest.json",
        "runtime_assemble.receipt.json", "runtime_unpack.receipt.json", "runtime_unpack.stdout", "portable_mpdec_manifest.json",
        "native_preflight_v3.receipt.json", "native_preflight_v3.stdout", "submission_receipt.json", "submit.stdout",
        "registration_native_observation.json", "coordinator_launch.json", "coordinator_lock.json", "coordinator_authorization.json")]
    for index, path in enumerate(paths):
        remote = REMOTE + "/" + path.relative_to(PACKAGE).as_posix() if path.is_relative_to(PACKAGE) else None
        rows["files"].append({"file_id": CID + f"__file_{index:03d}", "calculation_id": CID, "job_record_id": JID,
            "role": "GPU_replica_input_or_submission_provenance", "filename": path.name, "local_path": str(path),
            "remote_path": remote, "storage_mode": "local_and_remote" if remote else "local_only",
            "byte_size": path.stat().st_size, "sha256": sha256_file(path), "existence_status": "confirmed",
            "notes": "Prediction/deployment/arbitration evidence only;no DFT result."})
    runtime = load_json_object(OUT / "runtime_manifest.json")
    supplement = load_json_object(OUT / "portable_mpdec_manifest.json")
    for name, path, digest, size in [("runtime_archive", REMOTE + "/runtime.tgz", runtime["archive_sha256"], runtime["archive_bytes"]),
        ("checkpoint", request["model"]["path"], request["model"]["sha256"], 126477760),
        ("portable_decimal_library", REMOTE + "/native_libs/libmpdec.so.3", supplement["sha256"], supplement["bytes"])]:
        rows["files"].append({"file_id": CID + "__" + name, "calculation_id": CID, "job_record_id": JID,
            "role": "frozen_runtime_input", "filename": path.rsplit("/", 1)[1], "remote_path": path,
            "storage_mode": "remote_only", "byte_size": size, "sha256": digest, "existence_status": "confirmed",
            "notes": "BUCT2 archived environment/model/CPU library,checked by native preflight;not a scientific result."})
    write_json_exclusive(OUT / "registry_batch.json", {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": CID + "_submission", "created_at": now, "reviewer": "Codex",
        "reason": "Explicit user authority: second GPU submission,keep first ready;append provenance only.", "rows": rows})
    print("PREPARED_METADATA", {key: len(value) for key, value in rows.items()}, "scientific_results=0")


def verify():
    batch = load_json_object(OUT / "registry_batch.json")
    keys = {"calculations": "calculation_id", "jobs": "job_record_id", "files": "file_id"}
    count = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, key in keys.items():
            for row in batch["rows"][table]:
                saved = db.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (row[key],)).fetchone()
                if saved is None or any(saved[k] != v for k, v in row.items()):
                    raise ValueError("readback differs: " + table)
                count += 1
        row = batch["rows"]["job_status_history"][0]
        saved = db.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?", (JID, row["checked_at"])).fetchall()
        if len(saved) != 1 or any(saved[0][k] != v for k, v in row.items()):
            raise ValueError("status readback differs")
        count += 1
        if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (CID,)).fetchone():
            raise ValueError("prediction stage acquired scientific results")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("registry integrity failed")
    write_json_exclusive(OUT / "registry_verification.json", {"status": "PASS", "rows_read_back": count,
        "new_GPU_jobs": 1, "candidate_count": 12, "scientific_results": 0})
    print("VERIFIED", count, "provenance rows;zero scientific results")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    {"prepare": prepare, "verify": verify}[parser.parse_args().phase]()
