"""Resolve old replay/static pointers; read each newly identified source once."""
from __future__ import annotations

import subprocess

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .collect import OUT, PACKAGE, ROOT
from .remote_read import PROGRAM


def run():
    manifest = load_json_object(PACKAGE / "training_manifest.json")
    source = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6/replay_labels.reviewed.json"
    replay = {r["source_OUTCAR_sha256"]: r for r in load_json_object(source)["samples"]}
    submission = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_boundary_labels_20261018_v1/submission_summary.json"
    batch = load_json_object(submission)
    # Preserve actual submission fields; no paths inferred from job numbers.
    receipts = batch["records"]
    if not receipts:
        raise ValueError("inspect actual boundary submission schema before continuing")
    targets = []
    unresolved = []
    previous = load_json_object(OUT / "energy_label_sidecar_v2.json")
    missing = {r["sample_id"] for r in previous["records"] if r["pool"] == "frozen536" and "EXISTING_RAW_SOURCE_RECOVERY_REQUIRED_NOT_NEW_DFT" in r["flags"]}
    for row in [r for rows in [*manifest["splits"].values(), manifest["quarantined_observed_heldout"]] for r in rows if r["sample_id"] in missing]:
        item = replay.get(row["source_OUTCAR_sha256"])
        directory = item.get("source_directory") if item else None
        if directory is None:
            receipt = next((r for r in receipts if str(r.get("job_id")) == str(row.get("source_job_id"))), {})
            directory = receipt.get("remote_dir")
        if directory:
            targets.append({"job_id": str(row.get("source_job_id", row["sample_id"])), "sha256": row["source_OUTCAR_sha256"],
                            "directory": directory, "steps": [int(row["ionic_step"])]})
        else:
            unresolved.append(row["sample_id"])
    write_json_exclusive(OUT / "additional_remote_targets.json", {"targets": targets, "unresolved": unresolved,
                                                                "source_files": source_file_manifest([source, submission])})
    code = "TARGETS=" + repr(targets) + "\n" + PROGRAM
    with (OUT / "remote_additional_evidence.json").open("xb") as out, (OUT / "remote_additional.stderr").open("xb") as err:
        result = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                                 "-o", "ConnectTimeout=12", "sunboquan-codex", "python3 -B -"],
                                input=code.encode(), stdout=out, stderr=err, timeout=240)
    write_json_exclusive(OUT / "additional_remote_receipt.json", {"exit_code": result.returncode, "targets": len(targets),
                                                                "remote_writes_or_new_jobs": False})
    if result.returncode:
        raise RuntimeError("additional source read failed; preserve receipt and inspect")
    evidence = load_json_object(OUT / "remote_additional_evidence.json")
    print({"new_sources": len(evidence["results"]), "hash_matches": sum(r.get("expected_hash_matches", False) for r in evidence["results"]),
           "unresolved": unresolved}, flush=True)


if __name__ == "__main__":
    run()
