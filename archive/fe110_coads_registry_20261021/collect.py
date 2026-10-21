"""Collect only the authorized06 A/B/C closed outputs; never launch calculations."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from scripts.adsorption.collect_completed_batch import collect_one, ssh_options
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.execution_backends import load_execution_backends

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
OUT = BASE / "coadsorption_registration_20261021_v1"
OLD = ROOT / "calculations/fe110_five_c2_adsorption_20261006/final_review_20261012"
IDENTITY = Path("C:/Users/86177/.ssh/id_ed25519_fe_agent")


def main():
    OUT.mkdir(exist_ok=False)
    manifest = BASE / "vasp_batch_v1/submission_summary.json"
    records = [r for r in load_json_object(manifest)["records"] if r["name"] in {"06_A", "06_B", "06_C"}]
    if {r["name"] for r in records} != {"06_A", "06_B", "06_C"}:
        raise ValueError("exact authorized set missing")
    write_json_exclusive(OUT / "request.json", {
        "authorizing_user_request": "把06 ABC都加上录入数据库中 顺便检查一下上次01到05有没有这种共吸附的遗漏",
        "source_manifest_sha256": sha256_file(manifest),
        "prior_dedup_sha256": sha256_file(BASE / "dedup_final_review_20261021_v1/review.json"),
        "prior01_05_analysis_sha256": sha256_file(OLD / "final_analysis.json"),
        "records": records, "new_scientific_jobs": 0,
    })
    server = load_execution_backends().vasp.server_alias
    command = ["ssh", *ssh_options(IDENTITY), server, "bjobs -a -w " + " ".join(r["job_id"] for r in records)]
    run = subprocess.run(command, capture_output=True, timeout=45, check=False)
    write_json_exclusive(OUT / "scheduler.json", {
        "command": command, "exit_code": run.returncode,
        "stdout": run.stdout.decode("utf-8", "replace"), "stderr": run.stderr.decode("utf-8", "replace"),
        "observed_at": datetime.now(timezone.utc).isoformat(), "authority": "scheduler_only",
    })
    print("SCHEDULER", run.returncode, run.stdout.decode("utf-8", "replace")[:1500],
          run.stderr.decode("utf-8", "replace")[:500], flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_one, r, server, IDENTITY, OUT / "sources"): r for r in records}
        errors = []
        for future in as_completed(futures):
            record = futures[future]
            try:
                result = future.result()
                print("COLLECTED", result["name"], flush=True)
            except Exception as error:
                errors.append({"name": record["name"], "error": str(error)})
    if errors:
        write_json_exclusive(OUT / "collection_failures.json", {"failures": errors})
        raise RuntimeError("collection failed; preserve evidence before retry:" + str(errors))


if __name__ == "__main__":
    main()
