"""Reuse closed snapshots and resume only the two stalled file reads."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .collect import BASE, SUBMITTED
from .recover import one_case, save_case

OUTPUT = BASE / "paired_cost_comparison_20261028_v5"


def collect():
    OUTPUT.mkdir(exist_ok=False)
    prior = BASE / "paired_cost_comparison_20261028_v4"
    reused = []
    for name in ["10_A", "C3_05"]:
        path = prior / "snapshots" / name / "control/extracted.json"
        record = load_json_object(path)
        if record["state"] != "DONE" or not record["OUTCAR"]["stable_during_read"]:
            raise ValueError("only stable closed sources may be reused")
        save_case(record, OUTPUT)
        reused.append(path)
    source = load_json_object(SUBMITTED / "submission_summary.json")
    rows = [{**{k: r[k] for k in ["name", "model", "job_id", "remote_dir"]}, "atom_count": 50 if r["name"] == "10_A" else 51}
        for r in source["records"] if r["model"] == "new512"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one_case, row, OUTPUT, 180, True) for row in rows]
        records = [f.result() for f in futures]
    result = {"status": "COMPLETE" if all(r["status"] == "COLLECTED" for r in records) else "PARTIAL",
        "reused_closed_jobs": ["9925060", "9925062"], "records": records,
        "source_files": source_file_manifest([Path(__file__), Path(__file__).with_name("recover.py"), Path(__file__).with_name("collect.py"), *reused,
            *sorted(OUTPUT.glob("*.raw")), *sorted(OUTPUT.glob("*_transport.json"))])}
    write_json_exclusive(OUTPUT / "collection.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    collect()
