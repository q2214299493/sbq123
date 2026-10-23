"""Read six late frames of existing job9848812; no remote writes or jobs."""
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .legacy_helpers import (
    reader_source as original_reader, selected_steps as original_steps,
)
from scripts.artifact_io import sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "calculations/fe110_reico_pilot300_20261022/10b_lowforce_review_20261023_v1"
SUBMISSION = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/vasp_batch_v1/submission_summary.json"
PRIOR = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/dedup_final_review_20261021_v1/collected_tail_v2/10_B/source.json"


def selected_steps(total):
    if total != 296:
        raise ValueError("reviewed closed trajectory length changed")
    return [264, 272, 280, 288, 295, 296]


def source_record():
    records = json.loads(SUBMISSION.read_bytes())["records"]
    row = next(r for r in records if r["name"] == "10_B")
    if row["job_id"] != "9848812" or row["formula"] != "C2H3":
        raise ValueError("unexpected source job")
    return {**row, "split": "train_candidate", "atom_count": 50}


def reader_source(record):
    code = original_reader(record, version=2)
    replacements = {
        inspect.getsource(original_steps): inspect.getsource(selected_steps),
        "  byte_cursor=[0]": "  byte_cursor=[0]; local_tables=[0]",
        "h.update(value); byte_cursor[0]+=len(value); return value":
            "h.update(value); byte_cursor[0]+=len(value); local_tables[0]+=int(b'magnetization (x)' in value); return value",
        "'normal_completion':True,'files':files":
            "'normal_completion':True,'local_moment_table_count':local_tables[0],'files':files",
    }
    for old, new in replacements.items():
        if code.count(old) != 1:
            raise ValueError("reviewed extraction dependency changed")
        code = code.replace(old, new)
    return code


def main():
    OUTPUT.mkdir(exist_ok=True)
    row = source_record()
    code = reader_source(row)
    digest = hashlib.sha256(code.encode()).hexdigest()
    receipt = OUTPUT / "collection_receipt.json"
    if receipt.exists():
        saved = json.loads(receipt.read_bytes())
        if saved["exit_code"] or saved["reader_sha256"] != digest or saved["output_sha256"] != sha256_file(OUTPUT / "source.json"):
            raise ValueError("preserve failed/changed extraction; choose a new checkpoint")
        print("REUSED_VERIFIED_EXTRACTION", flush=True)
        return
    with (OUTPUT / "remote_reader.py").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(code)
    try:
        with (OUTPUT / "source.json").open("xb") as stdout, (OUTPUT / "collection.stderr.txt").open("xb") as stderr:
            result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                                     "sunboquan-codex", "python3 -"], input=code.encode(), stdout=stdout, stderr=stderr,
                                    timeout=180, check=False)
    except subprocess.TimeoutExpired:
        write_json_exclusive(receipt, {"exit_code": -1, "reason": "read-only collection exceeded180s",
            "reader_sha256": digest, "output_sha256": sha256_file(OUTPUT / "source.json"),
            "source_job_id": row["job_id"], "remote_writes": False, "new_DFT": False})
        raise
    write_json_exclusive(receipt, {"exit_code": result.returncode, "reader_sha256": digest,
        "output_sha256": sha256_file(OUTPUT / "source.json"), "source_job_id": row["job_id"],
        "checked_at": datetime.now(timezone.utc).isoformat(), "remote_writes": False, "new_DFT": False})
    if result.returncode:
        raise RuntimeError("read-only collection failed; see saved stderr")
    if (OUTPUT / "source.json").stat().st_size > 16_000_000:
        raise ValueError("extraction exceeds byte budget")
    source = json.loads((OUTPUT / "source.json").read_bytes())
    previous = json.loads(PRIOR.read_bytes())
    if source["OUTCAR_sha256"] != previous["OUTCAR_sha256"] or source["OUTCAR_bytes"] != previous["OUTCAR_bytes"]:
        raise ValueError("closed OUTCAR differs from previously reviewed source")
    if [r["ionic_step"] for r in source["frames"]] != selected_steps(source["total_steps"]):
        raise ValueError("extracted frames differ from frozen six-step selection")
    print(json.dumps({"collected_frames": len(source["frames"]), "job_id": row["job_id"],
                      "local_moment_tables": source["local_moment_table_count"], "new_DFT": False}), flush=True)


if __name__ == "__main__":
    main()
